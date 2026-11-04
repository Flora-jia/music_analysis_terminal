"""Bounded asynchronous recording of the exact DMA1 model features."""
from pathlib import Path
import copy
import hashlib
import json
import os
import queue
import re
import threading
import time
import numpy as np

LABELS=('piano','guitar','violin')
GROUND_TRUTHS=LABELS+('silence','background','unlabeled')

def atomic_json(path,value):
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    os.replace(str(temp),str(path))

def feature_diagnostics(features,result):
    mel=np.asarray(features['mel']);power=np.asarray(features['power'])
    if (mel.shape!=(64,63) or power.shape!=(513,63) or
            not np.isfinite(mel).all() or not np.isfinite(power).all() or
            np.any(power<0) or np.any(mel<0) or np.any(mel>1)):
        raise ValueError('Invalid capture features')
    probs=result.get('cnn_probabilities') or result.get('probabilities')
    rank=sorted(((k,float(probs[k])) for k in LABELS),key=lambda x:x[1],reverse=True) if probs else []
    return dict(top1=rank[0][0] if rank else None,top1_probability=rank[0][1] if rank else None,
        top2=rank[1][0] if rank else None,top1_top2_margin=rank[0][1]-rank[1][1] if rank else None,
        probability_entropy=-sum(v*np.log(max(v,1e-12)) for _,v in rank) if rank else None,
        mel_min=float(mel.min()),mel_max=float(mel.max()),mel_mean=float(mel.mean()),mel_std=float(mel.std()),
        mel_floor_fraction=float(np.mean(mel<=.001)),mel_peak_fraction=float(np.mean(mel>=.999)),
        power_max=float(power.max()),power_mean=float(power.mean()))

class FeatureRecorder:
    """One fixed operator label per run. No predictions are used as training labels."""
    def __init__(self,directory,epoch,label,metadata=None,max_segments=120,max_mb=256,queue_size=4):
        if not isinstance(epoch,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',epoch):raise ValueError('Invalid capture epoch')
        if label not in GROUND_TRUTHS:raise ValueError('Invalid operator label')
        if not 1<=max_segments<=10000 or not 1<=max_mb<=4096:raise ValueError('Invalid capture limits')
        self.directory=Path(directory)/epoch
        self.directory.mkdir(parents=True,exist_ok=False)
        self.label=label;self.epoch=epoch;self.limit=max_segments;self.byte_limit=int(max_mb*1024*1024)
        self.lock=threading.RLock();self.queue=queue.Queue(maxsize=queue_size);self.closing=False
        self.seen=self.accepted=self.written=self.queue_dropped=self.write_failed=self.skipped_limit=0
        self.reserved_bytes=self.bytes_written=0;self.error=None
        self.metadata=dict(schema='ac820.instrument_capture.v1',epoch=epoch,operator_label=label,
            label_source='operator_fixed_per_run',created_unix=time.time(),fs_hz=16000,
            feature_contract=dict(power_shape=[513,63],mel_shape=[64,63],fft_n=1024,hop=256,
                segment_samples=16000,frames=63,power='BFP restored float64; no phase or PCM',
                mel='exact float32 inference input; global max reference, -80..0 dB mapped to 0..1'),
            metadata=copy.deepcopy(metadata or {}))
        self._manifest()
        self.thread=threading.Thread(target=self._run,name='instrument_capture_writer',daemon=True)
        self.thread.start()
    def status(self):
        with self.lock:
            return dict(enabled=True,directory=str(self.directory),operator_label=self.label,
                seen=self.seen,accepted=self.accepted,written=self.written,queue_dropped=self.queue_dropped,
                write_failed=self.write_failed,skipped_limit=self.skipped_limit,pending=self.accepted-self.written-self.write_failed,
                reserved_bytes=self.reserved_bytes,bytes_written=self.bytes_written,error=self.error,
                closing=self.closing,max_segments=self.limit,max_bytes=self.byte_limit)
    def _manifest(self):
        atomic_json(self.directory/'manifest.json',dict(self.metadata,status=self.status()))
    def submit(self,features,result):
        """Called only by inference owner. Copies CPU arrays; never waits for the writer."""
        try:
            diagnostics=feature_diagnostics(features,result)
            arrays={k:np.array(features[k],copy=True) for k in ('power','mel','exponents')}
            if arrays['exponents'].shape!=(63,):raise ValueError('Invalid BFP exponent shape')
            row=dict(schema='ac820.instrument_segment.v1',epoch=self.epoch,operator_label=self.label,
                label_source='operator_fixed_per_run',recorded_unix=time.time(),
                result=copy.deepcopy(result),diagnostics=diagnostics)
            row['training_eligible_three_class']=bool(self.label in LABELS and result.get('label')!='silence' and not result.get('gap'))
            # reserve an upper bound for NPY headers, metadata and JSONL overhead
            reserve=sum(a.nbytes for a in arrays.values())+len(json.dumps(row,ensure_ascii=False,allow_nan=False).encode('utf-8'))+16384
            with self.lock:
                if self.closing:return False
                self.seen+=1
                if self.error:return False
                if self.accepted>=self.limit or self.reserved_bytes+reserve>self.byte_limit:
                    self.skipped_limit+=1;return False
                row['record_id']=self.seen
                try:self.queue.put_nowait((row,arrays))
                except queue.Full:self.queue_dropped+=1;return False
                self.accepted+=1;self.reserved_bytes+=reserve
            return True
        except Exception as exc:
            with self.lock:self.error='capture submit: '+str(exc)
            return False
    def _write(self,row,arrays):
        name='segment_{:06d}.npz'.format(row['record_id'])
        path=self.directory/name;temp=path.with_suffix('.npz.tmp')
        with temp.open('wb') as stream:np.savez(stream,**arrays)
        os.replace(str(temp),str(path))
        row['features_file']=name;row['features_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        line=json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n'
        with (self.directory/'segments.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(line);stream.flush()
        return path.stat().st_size+len(line.encode('utf-8'))
    def _run(self):
        while True:
            try:item=self.queue.get(timeout=.05)
            except queue.Empty:
                with self.lock:
                    if self.closing:break
                continue
            try:
                with self.lock:failed=self.error is not None
                if failed:raise RuntimeError('Writer disabled after previous failure')
                size=self._write(*item)
                with self.lock:self.written+=1;self.bytes_written+=size
            except Exception as exc:
                with self.lock:self.write_failed+=1;self.error='capture write: '+str(exc)
            finally:self.queue.task_done()
            try:self._manifest()
            except Exception as exc:
                with self.lock:self.error='capture manifest: '+str(exc)
        try:self._manifest()
        except Exception as exc:
            with self.lock:self.error='capture final manifest: '+str(exc)
    def close(self):
        with self.lock:self.closing=True
        self.thread.join(timeout=10)
        if self.thread.is_alive():raise RuntimeError('Feature writer still active; retain recorder')
        return self.status()
