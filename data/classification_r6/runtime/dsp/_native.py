"""wrapper.py - ctypes bindings for libmusic_ps.so (the C note engine).

Field order/types/alignment of the ctypes.Structure classes below MUST match
pynq_wrapper.h byte-for-byte. A mismatch corrupts results (or crashes) at
runtime on both x86 and ARM.

The engine is single-instance and not thread-safe; serialise access.
"""
import ctypes
import os

MP_BINS = 2049


class MPResult(ctypes.Structure):
    _fields_ = [
        ("valid", ctypes.c_int32),
        ("active", ctypes.c_int32),
        ("tracking_valid", ctypes.c_int32),
        ("midi", ctypes.c_int32),
        ("frequency_hz", ctypes.c_float),
        ("confidence", ctypes.c_float),
        ("note_id", ctypes.c_uint32),
        ("reason", ctypes.c_int32),
        ("time_quality", ctypes.c_int32),
        ("frame_id", ctypes.c_uint32),
        ("feature_sample", ctypes.c_uint64),
        ("decision_sample", ctypes.c_uint64),
    ]


class MPEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int32),
        ("note_id", ctypes.c_uint32),
        ("midi", ctypes.c_int32),
        ("frequency_hz", ctypes.c_float),
        ("confidence", ctypes.c_float),
        ("start_sample", ctypes.c_uint64),
        ("end_sample", ctypes.c_uint64),
        ("duration_s", ctypes.c_float),
        ("reason", ctypes.c_int32),
        ("time_quality", ctypes.c_int32),
        ("frame_id", ctypes.c_uint32),
        ("session_id", ctypes.c_uint32),
        ("event_seq", ctypes.c_uint32),
        ("schema_version", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("decision_sample", ctypes.c_uint64),
        ("fs", ctypes.c_uint32),
    ]


class MPSummary(ctypes.Structure):
    _fields_ = [
        ("on_count", ctypes.c_uint32),
        ("off_count", ctypes.c_uint32),
        ("onset_count", ctypes.c_uint32),
        ("unassigned_onsets", ctypes.c_uint32),
        ("bad_packet_count", ctypes.c_uint32),
        ("gap_count", ctypes.c_uint32),
        ("event_overflow", ctypes.c_uint32),
        ("noise_db_milli", ctypes.c_int32),
        ("calibrated", ctypes.c_int32),
        ("state", ctypes.c_int32),
    ]


class MPJianpu(ctypes.Structure):
    _fields_ = [
        ("valid", ctypes.c_int32),
        ("degree", ctypes.c_int32),
        ("accidental", ctypes.c_int32),
        ("octave_offset", ctypes.c_int32),
        ("name", ctypes.c_char * 8),
    ]


class NativeEngine:
    """ctypes wrapper around libmusic_ps.so."""

    def __init__(self, lib_path=None, session_id=1):
        if lib_path is None:
            lib_path = self._default_lib()
        self._lib = ctypes.CDLL(str(lib_path))
        self._setup_prototypes()
        self._session_id = session_id
        self._res = MPResult()
        self._ev = MPEvent()
        rc = self._lib.mp_init(ctypes.c_uint32(session_id))
        if rc != 0:
            raise RuntimeError("mp_init failed: %d" % rc)

    @staticmethod
    def _default_lib():
        here = os.path.dirname(os.path.abspath(__file__))
        names = (["libmusic_ps_host.dll", "libmusic_ps.dll", "libmusic_ps.so"]
                 if os.name == "nt"
                 else ["libmusic_ps.so", "libmusic_ps_host.dll", "libmusic_ps.dll"])
        for name in names:
            p = os.path.join(here, name)
            if os.path.exists(p):
                return p
        raise FileNotFoundError(
            "libmusic_ps.so / libmusic_ps_host.dll not found in %s" % here)

    def _setup_prototypes(self):
        lib = self._lib
        lib.mp_abi_version.argtypes=[];lib.mp_abi_version.restype=ctypes.c_uint32
        lib.mp_sizeof.argtypes=[ctypes.c_uint32];lib.mp_sizeof.restype=ctypes.c_uint32
        lib.mp_offsetof.argtypes=[ctypes.c_uint32,ctypes.c_uint32];lib.mp_offsetof.restype=ctypes.c_uint32
        lib.mp_reset_checked.argtypes=[ctypes.c_uint32];lib.mp_reset_checked.restype=ctypes.c_int
        lib.mp_watchdog.argtypes=[];lib.mp_watchdog.restype=ctypes.c_int
        if lib.mp_abi_version()!=2:raise RuntimeError('Native ABI version mismatch')
        for type_id,kind in enumerate((MPResult,MPEvent,MPSummary,MPJianpu),1):
            if lib.mp_sizeof(type_id)!=ctypes.sizeof(kind):raise RuntimeError('Native struct size mismatch: '+kind.__name__)
            for index,(name,_) in enumerate(kind._fields_):
                if lib.mp_offsetof(type_id,index)!=getattr(kind,name).offset:raise RuntimeError('Native offset mismatch: '+kind.__name__+'.'+name)
        lib.mp_init.argtypes = [ctypes.c_uint32]
        lib.mp_init.restype = ctypes.c_int
        lib.mp_reset.argtypes = [ctypes.c_uint32]
        lib.mp_reset.restype = None
        lib.mp_process.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint64,
            ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(MPResult),
        ]
        lib.mp_process.restype = ctypes.c_int
        lib.mp_on_bad_packet.argtypes = [ctypes.c_uint32, ctypes.c_int]
        lib.mp_on_bad_packet.restype = ctypes.c_int
        lib.mp_pop_event.argtypes = [ctypes.POINTER(MPEvent)]
        lib.mp_pop_event.restype = ctypes.c_int
        lib.mp_take_resync.argtypes = []
        lib.mp_take_resync.restype = ctypes.c_int
        lib.mp_stop.argtypes = []
        lib.mp_stop.restype = ctypes.c_int
        lib.mp_calib_start.argtypes = []
        lib.mp_calib_start.restype = ctypes.c_int
        lib.mp_calib_ready.argtypes = []
        lib.mp_calib_ready.restype = ctypes.c_int
        lib.mp_jianpu.argtypes = [ctypes.c_int, ctypes.POINTER(MPJianpu)]
        lib.mp_jianpu.restype = ctypes.c_int
        lib.mp_get_summary.argtypes = [ctypes.POINTER(MPSummary)]
        lib.mp_get_summary.restype = ctypes.c_int
        lib.mp_version.argtypes = []
        lib.mp_version.restype = ctypes.c_char_p

    # ---- high-level API ----

    def version(self):
        return self._lib.mp_version().decode("ascii", errors="replace")

    def process(self, mag, first_sample, frame_id, gap=0):
        """Feed one 2049-bin uint16 magnitude frame.

        mag: anything convertible to a contiguous uint16 array via
        numpy.ascontiguousarray (a numpy array, list, bytes, or buffer).
        Returns the current-note snapshot dict.
        """
        import numpy as np
        arr = np.ascontiguousarray(mag, dtype=np.uint16)
        if arr.size < MP_BINS:
            raise ValueError("need >= %d bins, got %d" % (MP_BINS, arr.size))
        rc = self._lib.mp_process(
            arr.ctypes.data, ctypes.c_int(arr.size),
            ctypes.c_uint64(int(first_sample)), ctypes.c_uint32(int(frame_id)),
            ctypes.c_uint32(int(gap)), ctypes.byref(self._res))
        if rc != 0:
            raise RuntimeError("mp_process failed: %d" % rc)
        return self._result_dict()

    def on_bad_packet(self, frame_id, check_code):
        return self._lib.mp_on_bad_packet(ctypes.c_uint32(int(frame_id)),
                                          ctypes.c_int(int(check_code)))

    def _result_dict(self):
        r = self._res
        valid = bool(r.valid)
        return {
            "valid": valid,
            "active": bool(r.active),
            "tracking_valid": bool(r.tracking_valid),
            "midi": int(r.midi) if valid else -1,
            "frequency_hz": float(r.frequency_hz) if valid else 0.0,
            "confidence": float(r.confidence),
            "note_id": int(r.note_id) if valid else 0,
            "reason": int(r.reason),
            "time_quality": int(r.time_quality),
            "frame_id": int(r.frame_id),
            "feature_sample": int(r.feature_sample),
            "decision_sample": int(r.decision_sample),
        }

    def pop_event(self):
        """Return one event dict, or None when the queue is empty."""
        if self._lib.mp_pop_event(ctypes.byref(self._ev)) == 0:
            return None
        e = self._ev
        return {
            "type": int(e.type),
            "note_id": int(e.note_id),
            "midi": int(e.midi),
            "frequency_hz": float(e.frequency_hz),
            "confidence": float(e.confidence),
            "start_sample": int(e.start_sample),
            "end_sample": int(e.end_sample),
            "duration_s": float(e.duration_s),
            "reason": int(e.reason),
            "time_quality": int(e.time_quality),
            "frame_id": int(e.frame_id),
            "session_id": int(e.session_id),
            "event_seq": int(e.event_seq),
            "native_schema": int(e.schema_version),
            "flags": int(e.flags),
            "decision_sample": int(e.decision_sample),
            "fs_hz": int(e.fs),
        }

    def drain_events(self):
        evs = []
        while True:
            e = self.pop_event()
            if e is None:
                return evs
            evs.append(e)

    def take_resync(self):
        return self._lib.mp_take_resync() != 0

    def stop(self):
        return self._lib.mp_stop()

    def reset(self, session_id):
        self._lib.mp_reset(ctypes.c_uint32(int(session_id)))
        self._session_id = session_id

    def calib_start(self):
        return self._lib.mp_calib_start()

    def calib_ready(self):
        return self._lib.mp_calib_ready() != 0

    def jianpu(self, midi):
        jp = MPJianpu()
        ok = self._lib.mp_jianpu(ctypes.c_int(int(midi)), ctypes.byref(jp))
        name = jp.name.split(b"\0", 1)[0].decode("ascii", errors="replace")
        return {
            "valid": bool(jp.valid),
            "degree": int(jp.degree),
            "accidental": int(jp.accidental),
            "octave_offset": int(jp.octave_offset),
            "name": name,
        }

    def summary(self):
        s = MPSummary()
        self._lib.mp_get_summary(ctypes.byref(s))
        return {
            "on_count": int(s.on_count),
            "off_count": int(s.off_count),
            "onset_count": int(s.onset_count),
            "unassigned_onsets": int(s.unassigned_onsets),
            "bad_packet_count": int(s.bad_packet_count),
            "gap_count": int(s.gap_count),
            "event_overflow": int(s.event_overflow),
            "noise_db_milli": int(s.noise_db_milli),
            "calibrated": bool(s.calibrated),
            "state": int(s.state),
        }


