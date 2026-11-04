"""SPEC v2 transport and shared C-note state. No Python pitch estimator."""
import copy
import json
import math
from pathlib import Path
import threading
import time
import uuid
from collections import deque
import numpy as np
MAGIC=0x53504543
HEADER,BINS,WORDS,N,HOP,FS=16,2049,2065,4096,512,16000
BYTES=WORDS*4
class InvalidSpectrum(ValueError):pass
SOLFEGE=('do','升do','re','升re','mi','fa','升fa','sol','升sol','la','升la','si')

def decode_packet(words):
    w=np.asarray(words,dtype='<u4')
    if w.shape!=(WORDS,):raise ValueError('SPEC v2 requires 2065 words / 8260 bytes')
    for index,value in {0:MAGIC,1:0x20040,2:BYTES,6:FS,7:0x02001000,8:0x10801,9:0x11557}.items():
        if int(w[index])!=value:raise ValueError('SPEC header mismatch at word {}'.format(index))
    if np.any(w[HEADER:]>>16!=np.arange(BINS,dtype=np.uint32)):
        raise ValueError('SPEC bins missing, duplicated or reordered')
    if int(w[10]) or int(w[14]) or int(w[15])!=N:
        raise ValueError('SPEC flagged frame: flags=0x%X source_drop=%d fft_count=%d'%tuple(map(int,w[[10,14,15]])))
    mag=(w[HEADER:]&65535).astype(np.float64)
    best=0;best_mag=0
    for k in range(13,513):
        m=mag[k]
        if m>=100 and m>best_mag and m>=mag[k-1] and m>mag[k+1]:best,best_mag=k,m
    if int(w[12])!=((best<<16)|int(best_mag)):
        raise ValueError('SPEC PL/PS dominant peak mismatch')
    neighbors=0 if not best_mag else (int(mag[best-1])<<16)|int(mag[best+1])
    if int(w[13])!=neighbors:raise ValueError('SPEC peak neighbor mismatch')
    frame=int(w[3]);first=int(w[4])|(int(w[5])<<32)
    if first!=frame*HOP:raise ValueError('SPEC frame/sample sequence mismatch')
    return dict(sequence=frame,first_sample=first,dropped_frames=int(w[11]),source_drop=int(w[14]),
                flags=int(w[10]),hw_peak_bin=best,hw_peak_mag=int(best_mag),magnitude=mag)


def spectrum_bars(mag,n_bars=128):
    m=np.asarray(mag,dtype=np.float64)
    if isinstance(n_bars,bool) or not isinstance(n_bars,int) or not 2<=n_bars<=2049:raise ValueError('bars must be 2..2049')
    if m.shape!=(2049,) or not np.isfinite(m).all() or np.any(m<0):raise ValueError('invalid 2049-bin magnitudes')
    edges=np.linspace(0,2049,n_bars+1,dtype=int)
    values=np.maximum.reduceat(m,edges[:-1])
    centers=(edges[:-1]+edges[1:]-1)*.5*FS/N
    return centers.tolist(),values.tolist()

class SpectrumAnalysis:
    def __init__(self,engine=None,clock=time.monotonic):
        self.clock=clock;self.lock=threading.RLock();self.session=uuid.uuid4().hex
        if engine is None:
            from dsp.note_engine import NoteEngine
            engine=NoteEngine(session_id=int(self.session[:8],16),clock=clock)
        self.engine=engine;self.frames=0;self.gaps=0;self.missing_frames=0;self.last_sequence=None;self.first=None
        self.last_time=None;self.capture={};self.connected=False;self.error=None;self.lifecycle='CREATED'
        self.pitch=self.spectrum=self.current=None;self.notes=deque(maxlen=120);self.records={};self.opens={}
        self.events=deque(maxlen=512);self.event_sequence=0;self.journal_evictions=0;self.record_evictions=0;self.resync_count=0
        self.score_generation=0;self.native_summary={};self.model=None;self.model_at=None;self.model_error=None
        self.model_enabled=True;self.model_windows=deque(maxlen=8);self.shared_start=False;self.fir_delay_samples=9.5
        self.stopped=False
        self.model_history=deque(maxlen=512);self.model_history_evictions=0;self.run_metadata={}
    def mark_capture_started(self,shared_start=True,fir_delay_samples=9.5):
        with self.lock:
            self.shared_start=bool(shared_start);self.fir_delay_samples=fir_delay_samples
            self.lifecycle='RUNNING';self.stopped=False
    def configure(self,high,low):raise ValueError('The supplied C ABI has fixed thresholds; use silent calibration instead')
    def clear_score(self):
        with self.lock:self.notes.clear();self.records.clear();self.score_generation+=1
    def _note(self,midi,frequency,confidence,identity):
        jp=self.engine.jianpu(midi)
        if not jp['valid']:raise ValueError('C engine returned invalid MIDI')
        return dict(id=identity,midi=midi,degree=jp['degree'],accidental=jp['accidental'],octave=midi//12-1,
            note=('♯' if jp['accidental'] else '')+str(jp['degree']),note_cn=SOLFEGE[midi%12],
            note_name=jp['name'],freq=frequency,confidence=confidence,confidence_kind='native_yinfft_score')
    def _associate(self,note):
        note['instrument_matches']=[]
        if not self.shared_start or self.fir_delay_samples is None or note.get('start_sample') is None:return
        start=note['start_sample']-self.fir_delay_samples;end=note.get('end_sample',start)-self.fir_delay_samples
        for m in self.model_windows:
            if m.get('epoch')!=self.session:continue
            if max(start,m['window_start'])<min(end,m['window_end']):
                note['instrument_matches'].append(dict(segment=m['segment'],cnn_label=m.get('cnn_label'),
                    reference_label=m.get('reference_label'),confidence=m.get('cnn_confidence'),
                    reference_similarity=m.get('reference_similarity'),association='overlap_nominal_fir_delay',
                    calibrated=False))
    def _commit(self,note):
        identity=note['id'];self._associate(note)
        if identity in self.records:self.records[identity].update(note);return
        if len(self.records)>=4096:
            self.records.pop(next(iter(self.records)));self.record_evictions+=1
        self.records[identity]=note;self.notes.append(note)
    def _truncate(self,cause):
        for identity,note in list(self.opens.items()):
            n=dict(note);end=max(n.get('start_sample') or 0,n.get('end_sample') or 0)
            n.update(end_sample=end,duration_ms=(end-n['start_sample'])*1000/FS if n.get('start_sample') is not None else None,
                completed=True,truncated=True,time_quality=2,runtime_reason=cause,timing_estimated=True)
            self._commit(n)
        self.opens.clear();self.current=self.pitch=None
    def _apply(self,output):
        if not output:return
        self.native_summary=output['summary']
        for event in output['events']:
            e=dict(event);self.event_sequence+=1;e['transport_seq']=self.event_sequence;e['epoch']=self.session
            if len(self.events)==self.events.maxlen:self.journal_evictions+=1
            self.events.append(e)
            kind=e['type']
            if kind in (3,4):
                self.resync_count+=1;self._truncate(e.get('runtime_reason','resync'));continue
            if kind not in (1,2):continue
            identity='{}:{}'.format(e['session_id'],e['note_id'])
            note=self._note(e['midi'],e['frequency_hz'],e['confidence'],identity)
            note.update(session_id=e['session_id'],native_note_id=e['note_id'],event_seq=e.get('event_seq'),
                start_sample=e['start_sample'],end_sample=e['end_sample'] if kind==2 else e['start_sample'],
                duration_ms=(e['end_sample']-e['start_sample'])*1000/FS if kind==2 else 0.,
                frame=e['frame_id'],start_frame=e['frame_id'],end_frame=e['frame_id'],frames=0,
                reason=e['reason'],time_quality=e['time_quality'],runtime_reason=e.get('runtime_reason'),
                decision_sample=e.get('decision_sample'),flags=e.get('flags'),native_schema=e.get('native_schema'),
                fs_hz=FS,timing_estimated=True,truncated=e['time_quality']==2 or bool(e.get('flags',0)&1),completed=kind==2,
                native_event=e)
            if kind==1:self.opens[identity]=note
            else:
                previous=self.opens.pop(identity,None)
                if previous:note['start_frame']=previous.get('start_frame',note['start_frame'])
                self._commit(note)
        cur=output['current']
        self.current=self.pitch=None
        if cur and cur['valid']:
            identity='{}:{}'.format(output['session_id'],cur['note_id'])
            pitch=self._note(cur['midi'],cur['frequency_hz'],cur['confidence'],identity)
            pitch.update(frame=cur['frame_id'],bin=cur['frequency_hz']*N/FS,magnitude=self.capture.get('hw_peak_mag',0),
                         feature_sample=cur['feature_sample'],decision_sample=cur['decision_sample'])
            self.pitch=pitch
            note=self.opens.get(identity)
            if note is None:
                note=dict(pitch,start_sample=None,end_sample=cur['feature_sample'],duration_ms=None,completed=False,
                    session_id=output['session_id'],native_note_id=cur['note_id'],time_quality=2,truncated=True,
                    timing_estimated=True,recovered_without_on=True,start_frame=cur['frame_id'],frames=0)
                self.opens[identity]=note
            note.update(pitch);note['end_sample']=max(note.get('end_sample') or 0,cur['feature_sample'])
            if note.get('start_sample') is not None:note['duration_ms']=(note['end_sample']-note['start_sample'])*1000/FS
            self.current=note
    def feed(self,words):
        try:p=decode_packet(words)
        except Exception:
            self.bad_packet('SPEC validation failed');raise InvalidSpectrum('SPEC validation failed')
        with self.lock:
            seq=p['sequence'];first=p['first_sample'];gap=0
            if self.last_sequence is not None:
                delta=(seq-self.last_sequence)&0xffffffff
                if not delta or delta&0x80000000 or first-self.first!=delta*HOP:
                    self.bad_packet('SPEC sequence error');raise InvalidSpectrum('SPEC sequence error')
                gap=delta-1
                if gap:self.gaps+=1;self.missing_frames+=gap
            mag=p.pop('magnitude');self.capture=p
            output=self.engine.process(mag,first,seq,gap)
            self.last_sequence,self.first=seq,first;self.frames+=1;self.last_time=self.clock()
            self.connected=True;self.error=None;self.stopped=False;self._apply(output)
            self.spectrum=dict(freq_hz=(np.arange(BINS)*FS/N).tolist(),mag=mag.astype(int).tolist(),
                units='pl_cordic_magnitude',frame=seq,source='pl_spec_v2',fft_n=N,hop_samples=HOP)
    def bad_packet(self,cause):
        with self.lock:
            self._apply(self.engine.bad_packet(cause=cause));self.connected=False;self.error=cause;self.pitch=self.current=self.spectrum=None
    def poll_watchdog(self):
        with self.lock:
            output=self.engine.poll()
            if output:
                self._apply(output);self.connected=False;self.error='No valid SPEC for 128ms';self.spectrum=None
    def fail(self,message):
        with self.lock:
            self.bad_packet(str(message));self.lifecycle='FAULT'
    def stop(self,cause='stop'):
        with self.lock:
            self._apply(self.engine.stop(cause));self._truncate(cause)
            self.connected=False;self.pitch=self.current=self.spectrum=None;self.stopped=True
    def close_engine(self):
        with self.lock:self._apply(self.engine.close())
    def calibrate(self):
        with self.lock:self._apply(self.engine.calibrate());return dict(ok=True,calibrated=False)
    def reset_session(self,session_id):
        with self.lock:
            self._apply(self.engine.reset(session_id))
            self.last_time=None;self.connected=False;self.spectrum=None
    def model_failed(self,message):
        with self.lock:self.model_error=str(message);self.model=None;self.model_at=None
    def update_model(self,result):
        clean=copy.deepcopy(result);json.dumps(clean,allow_nan=False)
        if clean.get('label') not in ('piano','guitar','violin','silence'):raise ValueError('Unknown instrument')
        if clean.get('epoch')!=self.session:raise ValueError('Model result belongs to another epoch')
        with self.lock:
            self.model=clean;self.model_at=self.clock();self.model_error=None;self.model_windows.append(clean)
            keys=('epoch','segment','window_start','window_end','label','confidence','probabilities',
                  'cnn_label','cnn_confidence','cnn_probabilities','reference_label','reference_similarity',
                  'reference_margin','reference_class_similarities','rms_est','gap','dropped',
                  'compute_ms','receive_ms','capture_to_result_ms','inference_queue_drops','time_quality','decision_source','piano_review','piano_support')
            history={k:copy.deepcopy(clean[k]) for k in keys if k in clean}
            history['result_monotonic']=self.model_at
            if len(self.model_history)==self.model_history.maxlen:self.model_history_evictions+=1
            self.model_history.append(history)
            for note in self.records.values():self._associate(note)

    def dashboard_snapshot(self,score_version=None,include_spectrum=False):
        """Small UI snapshot. HTTP keeps the full snapshot and raw event journal."""
        with self.lock:
            age=None if self.last_time is None else max(0.,self.clock()-self.last_time)
            fresh=self.connected and not self.error and age is not None and age<.128
            model_age=None if self.model_at is None else max(0.,self.clock()-self.model_at)
            ready=self.model_enabled and not self.model_error and model_age is not None and model_age<5.
            source=self.model or {}
            instrument=dict(enabled=self.model_enabled,error=self.model_error,
                label=source.get('label') if ready else None,cnn_label=source.get('cnn_label') if ready else None)
            version=(self.score_generation,self.event_sequence,self.model_at)
            score=None
            if score_version!=version:
                score=[{k:v for k,v in note.items() if k!='native_event'} for note in self.notes]
            return copy.deepcopy(dict(session=self.session,data_fresh=bool(fresh),age_seconds=age,
                fs_hz=FS,fft_n=N,score_version=version,score=score,score_generation=self.score_generation,
                current_note=self.current if fresh else None,
                spectrum=self.spectrum if fresh and include_spectrum else None,
                capture={'hw_peak_bin':self.capture.get('hw_peak_bin',0)},
                resync_count=self.resync_count,instrument=instrument,instrument_ready=bool(ready)))

    def snapshot(self):
        with self.lock:
            age=None if self.last_time is None else max(0.,self.clock()-self.last_time)
            fresh=self.connected and not self.error and age is not None and age<.128
            model_age=None if self.model_at is None else max(0.,self.clock()-self.model_at)
            ready=self.model_enabled and not self.model_error and model_age is not None and model_age<5.
            instrument=dict(self.model or {},data_fresh=bool(ready),age_seconds=model_age,error=self.model_error,
                enabled=self.model_enabled,source='pl_fft1024_dma1')
            if not ready:
                for k in ('label','cnn_label','reference_label','confidence','cnn_confidence','probabilities','cnn_probabilities','reference_similarity'):instrument[k]=None
            return copy.deepcopy(dict(schema='ac820.live.v2',data_origin='adc',session=self.session,
                lifecycle=self.lifecycle,connected=self.connected,data_fresh=bool(fresh),age_seconds=age,
                fs_hz=FS,fft_n=N,hop_samples=HOP,received_frames=self.frames,pitch=self.pitch if fresh else None,
                spectrum=self.spectrum if fresh else None,current_note=self.current if fresh else None,
                score=[{k:v for k,v in note.items() if k!='native_event'} for note in self.notes],score_generation=self.score_generation,history=[],logs=[],error=self.error,
                board_error=self.error,port='PYNQ SPEC v2 / C note engine',baud=None,source='pynq_dma_spectrum',
                capture=dict(self.capture,discontinuities=self.gaps,missing_frames=self.missing_frames),
                events=list(self.events)[-32:],event_sequence=self.event_sequence,event_window_start=self.events[0]['transport_seq'] if self.events else 0,resync_count=self.resync_count,
                event_journal_evictions=self.journal_evictions,record_evictions=self.record_evictions,
                native_summary=self.native_summary,pitch_backend='libmusic_ps 2.0.0',instrument=instrument,
                instrument_ready=bool(ready),pcm_available=False,
                timing=dict(epoch=self.session,shared_start=self.shared_start,fir_delay_samples=self.fir_delay_samples,
                    mapping='nominal FIR group delay, not hardware-calibrated'),
                segmentation=dict(configurable=False,high=None,low=None,stable_frames=2,harmonic_tracking=True,
                    frame_ms=32,window_ms=256,watchdog_ms=128,units='native_C_onset_and_calibration',
                    calibrated=bool(self.native_summary.get('calibrated')))))
    def pcm_snapshot(self):return dict(schema='ac820.pcm.unavailable.v1',available=False,samples=[],data_fresh=False,reason='SPEC has no PCM or phase')
    def export_records(self,path):
        with self.lock:
            value=dict(schema='ac820.note_recording.v1',epoch=self.session,notes=list(self.records.values()),
                       events=list(self.events),record_evictions=self.record_evictions,journal_evictions=self.journal_evictions,
                       run_metadata=copy.deepcopy(self.run_metadata),model_history=copy.deepcopy(list(self.model_history)),
                       model_history_evictions=self.model_history_evictions,
                       stream_summary=dict(received_frames=self.frames,discontinuities=self.gaps,missing_frames=self.missing_frames,
                           error=self.error,resync_count=self.resync_count,lifecycle=self.lifecycle,
                           final_capture=copy.deepcopy(self.capture)))
        p=Path(path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');return p

from dma_transport import PacketReceiver,NoPacketYet,ReceiverCancelled,DMAFault

class SpectrumReceiver(PacketReceiver):
    def __init__(self,overlay,mmio_factory=None,allocator=None,**kwargs):
        if mmio_factory is None:
            from pynq import MMIO
            mmio_factory=MMIO
        if allocator is None:
            from pynq import allocate
            allocator=allocate
        desc=overlay.ip_dict['axi_dma_0'];params={k.lower():v for k,v in desc.get('parameters',{}).items()}
        if int(str(params.get('c_include_sg','0')),0):raise ValueError('Requires simple DMA0')
        super().__init__(mmio_factory(desc['phys_addr'],desc['addr_range']),allocator,2065,**kwargs)
