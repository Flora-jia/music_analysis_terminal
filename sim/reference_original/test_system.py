"""Actual rebuilt C engine + register/owner mocks. No physical-board claims."""
from pathlib import Path
import ctypes,hashlib,json,math,sys,tempfile,threading,time,unittest,subprocess
from types import SimpleNamespace
from urllib.request import urlopen
from urllib.error import HTTPError
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
PC=ROOT/'pc_uart_viewer'
if not PC.is_dir():PC=ROOT.parents[2]/'pc_uart_viewer'
sys.path[:0]=[str(ROOT/'runtime'),str(PC)]
try:import flask
except ImportError:sys.path.append(str(PC/'.venv/Lib/site-packages'))
from dsp.note_engine import NoteEngine,layout
from spectrum_audio import SpectrumAnalysis,SpectrumReceiver,decode_packet,spectrum_bars
from dma_transport import PacketReceiver,NoPacketYet,ReceiverCancelled,DMAFault
from model_stream import ModelWorker,BatchProvider
from system_runtime import MusicSystem,StopFailed
from live_service import AudioService,CaptureWorker
from pynq_bridge import RoutedState,InputReader,validate_snapshot
from app import StreamState,SerialReader,create_app

class Clock:
    def __init__(self):self.now=10.
    def __call__(self):return self.now

def magnitude(f=500.,scale=10000):
    t=np.arange(4096)/16000.;w=.5-.5*np.cos(2*np.pi*np.arange(4096)/4096)
    y=sum(np.sin(2*np.pi*f*h*t)/h for h in [1,2,3,4] if f*h<7900)
    m=np.abs(np.fft.rfft(y*w));return np.round(m/max(m.max(),1e-12)*scale).astype('u2')

def packet(seq=0,mag=None):
    m=magnitude() if mag is None else np.asarray(mag,dtype='u2');best=k=0
    for j in range(13,513):
        if m[j]>=100 and m[j]>best and m[j]>=m[j-1] and m[j]>m[j+1]:k,best=j,int(m[j])
    first=seq*512;header=[0x53504543,0x20040,8260,seq,first&0xffffffff,first>>32,16000,0x02001000,0x10801,0x11557,0,0,
        (k<<16)|best,0 if not best else (int(m[k-1])<<16)|int(m[k+1]),0,4096]
    return np.r_[np.array(header,dtype='u4'),(np.arange(2049,dtype='u4')<<16)|m]

class Buffer(np.ndarray):
    next_address=0x10000000
    def __new__(cls,shape=(2080,),dtype='u4'):
        x=np.zeros(shape,dtype=dtype).view(cls);x.physical_address=cls.next_address;cls.next_address+=0x4000
        x.freed=False;x.events=[];return x
    def flush(self):self.events.append('flush')
    def invalidate(self):self.events.append('invalidate')
    def freebuffer(self):self.freed=True

class DMA:
    def __init__(self,packets=(),error=0):
        self.buffers={};self.packets=list(packets);self.error=error;self.regs={0x30:0,0x34:1};self.trace=[];self.issued=0
    def allocate(self,**kwargs):
        b=Buffer(**kwargs);self.buffers[b.physical_address]=b;return b
    def read(self,o):self.trace.append(('r',o));return self.regs.get(o,0)
    def write(self,o,v):
        self.trace.append(('w',o,v))
        if o==0x30:self.regs[o]=0 if v&4 else v;self.regs[0x34]=1 if v&4 or not v&1 else 0
        elif o==0x34:self.regs[o]=self.regs.get(o,0)&~v
        elif o==0x58:
            self.issued+=1;self.regs[o]=v
            if self.packets:
                data=self.packets.pop(0);b=self.buffers[self.regs[0x48]];b[:len(data)]=data
                self.regs[o]=len(data)*4;self.regs[0x34]=self.error or 0x1002
            elif self.error:self.regs[0x34]=self.error
        else:self.regs[o]=v

def receiver(d):return PacketReceiver(d,d.allocate,2065)

class Tests(unittest.TestCase):
    counter=100
    def analysis(self,clock=None):
        Tests.counter+=1;e=NoteEngine(session_id=Tests.counter,clock=clock or time.monotonic)
        a=SpectrumAnalysis(engine=e,clock=clock or time.monotonic);self.addCleanup(a.close_engine);return a
    def tone(self,a,n=6,start=0):
        for i in range(start,start+n):a.feed(packet(i))
    def test_abi_queries_and_real_c_exact_note(self):
        a=self.analysis();self.tone(a)
        self.assertEqual(a.current['midi'],71);self.assertLess(abs(a.current['freq']-500),.5)
        for i in range(6,11):a.feed(packet(i,np.zeros(2049)))
        off=a.snapshot()['score'][0];self.assertEqual(off['duration_ms'],192.)
        self.assertEqual(off['native_schema'],1);self.assertEqual(off['flags'],0);self.assertEqual(off['fs_hz'],16000)
        self.assertIsInstance(off['decision_sample'],int);self.assertEqual(off['session_id'],a.engine.session_id)
        for i,(name,info) in enumerate(layout().items(),1):self.assertEqual(a.engine.native._lib.mp_sizeof(i),info['size'])
    def test_real_c_440_and_880_octaves(self):
        a=self.analysis()
        for f,midi in [(440,69),(880,81)]:
            base=0 if a.last_sequence is None else a.last_sequence+1
            for i in range(base,base+6):a.feed(packet(i,magnitude(f)))
            self.assertEqual(a.current['midi'],midi)
    def test_bad_packet_drains_off_immediately(self):
        a=self.analysis();self.tone(a)
        bad=packet(6);bad[10]=1
        with self.assertRaises(ValueError):a.feed(bad)
        self.assertIsNone(a.current);self.assertTrue(a.notes[-1]['truncated']);self.assertEqual(a.notes[-1]['reason'],5)
        self.assertEqual(a.native_summary['bad_packet_count'],1)
    def test_real_c_watchdog_uses_trusted_samples(self):
        c=Clock();a=self.analysis(c);self.tone(a);last=a.current['feature_sample']
        c.now+=.127;a.poll_watchdog();self.assertFalse(a.notes)
        c.now+=.002;a.poll_watchdog();self.assertEqual(a.notes[-1]['end_sample'],last+512)
        self.assertEqual(a.notes[-1]['reason'],6);self.assertEqual(a.notes[-1]['time_quality'],2)
        self.assertIsNone(a.current);before=len(a.events);a.poll_watchdog();self.assertEqual(len(a.events),before)
    def test_gap_repetition_and_sample_progression(self):
        a=self.analysis();self.tone(a)
        a.feed(packet(9));self.assertEqual(a.missing_frames,3);self.assertTrue(a.notes[-1]['truncated'])
        for i in range(10,15):a.feed(packet(i))
        self.assertNotEqual(a.current['id'],a.notes[-1]['id'])
        for i in range(15,18):a.feed(packet(i,np.zeros(2049)))
        for i in range(18,24):a.feed(packet(i))
        self.assertEqual(len({n['id'] for n in a.notes}),len(a.notes))
    def test_reset_rejects_undelivered_c_queue_then_delivers_old_session(self):
        a=self.analysis();e=a.engine;old=e.session_id
        for i in range(6):e.native.process(magnitude(),i*512,i)
        self.assertEqual(e.native._lib.mp_reset_checked(old+1000),-2)
        output=e.reset(old+1000);notes=[x for x in output['events'] if x['type'] in (1,2)]
        self.assertEqual([x['type'] for x in notes],[1,2]);self.assertTrue(all(x['session_id']==old for x in notes))
        self.assertEqual(e.native.drain_events(),[])
        with self.assertRaises(ValueError):e.reset(old)
    def test_native_queue_overflow_visible_and_resync(self):
        a=self.analysis();e=a.engine
        for block in range(45):
            for j in range(5):
                i=block*5+j;e.native.process(magnitude() if j<2 else np.zeros(2049,dtype='u2'),i*512,i)
        result=e.stop();self.assertGreater(result['summary']['event_overflow'],0)
        self.assertTrue(any(x['type']==4 for x in result['events']) or any(x.get('flags',0)&1 for x in result['events']))
    def test_native_silent_calibration(self):
        a=self.analysis();self.tone(a);a.calibrate();self.assertTrue(a.notes[-1]['truncated'])
        for i in range(6,24):a.feed(packet(i,np.zeros(2049)))
        self.assertTrue(a.snapshot()['segmentation']['calibrated'])
    def test_original_rtl_packets_and_reject_pcm(self):
        words=np.array([int(x,16) for x in (ROOT/'tests/fixtures/spectrum_packets.hex').read_text().split()],dtype='u4')
        self.assertEqual([decode_packet(words[i*2065:(i+1)*2065])['sequence'] for i in range(3)],[0,1,3])
        with self.assertRaises(ValueError):decode_packet(np.zeros(528,dtype='u4'))
    def test_nyquist_bar_and_validation(self):
        m=np.zeros(2049);m[-1]=60000;f,b=spectrum_bars(m);self.assertEqual(b[-1],60000)
        self.assertEqual(len(f),128);self.assertTrue(all(x<y for x,y in zip(f,f[1:])))
        for count in [True,0,2049.1,2050]:
            with self.assertRaises(ValueError):spectrum_bars(m,count)
        m[3]=np.nan
        with self.assertRaises(ValueError):spectrum_bars(m)
    def test_dma_rs_start_and_length_before_rearm(self):
        d=DMA([packet(),packet(1)]);r=receiver(d);self.addCleanup(r.close)
        self.assertEqual(decode_packet(r.receive())['sequence'],0)
        reads=[i for i,x in enumerate(d.trace) if x==('r',0x58)]
        writes=[i for i,x in enumerate(d.trace) if x==('w',0x58,8260)]
        self.assertTrue(any(x==('w',0x30,1) for x in d.trace[:writes[0]]));self.assertLess(reads[0],writes[1])
        self.assertEqual(decode_packet(r.receive())['sequence'],1)
        self.assertEqual(len({b.physical_address for b in r.buffers}),2)
    def test_dma_short_with_stale_tail_never_reaches_c(self):
        a=self.analysis();d=DMA([packet()[:16]]);r=receiver(d);self.addCleanup(r.close)
        for b in r.buffers:b[:2065]=packet(0,np.zeros(2049))
        with self.assertRaises(DMAFault):a.feed(r.receive())
        self.assertEqual(a.frames,0);self.assertEqual(d.issued,1)
        self.assertTrue(any(x==('r',0x58) for x in d.trace))
    def test_poll_cancel_error_and_retained_memory(self):
        d=DMA();r=receiver(d);r.arm()
        with self.assertRaises(NoPacketYet):r.receive(timeout=.001)
        self.assertFalse(r.failed)
        with self.assertRaises(DMAFault):r.release()
        self.assertTrue(all(not b.freed for b in r.buffers))
        r.request_stop()
        with self.assertRaises(ReceiverCancelled):r.receive()
        r.close();self.assertTrue(all(b.freed for b in r.buffers))
        d=DMA(error=0x10);r=receiver(d)
        try:
            with self.assertRaises(DMAFault):r.receive()
            with self.assertRaises(DMAFault):r.receive()
        finally:r.close()
    def test_model_window_association_epoch_and_stale(self):
        c=Clock();a=self.analysis(c);a.mark_capture_started();self.tone(a)
        result=dict(label='piano',cnn_label='piano',confidence=.8,cnn_confidence=.8,reference_label='guitar',reference_similarity=.9,
                    epoch=a.session,segment=0,window_start=0,window_end=16000,dropped=0)
        a.update_model(result)
        for i in range(6,9):a.feed(packet(i,np.zeros(2049)))
        self.assertEqual(a.notes[-1]['instrument_matches'][0]['reference_label'],'guitar')
        with self.assertRaises(ValueError):a.update_model(dict(result,epoch='wrong'))
        c.now+=6;self.assertFalse(a.snapshot()['instrument_ready']);self.assertIsNone(a.snapshot()['instrument']['label'])
    def test_http_pc_calibration_and_raw_duration(self):
        c=Clock();a=self.analysis(c);self.tone(a)
        for i in range(6,9):a.feed(packet(i,np.zeros(2049)))
        service=AudioService(a,host='127.0.0.1',port=0);service.start()
        url='http://127.0.0.1:'+str(service.server.server_address[1]);state=RoutedState(StreamState(),clock=c);reader=InputReader(state,SerialReader)
        try:
            reader.connect_board(url);end=time.monotonic()+2
            while state.remote is None and time.monotonic()<end:time.sleep(.01)
            self.assertIsNotNone(state.remote);client=create_app(state,reader).test_client();value=client.get('/api/state').get_json()
            self.assertEqual(value['score'][0]['duration_ms'],192.);self.assertEqual(value['pitch_backend'],'libmusic_ps 2.0.0')
            self.assertEqual(client.get('/api/pcm').status_code,410)
            self.assertEqual(client.post('/api/calibration/start').status_code,200)
            self.assertEqual(client.post('/api/score/clear').status_code,200);self.assertFalse(a.notes)
            validate_snapshot(a.snapshot())
            (ROOT/'tests/fixtures/state.json').write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        finally:reader.disconnect();service.close()
    def test_ui_receives_off_when_not_fresh_and_preserves_raw(self):
        from live_dashboard import LiveDashboardUI
        from PIL import Image
        a=self.analysis();self.tone(a)
        class LCD:
            running=True;frame=Buffer(shape=(480,800,3),dtype='u1');overlay=object()
        class Speaker:
            prepared=True;overlay=LCD.overlay
            def stop(self):pass
            def configure(self,**kw):pass
            def poll(self):return dict(clock_ok=True,watchdog_fault=False,fast_clock_fault=False,beat_index=0,beat_count=0)
        ui=LiveDashboardUI(LCD(),SimpleNamespace(read_points=lambda:[]),Speaker(),a)
        ui.step(time.monotonic(),[]);a.stop('test_shutdown')
        ui.step(time.monotonic()+.2,[]);ui._drain(time.monotonic()+.2)
        self.assertEqual(len(ui.records),1);raw=next(iter(ui.raw_note_records.values()))
        self.assertEqual(raw['time_quality'],2);self.assertIn(str(a.engine.session_id),ui.records[0].note_id)
        with tempfile.TemporaryDirectory() as folder:
            result=ui.save_records(Path(folder)/'notes.json');saved=json.loads(Path(folder,'notes_raw.json').read_text())
            self.assertEqual(saved['notes'][0]['duration_ms'],192.)
        (ROOT/'reports/previews').mkdir(parents=True,exist_ok=True)
        for page in ['home','metronome','spectrum','notation']:
            ui.page=page;image=ui.render(time.monotonic());Image.fromarray(image[:,:,::-1]).save(ROOT/'reports/previews'/(page+'.png'))
    def test_c_input_range_jianpu_ui_octaves(self):
        from music_dashboard import Note
        a=self.analysis()
        for midi in [21,108]:
            j=a.engine.jianpu(midi);n=Note(j['degree'],octave=j['octave_offset']);self.assertIn(n.octave,[-4,4])
    def test_model_capture_continues_while_inference_blocked(self):
        a=self.analysis();provider=BatchProvider(threading.Event());release=threading.Event()
        class Rx:
            def __init__(self):self.count=0;self.armed=True
            def receive_batch(self):
                if provider.stop.is_set():raise ReceiverCancelled()
                time.sleep(.002);i=self.count;self.count+=1
                return dict(segment=i,start=i*16000,power=np.zeros((513,63)),dropped=0,exponents=np.zeros(63,dtype='u1'))
            def halt(self):pass
            def release(self):pass
            def request_stop(self):provider.stop.set()
        class Session:
            def next(self):
                b=provider.receive_batch();release.wait(1)
                return dict(label='silence',cnn_label='silence',confidence=None,cnn_confidence=None,reference_label='silence',reference_similarity=None,segment=b['segment'],dropped=0)
        rx=Rx();m=ModelWorker(rx,Session(),a,provider);m.start();time.sleep(.05)
        self.assertGreater(rx.count,3);self.assertGreater(provider.dropped,0)
        m.request_stop();release.set();m.join()
    def test_legacy_serial_source_does_not_leak(self):
        legacy=StreamState();legacy.connection(True,'COM5')
        for i in range(6):legacy.consume('PCM frame=%d peak_index=113 mag=500 L=100 R=100'%i)
        state=RoutedState(legacy);self.assertTrue(state.snapshot()['data_fresh']);state.select('pynq');self.assertIsNone(state.snapshot()['current_note'])


    def owner(self,a,fail_model=False):
        trace=[];folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        args=SimpleNamespace(bit=str(ROOT/'runtime/audio_merged.bit'),input='line',no_model=False,http_port=0,
                             volume=32,no_touch=True,headless=True,record_dir=folder.name)
        class Rx:
            def read(self,*args):return 0
        class Speaker:
            def __init__(self,overlay):self.rx=Rx();self.codec=SimpleNamespace(checked=lambda *x:None)
            def prepare(self,start_rx=True):self.early=start_rx;trace.append(('prepare',start_rx));return {}
            def start_capture(self):trace.append('rx_enable');return {}
            def stop_capture(self):trace.append('rx_disable')
        class Lcd:
            def __init__(self,*unused):
                self.overlay=SimpleNamespace(ip_dict={n:{'phys_addr':v} for n,v in {'axi_dma_0':0x40400000,'axi_dma_1':0x40410000,'lcd_vdma':0x43000000,'lcd_vtc':0x43c20000,'speaker_core':0x43c30000}.items()})
            def start(self):trace.append('lcd_start')
            def stop(self):trace.append('lcd_stop')
        class R:
            def __init__(self,*unused):self.armed=False;self.fail=False;self.released=False
            def arm(self):trace.append('dma0_arm');self.armed=True
            def request_stop(self):trace.append('dma0_cancel')
            def halt(self):
                trace.append('dma0_halt')
                if self.fail:raise RuntimeError('injected halt failure')
            def release(self):trace.append('dma0_release');self.released=True
        class Audio:
            def __init__(self,*args,**kwargs):pass
            def start(self,event):trace.append('audio_start')
            def request_stop(self):trace.append('audio_cancel')
            def join(self):trace.append('audio_join')
        class Model:
            def __init__(self,*unused):
                if fail_model:raise RuntimeError('injected model init failure')
                trace.append('dma1_arm');self.receiver=SimpleNamespace(armed=True,halt=lambda:trace.append('dma1_halt'),release=lambda:trace.append('dma1_release'))
            def start(self,event):trace.append('model_start')
            def request_stop(self):trace.append('model_cancel')
            def join(self):trace.append('model_join')
        class Service:
            def __init__(self,*args,**kwargs):pass
            def start(self):trace.append('service_start')
            def close(self):trace.append('service_close')
        factories=dict(lcd=Lcd,speaker=Speaker,dma0=R,audio=Audio,model=Model,service=Service)
        return MusicSystem(a,args,factories),trace
    def test_owner_start_order_and_safe_stop_order(self):
        a=self.analysis();owner,trace=self.owner(a);owner.start()
        self.assertIn(('prepare',False),trace)
        self.assertLess(trace.index('dma0_arm'),trace.index('rx_enable'));self.assertLess(trace.index('dma1_arm'),trace.index('rx_enable'))
        owner.close();self.assertLess(trace.index('rx_disable'),trace.index('dma0_halt'))
        self.assertLess(trace.index('audio_join'),trace.index('dma0_release'));self.assertLess(trace.index('model_join'),trace.index('dma1_release'))
        self.assertLess(trace.index('dma1_release'),trace.index('lcd_stop'));self.assertTrue(owner.stopped)
    def test_owner_partial_init_failure_before_rx(self):
        a=self.analysis();owner,trace=self.owner(a,fail_model=True)
        with self.assertRaises(RuntimeError):owner.start()
        owner.close();self.assertNotIn('rx_enable',trace);self.assertTrue(owner.receiver.released);self.assertIn('lcd_stop',trace)
    def test_stop_failure_quarantines_buffers_and_allows_retry(self):
        a=self.analysis();owner,trace=self.owner(a);owner.start();owner.receiver.fail=True
        with self.assertRaises(StopFailed):owner.close()
        self.assertFalse(owner.receiver.released);self.assertNotIn('lcd_stop',trace)
        owner.receiver.fail=False;owner.close();self.assertTrue(owner.receiver.released)
    def test_packaged_entry_verifies_before_any_hardware_import(self):
        from run_live_system import verify_bit_pair
        verify_bit_pair(ROOT/'runtime/audio_merged.bit')
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'wrong.bit';p.write_bytes(b'bad')
            with self.assertRaises(FileNotFoundError):verify_bit_pair(p)
    def test_model_power_restore_and_frozen_silence(self):
        from pl_fft import restore_power
        from reference_infer import ReferenceSession
        self.assertEqual(restore_power([0x80000000],3)[0],128.)
        class R:
            def receive_batch(self):return dict(power=np.zeros((513,63)),segment=0,start=0,dropped=0,exponents=np.zeros(63,dtype='u1'))
        result=ReferenceSession(R(),ROOT/'runtime/models',ROOT/'runtime/reference').next()
        self.assertEqual(result['label'],'silence');self.assertIsNone(result['reference_similarity'])

if __name__=='__main__':unittest.main(verbosity=2)
