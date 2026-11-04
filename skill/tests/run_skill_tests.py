"""Independent fixtures and fault injection for reusable skill helpers.
No hardware is loaded; tests distinguish accepted/rejected inputs explicitly.
"""
from pathlib import Path
import argparse,copy,hashlib,importlib.util,json,shutil,sys,tempfile,unittest
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
overlay=load('overlay','pynq-portable-bringup/scripts/inspect_overlay.py')
dma=load('dma','pynq-portable-bringup/assets/simple_s2mm_session.py')
frames=load('frames','axis-frame-validation/scripts/check_frames.py')
features=load('features','dsp-feature-alignment/scripts/check_features.py')
build=load('build','build-evidence-review/scripts/audit_build.py')

class Buffer:
    def __init__(self,n):self.physical_address=0x100001000;self.data=list(range(n));self.freed=False;self.flushed=False;self.invalidated=False
    def flush(self):self.flushed=True
    def invalidate(self):self.invalidated=True
    def copy(self):return self.data[:]
    def freebuffer(self):self.freed=True
class MMIO:
    def __init__(self,sg=False,stuck=False,error=False,short=False):
        self.regs={0x30:0,0x34:1|(8 if sg else 0)};self.trace=[];self.stuck=stuck;self.error=error;self.short=short
    def read(self,o):return self.regs.get(o,0)
    def write(self,o,v):
        self.trace.append((o,v));self.regs[o]=v
        if o==0x30:
            if v&4:self.regs[o]=0;self.regs[0x34]=1
            elif v&1:self.regs[0x34]=0
            else:self.regs[0x34]=0 if self.stuck else 1
        elif o==0x34:self.regs[o]=0
        elif o==0x58:self.regs[0x34]=0x10 if self.error else 0x1002;self.regs[o]=v-4 if self.short else v

def session(mmio=None,stop=None):
    io=mmio or MMIO();created=[]
    def alloc(shape,dtype):b=Buffer(shape[0]);created.append(b);return b
    def start():
        # Completion may already have changed readable BTT; assert the submitted descriptor.
        assert (0x58,16) in io.trace and io.regs[0x30]&1
        assert created[0].flushed
    s=dma.SimpleS2MMSession(io,alloc,4,start,stop or (lambda:None),timeout=.002)
    return s,io,created

def packets():
    return [{'sequence':i,'first_sample':i*2,'sample_count':8,'bins':[0,1,2,3,4],
             'values':[0,1,9,2,0],'reference_peak':{'bin':2,'value':9}} for i in range(3)]
CONTRACT={'bins':5,'window_samples':8,'hop_samples':2,'reference_peak':{'first_bin':1,'last_bin':3,'threshold':1}}
TIMING='''checking no_clock (0)
checking unconstrained_internal_endpoints (0)
checking no_input_delay (0)
checking no_output_delay (0)
checking partial_input_delay (0)
checking partial_output_delay (0)
WNS(ns) TNS(ns) TNS Failing Endpoints TNS Total Endpoints WHS(ns) THS(ns) THS Failing Endpoints THS Total Endpoints
------- ------- ---- ---- ------- ------- ---- ----
7.336 0.000 0 123 0.040 0.000 0 123
clk_test {0.000 5.000} 10.000 100.000
'''
class Checks(unittest.TestCase):
    def test_two_unrelated_overlay_maps(self):
        for instance,address in [('sensor_dma',0x81000000),('image_transfer',0xa0000000)]:
            with tempfile.TemporaryDirectory() as name:
                r=Path(name);(r/'payload.bin').write_bytes(b'fixture_only_not_a_bitstream')
                (r/'design.hwh').write_text('<ROOT><MEMRANGE MEMTYPE="REGISTER" INSTANCE="'+instance+'" BASEVALUE="'+hex(address)+'"/></ROOT>')
                spec={'hwh':'design.hwh','artifacts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in r.iterdir()},'expected_ips':{instance:hex(address)}}
                self.assertTrue(overlay.inspect(r,spec)['passed'])
    def test_hash_drift_rejected(self):
        r=ROOT/'pynq-portable-bringup/examples/offline_fixture';spec=json.loads((r/'spec.json').read_text());spec['artifacts']['payload.bin']='0'*64
        self.assertIn('hash_mismatch:payload.bin',overlay.inspect(r,spec)['errors'])
    def test_wrong_ip_address_rejected(self):
        r=ROOT/'pynq-portable-bringup/examples/offline_fixture';spec=json.loads((r/'spec.json').read_text());spec['expected_ips']['sensor_dma']='0x1000'
        self.assertFalse(overlay.inspect(r,spec)['passed'])
    def test_escape_path_rejected(self):
        with self.assertRaises(ValueError):overlay.safe_path(ROOT,'../outside.bin')
    def test_dma_descriptor_before_producer_and_cache(self):
        s,io,b=session();s.arm();self.assertEqual(io.regs[0x4c],1);self.assertEqual(s.receive_copy(),[0,1,2,3]);self.assertTrue(b[0].invalidated)
        s.close();self.assertTrue(b[0].freed);self.assertEqual(s.state,'CLOSED')
    def test_dma_stuck_halt_retains_buffer(self):
        s,io,b=session(MMIO(stuck=True));s.arm()
        with self.assertRaises(dma.UnsafeStop):s.close()
        self.assertFalse(b[0].freed);self.assertIsNotNone(s.buffer);self.assertEqual(s.state,'QUARANTINED')
    def test_producer_stop_failure_retains_buffer(self):
        def fail():raise RuntimeError('producer still active')
        s,io,b=session(stop=fail);s.arm()
        with self.assertRaises(dma.UnsafeStop):s.close()
        self.assertFalse(b[0].freed)
    def test_sg_requires_different_adapter(self):
        s,io,b=session(MMIO(sg=True))
        with self.assertRaises(ValueError):s.arm()
        self.assertEqual(b,[])
    def test_dma_error_rejected(self):
        s,io,b=session(MMIO(error=True));s.arm()
        with self.assertRaises(RuntimeError):s.receive_copy()
        s.close()
    def test_short_packet_rejected(self):
        s,io,b=session(MMIO(short=True));s.arm()
        with self.assertRaises(ValueError):s.receive_copy()
        s.close()
    def test_complete_frames(self):self.assertTrue(frames.check(packets(),CONTRACT)['passed'])
    def test_whole_frame_gap_marked(self):
        f=packets();f[2].update(sequence=4,first_sample=8,whole_frame_drop=True)
        r=frames.check(f,CONTRACT);self.assertTrue(r['passed']);self.assertEqual(r['gaps'][0]['missing_sequences'],2)
    def test_unmarked_gap_rejected(self):
        f=packets();f[2].update(sequence=4,first_sample=8);self.assertFalse(frames.check(f,CONTRACT)['passed'])
    def test_bin_reorder_and_short_rejected(self):
        for bins in [[0,2,1,3,4],[0,1,2,3]]:
            f=packets();f[0]['bins']=bins;self.assertFalse(frames.check(f,CONTRACT)['passed'])
    def test_inconsistent_hop_rejected(self):
        f=packets();f[1]['first_sample']=7;self.assertFalse(frames.check(f,CONTRACT)['passed'])
    def test_nonfinite_magnitude_rejected(self):
        f=packets();f[1]['values'][0]=float('nan');self.assertFalse(frames.check(f,CONTRACT)['passed'])
    def test_same_frame_reference_peak_rejected(self):
        f=packets();f[1]['reference_peak']['value']=8;self.assertFalse(frames.check(f,CONTRACT)['passed'])
    def test_mixed_payload_detected_with_golden(self):
        f=packets();f[1]['golden_values']=f[1]['values'][:];f[1]['values'][0]=99
        self.assertIn('record1:golden_payload_mismatch',frames.check(f,CONTRACT)['errors'])
    def test_sampled_log_does_not_claim_dma_loss(self):
        f=packets();f[2].update(sequence=4,first_sample=8);c=dict(CONTRACT,coverage='sampled')
        self.assertTrue(frames.check(f,c)['passed']);self.assertEqual(frames.check(f,c)['gaps'][0]['coverage'],'sampled')
    def test_unsigned_bfp_and_format_rejection(self):
        p=np.array([[0x80000000]],dtype='u4');self.assertEqual(features.restore_bfp(p,np.array([3]),15)[0,0],128)
        with self.assertRaises(ValueError):features.restore_bfp(p.view('i4'),np.array([3]),15)
    def test_wrong_exponent_numerically_detected(self):
        p=np.array([[9]],dtype='u4');a=features.restore_bfp(p,np.array([1]),15);b=features.restore_bfp(p,np.array([2]),15)
        self.assertFalse(features.compare(a,b,0,0)['passed'])
    def test_global_mel_reference_and_silence(self):
        p=np.array([[1.,100.],[.01,.1]]);m=np.eye(2);db=10*np.log10(p);expected=np.clip((db-db.max()+80)/80,0,1).astype('f4')
        np.testing.assert_array_equal(features.logmel(p,m),expected)
        # Documented trap: segment-max normalization alone is NOT a silence detector.
        self.assertTrue(np.all(features.logmel(np.zeros((2,2)),m)==1))
    def test_shape_nan_and_tolerance(self):
        self.assertFalse(features.compare(np.ones(2),np.ones(3),0,0)['passed'])
        self.assertFalse(features.compare(np.array([np.nan]),np.ones(1),0,0)['passed'])
        self.assertTrue(features.compare(np.array([1.0001]),np.ones(1),.001,0)['passed'])
    def test_complex_reference_preserves_phase_difference(self):
        self.assertFalse(features.compare(np.array([1+2j]),np.array([1+3j]),0,0)['passed'])
    def test_positive_timing_complete_constraints(self):
        with tempfile.TemporaryDirectory() as n:
            r=Path(n);(r/'timing.rpt').write_text(TIMING);spec={'timing_report':'timing.rpt','files':{'timing.rpt':hashlib.sha256((r/'timing.rpt').read_bytes()).hexdigest()}}
            self.assertTrue(build.audit(r,spec)['passed'])
            spec['files']['timing.rpt']='0'*64
            self.assertIn('receipt_mismatch:timing.rpt',build.audit(r,spec)['errors'])
    def test_positive_slack_missing_io_is_not_full_pass(self):
        with tempfile.TemporaryDirectory() as n:
            r=Path(n);(r/'timing.rpt').write_text(TIMING.replace('no_input_delay (0)','no_input_delay (3)'))
            spec={'timing_report':'timing.rpt','files':{'timing.rpt':hashlib.sha256((r/'timing.rpt').read_bytes()).hexdigest()}}
            a=build.audit(r,spec);self.assertFalse(a['passed']);self.assertEqual(a['timing']['wns_ns'],7.336)
    def test_negative_hold_rejected(self):
        with tempfile.TemporaryDirectory() as n:
            r=Path(n);(r/'timing.rpt').write_text(TIMING.replace('0.040','-0.001'))
            spec={'timing_report':'timing.rpt','files':{'timing.rpt':hashlib.sha256((r/'timing.rpt').read_bytes()).hexdigest()}}
            self.assertIn('constrained_timing_failed',build.audit(r,spec)['errors'])
    def test_timing_unknown_format_fails_closed(self):
        with self.assertRaises(ValueError):build.timing_metrics('All timing constraints are met')

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a new output directory')
    a.out.mkdir(parents=True);temp=a.out.resolve()/'temp';temp.mkdir();tempfile.tempdir=str(temp)
    with (a.out/'tests.log').open('w',encoding='utf-8') as f:r=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    summary={'tests':r.testsRun,'failures':len(r.failures),'errors':len(r.errors),'successful':r.wasSuccessful(),
             'scope':'offline fixtures, injected failures and mocked MMIO only; no new physical PYNQ board execution'}
    (a.out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
    if not r.wasSuccessful():print((a.out/'tests.log').read_text());raise SystemExit(1)
if __name__=='__main__':main()
