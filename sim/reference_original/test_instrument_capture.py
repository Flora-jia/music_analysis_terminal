"""Feature fidelity, bounded async IO, failure isolation and diagnostic export."""
from pathlib import Path
import hashlib,json,sys,tempfile,threading,time,unittest,zipfile
from types import SimpleNamespace
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'runtime'))
from instrument_capture import FeatureRecorder,feature_diagnostics
from summarize_capture import summarize,export_capture
from pl_fft import power_to_mel
from reference_infer import ReferenceSession

def wait_for(fn):
    deadline=time.monotonic()+3
    while not fn():
        if time.monotonic()>deadline:raise AssertionError('Timed out')
        time.sleep(.005)

def features(zero=False):
    p=np.zeros((513,63)) if zero else np.random.default_rng(42).uniform(0,5,(513,63))
    matrix=np.load(ROOT/'runtime/models/mel_matrix.npy')
    return dict(power=p,mel=power_to_mel(p,matrix),exponents=np.zeros(63,dtype='u1'))
def result(segment=0,pred='guitar',probs=None):
    probs=probs or dict(piano=.05,guitar=.9,violin=.05)
    return dict(segment=segment,label=pred,cnn_label=pred,cnn_probabilities=probs,probabilities=probs,
        rms_est=.1,gap=False,reference_label='piano',reference_similarity=.8,
        capture_to_result_ms=10.,inference_queue_drops=0,window_start=segment*16000,window_end=(segment+1)*16000)

class Tests(unittest.TestCase):
    def recorder(self,root,epoch='take1',**kwargs):
        rec=FeatureRecorder(root,epoch,'piano',**kwargs);self.addCleanup(rec.close);return rec
    def test_exact_features_and_operator_label_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            rec=self.recorder(folder);f=features();mel=f['mel'].copy();power=f['power'].copy()
            self.assertTrue(rec.submit(f,result()));f['mel'][:]=0;f['power'][:]=0
            rec.close();row=json.loads((rec.directory/'segments.jsonl').read_text())
            self.assertEqual(row['operator_label'],'piano');self.assertEqual(row['diagnostics']['top1'],'guitar')
            self.assertTrue(row['training_eligible_three_class'])
            with np.load(rec.directory/row['features_file'],allow_pickle=False) as z:
                np.testing.assert_array_equal(z['mel'],mel);np.testing.assert_array_equal(z['power'],power)
                np.testing.assert_array_equal(power_to_mel(z['power'],np.load(ROOT/'runtime/models/mel_matrix.npy')),z['mel'])
    def test_segment_and_byte_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            rec=self.recorder(folder,max_segments=1)
            self.assertTrue(rec.submit(features(),result()))
            self.assertFalse(rec.submit(features(),result(1)));rec.close()
            self.assertEqual(rec.status()['written'],1);self.assertEqual(rec.status()['skipped_limit'],1)
            rec2=self.recorder(folder,epoch='small',max_mb=1)
            for i in range(8):rec2.submit(features(),result(i))
            rec2.close();self.assertLessEqual(rec2.status()['reserved_bytes'],1024*1024)
    def test_full_queue_does_not_wait_and_close_drains(self):
        with tempfile.TemporaryDirectory() as folder:
            release=threading.Event();started=threading.Event()
            rec=self.recorder(folder,queue_size=1);original=rec._write
            def blocked(*args):started.set();release.wait(3);return original(*args)
            rec._write=blocked
            try:
                self.assertTrue(rec.submit(features(),result()));self.assertTrue(started.wait(1))
                self.assertTrue(rec.submit(features(),result(1)))
                begin=time.monotonic();self.assertFalse(rec.submit(features(),result(2)))
                self.assertLess(time.monotonic()-begin,.2);self.assertEqual(rec.status()['queue_dropped'],1)
            finally:release.set();rec.close()
            self.assertEqual(rec.status()['written'],2);self.assertEqual(rec.status()['pending'],0)
    def test_disk_failure_is_reported_without_raising_to_producer(self):
        with tempfile.TemporaryDirectory() as folder:
            rec=self.recorder(folder)
            def fail(*args):raise OSError('simulated disk full')
            rec._write=fail;self.assertTrue(rec.submit(features(),result()))
            wait_for(lambda:rec.status()['error'] is not None)
            self.assertFalse(rec.submit(features(),result(1)));rec.close()
            self.assertEqual(rec.status()['write_failed'],1)
            self.assertIn('disk full',rec.status()['error'])
    def test_silence_is_recorded_without_fake_probabilities(self):
        class Receiver:
            def receive_batch(self):
                return dict(segment=0,start=0,power=np.zeros((513,63)),dropped=0,exponents=np.zeros(63,dtype='u1'))
        session=ReferenceSession(Receiver(),ROOT/'runtime/models',ROOT/'runtime/reference')
        session.base.capture_features=True;r=session.next()
        self.assertEqual(r['label'],'silence');self.assertIsNone(r['cnn_probabilities'])
        with tempfile.TemporaryDirectory() as folder:
            rec=self.recorder(folder);self.assertTrue(rec.submit(session.base.last_features,r));rec.close()
            row=json.loads((rec.directory/'segments.jsonl').read_text())
            self.assertFalse(row['training_eligible_three_class']);self.assertIsNone(row['diagnostics']['top1'])
    def test_diagnostics_confusion_transition_and_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            matrix=ROOT/'runtime/models/mel_matrix.npy'
            rec=self.recorder(folder,metadata={'paired_artifacts':{'models/mel_matrix.npy':{'sha256':hashlib.sha256(matrix.read_bytes()).hexdigest()}}})
            for r in [result(),result(1,'piano',dict(piano=.36,guitar=.34,violin=.30)),result(4)]:
                self.assertTrue(rec.submit(features(),r))
            rec.close();report=summarize(rec.directory,True)
            self.assertEqual(report['verified_feature_files'],3);self.assertEqual(report['eligible_segments'],3)
            self.assertEqual(report['high_confidence_wrong_segments'],2);self.assertEqual(report['low_margin_segments'],1)
            self.assertEqual(report['adjacent_pairs'],1);self.assertEqual(report['label_transitions'],1)
            target=Path(folder)/'delivery.zip';export_capture(rec.directory,target)
            with zipfile.ZipFile(target) as z:self.assertIsNone(z.testzip());self.assertEqual(len(z.namelist()),7)
            path=rec.directory/'segment_000001.npz';path.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):summarize(rec.directory,True)
    def test_preprocessing_mismatch_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            matrix=ROOT/'runtime/models/mel_matrix.npy'
            rec=self.recorder(folder,metadata={'paired_artifacts':{'models/mel_matrix.npy':{'sha256':hashlib.sha256(matrix.read_bytes()).hexdigest()}}})
            f=features();f['mel'][:]=.1;rec.submit(f,result());rec.close()
            with self.assertRaisesRegex(ValueError,'Saved Mel differs'):summarize(rec.directory,True)
    def test_capture_does_not_change_real_model_decision(self):
        f=features()
        class R:
            def receive_batch(self):return dict(power=f['power'],segment=0,start=0,dropped=0,exponents=f['exponents'])
        session=ReferenceSession(R(),ROOT/'runtime/models',ROOT/'runtime/reference')
        original=session.next();self.assertIsNone(session.base.last_features)
        session.base.capture_features=True;recorded=session.next()
        self.assertEqual(original['cnn_probabilities'],recorded['cnn_probabilities'])
        self.assertEqual(original['reference_label'],recorded['reference_label'])
        np.testing.assert_array_equal(session.base.last_features['mel'],f['mel'])
    def test_worker_recording_failure_does_not_stop_inference(self):
        from model_stream import ModelWorker,BatchProvider
        from dma_transport import ReceiverCancelled
        provider=BatchProvider(threading.Event());received=[]
        class R:
            def __init__(self):self.i=0
            def receive_batch(self):
                if provider.stop.is_set():raise ReceiverCancelled()
                time.sleep(.01);i=self.i;self.i+=1
                return dict(segment=i,start=i*16000,power=np.zeros((513,63)),dropped=0,exponents=np.zeros(63,dtype='u1'))
            def halt(self):pass
            def request_stop(self):provider.stop.set()
        class Session:
            def __init__(self):self.base=SimpleNamespace(last_features=features())
            def next(self):
                b=provider.receive_batch();return result(b['segment'])
        analysis=SimpleNamespace(session='worker',update_model=received.append,model_failed=lambda e:received.append(e))
        with tempfile.TemporaryDirectory() as folder:
            rec=self.recorder(folder);rec._write=lambda *args:(_ for _ in ()).throw(OSError('disk unavailable'))
            worker=ModelWorker(R(),Session(),analysis,provider);worker.recorder=rec
            worker.start()
            try:wait_for(lambda:len(received)>=3)
            finally:worker.request_stop();worker.join();rec.close()
            self.assertFalse(any(isinstance(x,str) for x in received))
            self.assertTrue(any(x['feature_capture']['error'] for x in received))
    def test_invalid_labels_epochs_and_bad_features(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):FeatureRecorder(folder,'../escape','piano')
            with self.assertRaises(ValueError):FeatureRecorder(folder,'bad','automatic_prediction')
            rec=self.recorder(folder);f=features();f['mel'][0,0]=np.nan
            self.assertFalse(rec.submit(f,result()));rec.close();self.assertIsNotNone(rec.status()['error'])

if __name__=='__main__':unittest.main(verbosity=2)
