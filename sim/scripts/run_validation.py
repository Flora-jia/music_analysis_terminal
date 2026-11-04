"""Package integration checks using real frozen Python/C; no physical hardware.
The fake AXI packets here test protocol/algorithms, not ADC or vendor FFT math.
"""
from pathlib import Path
import argparse,ast,ctypes,hashlib,importlib.util,json,math,sys,unittest,os
ROOT=Path(__file__).resolve().parents[2]
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
sys.dont_write_bytecode=True
sys.path.insert(0,str(ROOT/'board/runtime'))
import numpy as np
import pl_fft
from infer_numpy import NumpyInstrumentClassifier,mel_spectrogram_np
from spectrum_audio import decode_packet,SpectrumAnalysis,spectrum_bars
from dsp.note_engine import NoteEngine

def spectrum(f=440):
    t=np.arange(4096)/16000;w=.5-.5*np.cos(2*np.pi*np.arange(4096)/4096)
    x=sum(np.sin(2*np.pi*f*h*t)/h for h in (1,2,3,4) if f*h<7900)
    m=np.abs(np.fft.rfft(x*w));return np.round(m/m.max()*10000).astype('u2')
def packet(seq,mag):
    m=np.asarray(mag,dtype='u2');best=k=0
    for j in range(13,513):
        if m[j]>=100 and m[j]>best and m[j]>=m[j-1] and m[j]>m[j+1]:k,best=j,int(m[j])
    first=seq*512
    h=[0x53504543,0x20040,8260,seq,first&0xffffffff,first>>32,16000,0x02001000,0x10801,0x11557,0,0,
       (k<<16)|best,0 if best==0 else (int(m[k-1])<<16)|int(m[k+1]),0,4096]
    return np.r_[np.array(h,dtype='u4'),(np.arange(2049,dtype='u4')<<16)|m]
def model_packet(i,segment=1):return np.array([pl_fft.MAGIC,segment,i,16000,0,513,1,0,3]+list(range(513)),dtype='u4')

class Checks(unittest.TestCase):
    def test_runtime_manifest(self):
        from run_live_system import verify_bit_pair
        self.assertEqual(verify_bit_pair(ROOT/'board/runtime/audio_merged.bit')['software_release'],'20261101-R6')
    def test_source_mirrors(self):
        for p in (ROOT/'src/ps/pynq').rglob('*.py'):
            self.assertEqual(p.read_bytes(),(ROOT/'board/runtime'/p.relative_to(ROOT/'src/ps/pynq')).read_bytes())
    def test_python_syntax(self):
        for p in (ROOT/'board/runtime').rglob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
    def test_saved_rtl_spectra_and_corruption(self):
        w=np.array([int(x,16) for x in (ROOT/'sim/fixtures/spectrum_packets.hex').read_text().split()],dtype='u4')
        self.assertEqual([decode_packet(w[i*2065:(i+1)*2065])['sequence'] for i in range(3)],[0,1,3])
        bad=w[:2065].copy();bad[116]^=0x10000
        with self.assertRaises(ValueError):decode_packet(bad)
    def test_nyquist_visualization(self):
        m=np.zeros(2049);m[-1]=60000
        self.assertEqual(spectrum_bars(m,64)[1][-1],60000)
    def test_bfp_unsigned(self):
        self.assertEqual(pl_fft.restore_power(np.array([0x80000000],dtype='u4'),3)[0],128.)
        self.assertEqual(pl_fft.restore_power([123],5)[0]/pl_fft.restore_power([123],2)[0],64)
    def test_model_complete_batch(self):
        a=pl_fft.BatchAssembler();result=None
        for i in range(63):result=a.push(pl_fft.decode_frame(model_packet(i)))
        self.assertEqual(result['power'].shape,(513,63));self.assertEqual(result['segment'],1)
    def test_model_rejects_splice(self):
        a=pl_fft.BatchAssembler();a.push(pl_fft.decode_frame(model_packet(0)))
        with self.assertRaises(pl_fft.ProtocolError):a.push(pl_fft.decode_frame(model_packet(1,2)))
        self.assertEqual(a.frames,[])
    def test_mel_against_pcm_reference(self):
        y=np.sin(2*np.pi*440*np.arange(16000)/16000).astype('f4')*.1
        w=.5-.5*np.cos(2*np.pi*np.arange(1024)/1024);frames=np.lib.stride_tricks.sliding_window_view(np.pad(y,512),1024)[::256]*w
        p=np.abs(np.fft.rfft(frames,axis=1)).T**2
        matrix=np.load(ROOT/'board/runtime/models/mel_matrix.npy')
        np.testing.assert_allclose(pl_fft.power_to_mel(p,matrix),mel_spectrogram_np(y,matrix),atol=1e-6)
    def test_cnn_is_three_conv_and_finite(self):
        clf=NumpyInstrumentClassifier(ROOT/'board/runtime/models/cnn_weights.npz',ROOT/'board/runtime/models/model_meta.json')
        self.assertEqual(len([k for k in clf.w if k.startswith('conv') and k.endswith('_w')]),3)
        i,p=clf.infer(np.zeros((64,63),dtype='f4'));self.assertEqual(p.shape,(3,));self.assertTrue(np.isfinite(p).all());self.assertAlmostEqual(float(p.sum()),1,places=5)
    def test_native_octaves_and_silence(self):
        for f,midi in [(82.4069,40),(110,45),(440,69),(659.255,76),(880,81)]:
            a=SpectrumAnalysis()
            try:
                for j in range(8):a.feed(packet(j,spectrum(f)))
                self.assertIsNotNone(a.current);self.assertEqual(a.current['midi'],midi)
                for j in range(8,16):a.feed(packet(j,np.zeros(2049,dtype='u2')))
                self.assertIsNone(a.current);self.assertTrue(a.notes)
            finally:a.close_engine()
    def test_native_gap_marks_truncation(self):
        a=SpectrumAnalysis()
        try:
            for j in range(8):a.feed(packet(j,spectrum()))
            a.feed(packet(12,spectrum()));self.assertEqual(a.missing_frames,4)
            self.assertTrue(a.notes[-1]['truncated'])
        finally:a.close_engine()

def main():
    p=argparse.ArgumentParser();p.add_argument('--native-lib',type=Path);p.add_argument('--out',type=Path,default=ROOT/'sim/results/release_validation_20261102');a=p.parse_args()
    if a.out.exists():raise SystemExit('Use a NEW --out directory')
    a.out.mkdir(parents=True)
    import tempfile
    local_temp=a.out.resolve()/'temp';local_temp.mkdir()
    tempfile.tempdir=str(local_temp)
    lib=a.native_lib or ROOT/'sim/fixtures/libmusic_ps_host.dll'
    original_init=NoteEngine.__init__
    def init(self,lib_path=None,*args,**kwargs):return original_init(self,lib_path or lib.resolve(),*args,**kwargs)
    NoteEngine.__init__=init
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    # Existing recorder checks are relocated without changing their assertions.
    text=(ROOT/'sim/reference_original/test_instrument_capture.py').read_text(encoding='utf-8')
    text=text.replace("ROOT=Path(__file__).resolve().parents[1]",'ROOT=Path('+repr(str(ROOT))+')').replace("ROOT/'runtime","ROOT/'board/runtime")
    import types
    module=types.ModuleType('capture_release_checks');module.__file__=str(ROOT/'sim/reference_original/test_instrument_capture.py')
    exec(compile(text,module.__file__,'exec'),module.__dict__)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
    with (a.out/'tests.log').open('w',encoding='utf-8') as stream:result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    data={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'successful':result.wasSuccessful(),
          'native_lib_sha256':hashlib.sha256(lib.read_bytes()).hexdigest(),'scope':'PC real C/Python with generated/recorded protocol data; no board, ADC, LCD or vendor FFT arithmetic assertion'}
    (a.out/'summary.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data))
    if not result.wasSuccessful():print((a.out/'tests.log').read_text());raise SystemExit(1)
if __name__=='__main__':main()
