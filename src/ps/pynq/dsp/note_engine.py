"""Serialized, lifecycle-safe access to the supplied legacy C note engine."""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import platform
import threading
import time
import weakref
import numpy as np
from ._native import NativeEngine,MPResult,MPEvent,MPSummary,MPJianpu

_REGISTRY=weakref.WeakValueDictionary()
_REGISTRY_LOCK=threading.RLock()

def layout():
    return {c.__name__:{'size':ctypes.sizeof(c),'offsets':{name:getattr(c,name).offset for name,_ in c._fields_}}
            for c in (MPResult,MPEvent,MPSummary,MPJianpu)}

class NoteEngine:
    def __init__(self,lib_path=None,session_id=1,clock=time.monotonic):
        here=Path(__file__).resolve().parent
        if lib_path is None:
            lib_path=here.parent.parent/'dsp/libmusic_ps_host.dll' if os.name=='nt' else here/'libmusic_ps.so'
        self.path=Path(lib_path).resolve();self.clock=clock;self.lock=threading.RLock();self.closed=False
        if isinstance(session_id,bool) or not 0<=int(session_id)<=0xffffffff:raise ValueError('Invalid session ID')
        self.used_sessions={int(session_id)}
        self.session_id=int(session_id);self.last_time=None;self.last_frame=0;self.timed_out=False
        self._verify_abi(here)
        with _REGISTRY_LOCK:
            owner=_REGISTRY.get(str(self.path))
            if owner is not None and not owner.closed:raise RuntimeError('C library is single-instance; share the existing note engine')
            try:self.native=NativeEngine(str(self.path),self.session_id)
            except OSError as exc:raise RuntimeError('Native note library initialization failed (ABI/ISA/runtime): '+str(exc)) from exc
            if self.native.version()!='libmusic_ps 2.0.0':raise RuntimeError('Unknown native note ABI version')
            if self.native.jianpu(60)['name']!='C4':raise RuntimeError('Native ABI smoke check failed')
            _REGISTRY[str(self.path)]=self
    def _verify_abi(self,here):
        manifest=json.loads((here/'abi_manifest.json').read_text(encoding='utf-8'))
        if layout()!=manifest['layout']:raise RuntimeError('ctypes native ABI size/offset mismatch')
        digest=hashlib.sha256(self.path.read_bytes()).hexdigest()
        if digest not in manifest['libraries'].values():raise RuntimeError('Unrecognized native note library hash')
        if os.name!='nt':
            if platform.machine().lower() not in ('armv7l','armv7') or ctypes.sizeof(ctypes.c_void_p)!=4:
                raise RuntimeError('This supplied library requires ARMv7 hard-float Linux, not '+platform.machine())
            header=self.path.read_bytes()[:52]
            if header[:6]!=b'\x7fELF\x01\x01' or int.from_bytes(header[18:20],'little')!=40:
                raise RuntimeError('Native library is not little-endian ELF32 ARM')
        self.abi_verified=True
    def _events(self,cause):
        values=self.native.drain_events()
        for e in values:
            e.update(schema='ac820.note_event.v2',runtime_reason=cause)
        if self.native.take_resync():
            values.append(dict(type=4,session_id=self.session_id,event_seq=None,note_id=None,
                schema='ac820.note_event.v2',runtime_reason='native_queue_overflow',time_quality=2,flags=1,fs_hz=16000,native_schema=None,decision_sample=None))
        return values
    def _output(self,current,events):
        candidates=list(events)+([current] if current and current.get('valid') else [])
        for item in candidates:
            if item.get('type') in (3,4):continue
            if not 0<=int(item.get('midi',-1))<=127 or not np.isfinite(item.get('frequency_hz',float('nan'))) or not np.isfinite(item.get('confidence',float('nan'))):
                raise RuntimeError('Invalid native note fields')
        return dict(current=current,events=events,summary=self.native.summary(),session_id=self.session_id)
    def process(self,mag,first_sample,frame_id,gap=0):
        arr=np.asarray(mag)
        if arr.shape!=(2049,) or arr.dtype.kind not in 'uif' or not np.isfinite(arr).all() or np.any(arr<0) or np.any(arr>65535) or np.any(arr!=np.floor(arr)):
            raise ValueError('Native pitch requires exactly 2049 uint16 magnitudes')
        if first_sample<0 or not 0<=frame_id<=0xffffffff or not 0<=gap<=0xffffffff:raise ValueError('Invalid native frame metadata')
        with self.lock:
            if self.closed:raise RuntimeError('Note engine closed')
            current=self.native.process(arr,int(first_sample),int(frame_id),int(gap))
            self.last_time=self.clock();self.last_frame=int(frame_id);self.timed_out=False
            return self._output(current,self._events('frame'))
    def bad_packet(self,frame_id=None,check_code=1,cause='bad_packet'):
        with self.lock:
            if self.closed:return None
            if frame_id is None:frame_id=self.last_frame
            rc=self.native.on_bad_packet(frame_id,check_code)
            if rc:raise RuntimeError('Native bad-packet handler failed')
            self.timed_out=True
            return self._output(None,self._events(cause))
    def poll(self):
        with self.lock:
            if self.closed or self.timed_out or self.last_time is None or self.clock()-self.last_time<.128:return None
            if self.native._lib.mp_watchdog():raise RuntimeError('Native watchdog failed')
            self.timed_out=True
            return self._output(None,self._events('watchdog_timeout'))
    def stop(self,cause='stop'):
        with self.lock:
            if self.closed:return None
            if self.native.stop():raise RuntimeError('Native stop failed')
            self.timed_out=True
            return self._output(None,self._events(cause))
    def reset(self,session_id):
        with self.lock:
            # Deliver old session OFF before reinitializing, never use the unsafe mp_reset.
            if int(session_id) in self.used_sessions or not 0<=int(session_id)<=0xffffffff:raise ValueError('Use a new uint32 session ID')
            self.used_sessions.add(int(session_id))
            old=self.stop('session_reset');previous=self.session_id
            self.session_id=int(session_id)
            if self.native._lib.mp_reset_checked(ctypes.c_uint32(self.session_id)):raise RuntimeError('Native reset rejected; old data must be delivered first')
            self.native._session_id=self.session_id;self.last_time=None;self.timed_out=False
            old['events'].append(dict(type=4,session_id=self.session_id,previous_session_id=previous,event_seq=None,
                note_id=None,schema='ac820.note_event.v2',runtime_reason='session_reset',time_quality=2))
            return self._output(None,old['events'])
    def calibrate(self):
        with self.lock:
            previous=self.stop('calibration_start')
            if self.native.calib_start():raise RuntimeError('Calibration start failed')
            return self._output(None,previous['events']+self._events('calibration'))
    def jianpu(self,midi):
        with self.lock:return self.native.jianpu(midi)
    def close(self):
        with self.lock:
            if self.closed:return None
            output=self.stop();self.closed=True
            with _REGISTRY_LOCK:
                if _REGISTRY.get(str(self.path)) is self:_REGISTRY.pop(str(self.path),None)
            return output
