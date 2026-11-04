"""DMA1 capture never waits for NumPy inference; only complete batches coalesce."""
from pathlib import Path
import queue
import threading
import time
from dma_transport import PacketReceiver,NoPacketYet,ReceiverCancelled,DMAFault
from pl_fft import BatchAssembler,decode_frame


PIANO_REVIEW_WEIGHTS_SHA='b3cfc4c092a788968e343b6b06bc678ea79d840bab59cf7c772494b948f727cf'
PIANO_REVIEW_THRESHOLDS=dict(cnn_max=.90,guitar_protect=.85,piano_min=.10,reference_min=.80,margin_min=.04)

def review_instrument(result,enabled=False):
    """Optional piano verification; never changes the raw CNN fields/probabilities."""
    if not enabled or result.get('decision_source')=='audio_piano_support':return result
    import math
    out=dict(result)
    out.setdefault('cnn_label',out.get('label'))
    out.setdefault('cnn_confidence',out.get('confidence'))
    out.setdefault('cnn_probabilities',out.get('probabilities'))
    review=dict(policy='piano_review_v1',applied=False,reason='not_eligible',
                thresholds=dict(PIANO_REVIEW_THRESHOLDS))
    out['piano_review']=review;out['decision_source']='cnn'
    raw=out['cnn_label'];probs=out.get('cnn_probabilities')
    if raw not in ('guitar','violin') or not isinstance(probs,dict):
        review['reason']='silence_or_already_piano';return out
    try:
        values=[float(probs[k]) for k in ('piano','guitar','violin')]
        conf=float(out['cnn_confidence'])
        similarity=float(out.get('reference_similarity'))
        margin=float(out.get('reference_margin'))
    except (KeyError,ValueError,TypeError):
        review['reason']='missing_evidence';return out
    if not all(math.isfinite(v) for v in values+[conf,similarity,margin]) or any(v<0 or v>1 for v in values+[conf]) or abs(sum(values)-1)>.02 or not -1<=similarity<=1 or not 0<=margin<=2 or abs(conf-values[1 if raw=='guitar' else 2])>.02 or conf<max(values)-.02:
        review['reason']='invalid_evidence';return out
    if conf>=PIANO_REVIEW_THRESHOLDS['cnn_max'] or (raw=='guitar' and conf>=PIANO_REVIEW_THRESHOLDS['guitar_protect']):
        review['reason']='protected_cnn';return out
    if (values[0]<PIANO_REVIEW_THRESHOLDS['piano_min'] or out.get('reference_label')!='piano' or
        similarity<PIANO_REVIEW_THRESHOLDS['reference_min'] or margin<PIANO_REVIEW_THRESHOLDS['margin_min']):
        review['reason']='insufficient_piano_evidence';return out
    out['label']='piano'
    out['confidence']=None  # No calibrated probability exists for this combined rule.
    out['decision_source']='cnn_reference_piano_review'
    review.update(applied=True,reason='reference_supported_piano')
    return out



class AudioPianoReferenceModel:
    """One unchanged CNN pass, plus a learned local piano-vs-negative support model."""
    def __init__(self,base,reference_dir):
        import numpy as np
        self.base=base;self.labels=base.labels;self.last_reference=None
        info=base.meta['piano_support'];self.source_group=info['source_group']
        with np.load(Path(reference_dir)/'reference_bank.npz',allow_pickle=False) as z:
            self.center=z['piano_support_center'].astype('f8')
            self.prototypes=z['piano_support_prototypes'].astype('f8')
            self.negatives=z['piano_support_negatives'].astype('f8')
            self.thresholds=z['piano_support_thresholds'].astype('f8')
            self.margin=float(z['piano_support_margin'])
        if (self.center.shape!=(64,) or self.prototypes.ndim!=2 or self.prototypes.shape[1]!=64 or
            not len(self.prototypes) or self.negatives.ndim!=2 or self.negatives.shape[1]!=64 or not len(self.negatives) or
            self.thresholds.shape!=(len(self.prototypes),) or not .01<=self.margin<=.5 or
            not all(np.isfinite(a).all() for a in [self.center,self.prototypes,self.negatives,self.thresholds]) or
            not np.allclose(self.center,base.center,rtol=1e-6,atol=1e-6) or
            not np.allclose(np.linalg.norm(self.prototypes,axis=1),1,atol=1e-5) or
            not np.allclose(np.linalg.norm(self.negatives,axis=1),1,atol=1e-5) or
            np.any(self.thresholds<.8) or np.any(self.thresholds>1.03)):
            raise ValueError('Invalid or unpaired piano support model')
    def evidence(self,embedding):
        import numpy as np
        x=np.asarray(embedding,dtype='f8')-self.center;norm=float(np.linalg.norm(x))
        if not np.isfinite(norm) or norm<1e-12:
            return dict(eligible=False,applied=False,reason='degenerate_embedding')
        x=x/norm;scores=np.clip(self.prototypes@x,-1,1)
        negative=float(np.max(self.negatives@x))
        accepted=(scores>=self.thresholds)&(scores-negative>=self.margin)
        indices=np.flatnonzero(accepted)
        index=int(indices[np.argmax(scores[indices])]) if len(indices) else int(scores.argmax())
        return dict(eligible=bool(len(indices)),applied=False,reason='within_support' if len(indices) else 'outside_support',
            source_group=self.source_group,template=index,similarity=float(scores[index]),
            required_similarity=float(self.thresholds[index]),negative_similarity=negative,
            margin=float(scores[index]-negative),required_margin=self.margin)
    def infer(self,mel):
        started=time.monotonic();self.last_reference=None
        embedding,probs=self.base.encode(mel)
        result=self.base.match(embedding);result['piano_support']=self.evidence(embedding)
        result['cnn_and_reference_ms']=(time.monotonic()-started)*1000
        self.last_reference=result
        return int(probs.argmax()),probs

def apply_piano_support(result,enabled=True):
    evidence=result.get('piano_support')
    if not enabled or not isinstance(evidence,dict):return result
    out=dict(result);out['piano_support']=dict(evidence)
    if evidence.get('eligible') and out.get('label') in ('guitar','violin'):
        out['label']='piano';out['confidence']=None
        out['decision_source']='audio_piano_support'
        out['piano_support'].update(applied=True,reason='learned_piano_support')
    return out


ModelCancelled=ReceiverCancelled
class ModelReceiver(PacketReceiver):
    def __init__(self,mmio,allocator,timeout=3.):
        super().__init__(mmio,allocator,522,transport_timeout=timeout)
        self.assembler=BatchAssembler();self.arm()
    def receive_batch(self):
        while True:
            frame=decode_frame(self.receive())
            batch=self.assembler.push(frame)
            if batch is not None:return batch

class BatchProvider:
    def __init__(self,stop):self.queue=queue.Queue(maxsize=1);self.stop=stop;self.current=None;self.dropped=0
    def put(self,batch):
        try:self.queue.put_nowait(batch)
        except queue.Full:
            try:self.queue.get_nowait();self.dropped+=1
            except queue.Empty:pass
            self.queue.put_nowait(batch)
    def receive_batch(self):
        while not self.stop.is_set():
            try:self.current=self.queue.get(timeout=.05);return self.current
            except queue.Empty:pass
        raise ReceiverCancelled('Inference stopped')

class ModelWorker:
    def __init__(self,receiver,session,analysis,provider):
        self.receiver,self.session,self.analysis,self.provider=receiver,session,analysis,provider
        self.recorder=None;self.piano_review=False;self.piano_support=True;self._last_review_log=None
        self.stop_event=provider.stop;self.capture_thread=None;self.inference_thread=None
        self.previous=None;self.start32=None;self.extended_start=None;self.epoch=analysis.session
    def start(self,started=None):
        def capture():
            try:
                if started is not None:
                    while not self.stop_event.is_set() and not started.wait(.02):pass
                while not self.stop_event.is_set():
                    try:batch=self.receiver.receive_batch()
                    except NoPacketYet:continue
                    segment=int(batch['segment']);start=int(batch['start'])
                    if self.previous is None:self.extended_start=start
                    else:
                        delta=(segment-self.previous)&0xffffffff
                        if not delta or delta&0x80000000 or ((start-self.start32)&0xffffffff)!=(delta*16000)&0xffffffff:
                            raise ValueError('Model stream reset or inconsistent timebase')
                        self.extended_start+=delta*16000
                    self.previous,self.start32=segment,start
                    batch.update(epoch=self.epoch,window_start=self.extended_start,window_end=self.extended_start+16000,
                        captured_monotonic=time.monotonic())
                    self.provider.put(batch)
            except ReceiverCancelled:pass
            except Exception as exc:
                self.analysis.model_failed('DMA1: '+str(exc));self.stop_event.set()
            finally:
                try:self.receiver.halt()
                except Exception as exc:self.analysis.model_failed('DMA1 halt: '+str(exc))
        def infer():
            try:
                while not self.stop_event.is_set():
                    result=review_instrument(apply_piano_support(self.session.next(),self.piano_support),self.piano_review);batch=self.provider.current
                    if self.piano_review or result.get('piano_support'):
                        key=(result.get('label'),result.get('cnn_label'),result.get('piano_support',{}).get('reason') if result.get('decision_source')=='audio_piano_support' else result.get('piano_review',{}).get('reason'))
                        if key!=self._last_review_log:
                            print('MODEL_REVIEW: label={} raw_cnn={} raw_confidence={} reason={}'.format(*key[:2],result.get('cnn_confidence'),key[2]),flush=True)
                            self._last_review_log=key
                    result.update(epoch=batch['epoch'],window_start=batch['window_start'],window_end=batch['window_end'],
                        capture_to_result_ms=(time.monotonic()-batch['captured_monotonic'])*1000,
                        inference_queue_drops=self.provider.dropped,time_quality='shared_start_nominal_not_calibrated')
                    if self.recorder is not None:
                        from instrument_capture import feature_diagnostics
                        features=self.session.base.last_features
                        result['diagnostics']=feature_diagnostics(features,result)
                        self.recorder.submit(features,result)
                        result['feature_capture']=self.recorder.status()
                    if not self.stop_event.is_set():self.analysis.update_model(result)
            except ReceiverCancelled:pass
            except Exception as exc:self.analysis.model_failed('Inference: '+str(exc));self.stop_event.set();self.receiver.request_stop()
        self.capture_thread=threading.Thread(target=capture,name='dma1_capture',daemon=True)
        self.inference_thread=threading.Thread(target=infer,name='model_inference',daemon=True)
        self.capture_thread.start();self.inference_thread.start()
    def request_stop(self):self.stop_event.set();self.receiver.request_stop()
    def join(self):
        for t in [self.capture_thread,self.inference_thread]:
            if t:
                t.join(timeout=5)
                if t.is_alive():raise RuntimeError(t.name+' has not stopped; retain resources')
    def close(self):
        self.request_stop();self.receiver.halt();self.join();self.receiver.release()

def create_model_worker(overlay,analysis,root):
    from pynq import MMIO,allocate
    from reference_infer import ReferenceSession
    desc=overlay.ip_dict['axi_dma_1'];params={k.lower():v for k,v in desc.get('parameters',{}).items()}
    if int(str(params.get('c_include_sg','0')),0):raise ValueError('Requires simple DMA1')
    receiver=ModelReceiver(MMIO(desc['phys_addr'],desc['addr_range']),allocate)
    provider=BatchProvider(threading.Event());root=Path(root)
    try:
        session=ReferenceSession(provider,str(root/'models'),str(root/'reference'))
        if session.model.meta.get('piano_support'):
            wrapped=AudioPianoReferenceModel(session.model,root/'reference')
            session.model=wrapped;session.base.model=wrapped
            print('AUDIO_PIANO_SUPPORT: loaded {} learned templates'.format(len(wrapped.prototypes)),flush=True)
    except Exception:receiver.close();raise
    return ModelWorker(receiver,session,analysis,provider)
