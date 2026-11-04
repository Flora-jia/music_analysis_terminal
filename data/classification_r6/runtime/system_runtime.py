"""Resource owner for one overlay, two DMA masters, C notes and the existing UI."""
from pathlib import Path
import json
import os
import threading
import time
_RETAINED=[]

class StopFailed(RuntimeError):pass

class MusicSystem:
    def __init__(self,analysis,args,factories=None):
        self.analysis,self.args=analysis,args;self.factories=factories or {}
        self.lcd=self.speaker=self.receiver=self.audio=self.model=self.service=self.touch=self.app=None
        self.recorder=None
        self.started=threading.Event();self.lock_file=None;self.stopped=False
    def _factory(self,key,default):return self.factories.get(key,default)
    def start(self):
        from lcd_colorbars import LCDColorbars
        from speaker_audio import Speaker
        from spectrum_audio import SpectrumReceiver
        from live_service import CaptureWorker,AudioService
        from model_stream import create_model_worker
        if _RETAINED:raise StopFailed('A previous session still owns unsafe resources')
        if os.name!='nt' and not self.factories:
            import fcntl
            self.lock_file=open('/tmp/ac820_music_runtime.lock','a+')
            try:fcntl.flock(self.lock_file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except Exception:self.lock_file.close();self.lock_file=None;raise RuntimeError('Another music runtime owns the board')
        self.lcd=self._factory('lcd',LCDColorbars)(self.args.bit);self.lcd.start()
        required={'axi_dma_0':0x40400000,'axi_dma_1':0x40410000,'lcd_vdma':0x43000000,'lcd_vtc':0x43C20000,'speaker_core':0x43C30000}
        for name,address in required.items():
            if int(self.lcd.overlay.ip_dict[name]['phys_addr'])!=address:raise ValueError('Overlay address mismatch: '+name)
        self.speaker=self._factory('speaker',Speaker)(self.lcd.overlay)
        info=self.speaker.prepare(start_rx=False)
        if self.args.input=='line':self.speaker.codec.checked(0x09,0);self.speaker.codec.checked(0x0A,0)
        if getattr(self.args,'capture_label',None):
            from instrument_capture import FeatureRecorder
            root=Path(self.args.bit).parent
            manifest=json.loads((root/'manifest_board.json').read_text(encoding='utf-8'))
            artifacts={name:value for name,value in manifest['files'].items() if name in (
                'models/cnn_weights.npz','models/mel_matrix.npy','models/model_meta.json',
                'reference/reference_bank.npz','reference/reference_meta.json','reference/frozen_config.json',
                'audio_merged.bit','audio_merged.hwh','pl_fft.py','reference_infer.py','infer_numpy.py','instrument_capture.py')}
            metadata=dict(input_profile=self.args.input,note=self.args.capture_note,
                frontend_prepared=info,paired_artifacts=artifacts,
                silence_rms=.003,classification='raw CNN and reference; no smoothing/retraining')
            self.recorder=FeatureRecorder(self.args.capture_dir or root/'instrument_captures',
                self.analysis.session,self.args.capture_label,metadata,
                max_segments=self.args.capture_limit,max_mb=self.args.capture_max_mb)
            print('CAPTURE_DIR:',str(self.recorder.directory),flush=True)
        self.analysis.lifecycle='FRONTEND_CONFIGURED'
        self.receiver=self._factory('dma0',SpectrumReceiver)(self.lcd.overlay);self.receiver.arm()
        if not self.args.no_model:self.model=self._factory('model',create_model_worker)(self.lcd.overlay,self.analysis,Path(self.args.bit).parent)
        if self.model:
            self.model.piano_review=getattr(self.args,'piano_review',False)
            self.model.piano_support=not getattr(self.args,'no_piano_support',False)
        if self.recorder and self.model:
            self.model.recorder=self.recorder
            self.model.session.base.capture_features=True
        if not self.receiver.armed or (self.model and not self.model.receiver.armed):raise RuntimeError('Both DMA receivers must be armed before RX')
        self.analysis.lifecycle='DMA_ARMED'
        def health():
            status=int(self.speaker.rx.read(0x14))
            if status&2:raise RuntimeError('I2S RX FIFO overflow 0x%X'%status)
        self.audio=self._factory('audio',CaptureWorker)(self.receiver,self.analysis,health=health)
        self.audio.start(self.started)
        if self.model:self.model.start(self.started)
        self.service=self._factory('service',AudioService)(self.analysis,port=self.args.http_port);self.service.start()
        self.analysis.mark_capture_started(shared_start=bool(self.model),fir_delay_samples=9.5)
        self.started.set();info=self.speaker.start_capture()
        print('CODEC_AND_CLOCKS:',json.dumps(info),flush=True)
    def run(self):
        from gt911_touch import GT911Touch
        from live_dashboard import LiveDashboardUI
        if self.args.headless:
            while True:self.speaker.poll();time.sleep(.05)
        else:
            class QuietTouch:
                def read_points(self):return []
                def close(self):pass
            self.touch=QuietTouch() if self.args.no_touch else self._factory('touch',GT911Touch)()
            self.app=self._factory('ui',LiveDashboardUI)(self.lcd,self.touch,self.speaker,self.analysis,volume=self.args.volume)
            self.app.ui_stats=getattr(self.args,'ui_stats',False)
            self.app.run()
    def close(self):
        if self.stopped:return
        errors=[]
        def attempt(fn):
            try:fn()
            except Exception as exc:errors.append(str(exc))
        if self.audio:self.audio.request_stop()
        elif self.receiver:self.receiver.request_stop()
        if self.model:self.model.request_stop()
        if self.speaker:attempt(self.speaker.stop_capture)
        attempt(lambda:self.analysis.stop('shutdown'))
        if self.receiver:attempt(self.receiver.halt)
        if self.model:attempt(self.model.receiver.halt)
        if self.audio:attempt(self.audio.join)
        if self.model:attempt(self.model.join)
        if errors:
            self.analysis.lifecycle='STOP_FAILED';self.analysis.error='; '.join(errors)
            if self not in _RETAINED:_RETAINED.append(self)
            raise StopFailed('Keep buffers/overlay alive; '+self.analysis.error)
        # No master or capture worker can access these physical buffers now.
        if self.receiver:attempt(self.receiver.release)
        if self.model:attempt(self.model.receiver.release)
        if self.recorder:
            attempt(self.recorder.close)
            print('CAPTURE_FINAL:',json.dumps(self.recorder.status()),flush=True)
        if self.app:
            attempt(lambda:self.app.feed.step(self.app,force=True));attempt(lambda:self.app._drain(time.monotonic()))
        if self.touch:attempt(self.touch.close)
        if self.lcd:attempt(self.lcd.stop)
        if errors:
            self.analysis.lifecycle='STOP_FAILED';self.analysis.error='; '.join(errors)
            if self not in _RETAINED:_RETAINED.append(self)
            raise StopFailed(self.analysis.error)
        self.analysis.lifecycle='STOPPED'
        if self.service:attempt(self.service.close)
        attempt(lambda:self.analysis.export_records(Path(self.args.record_dir)/(self.analysis.session+'.json')))
        attempt(self.analysis.close_engine)
        if self.lock_file:self.lock_file.close();self.lock_file=None
        self.stopped=True
        if self in _RETAINED:_RETAINED.remove(self)
        if errors:raise RuntimeError('; '.join(errors))
