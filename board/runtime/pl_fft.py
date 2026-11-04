"""PYNQ receiver for music_fft1024_batch protocol 0xA55A0402 (not old 0401).

No PS FFT is used in this deployment. NumPy FFT appears only in offline tests.
PYNQ imports are lazy so protocol and feature checks also run on a PC.
"""
from pathlib import Path
import time
import numpy as np

MAGIC, WORDS, FRAMES, BINS = 0xA55A0402, 522, 63, 513
DMA_BASE, ERROR_MASK = 0x40410000, 0x4770


class ProtocolError(RuntimeError):
    pass


def decode_frame(words):
    w = np.asarray(words, dtype=np.uint32)
    if w.shape != (WORDS,):
        raise ProtocolError("Expected exactly 522 uint32 words")
    magic, segment, index, start, flags, bins, config, reserved, exp = map(int, w[:9])
    if magic != MAGIC or bins != BINS or config != 1 or reserved != 0:
        raise ProtocolError("Overlay/protocol mismatch: header=" + repr(w[:9].tolist()))
    if index >= FRAMES or flags & 0xFFFF or exp > 31:
        raise ProtocolError("Invalid frame index, PL error flag, or BFP exponent")
    return dict(segment=segment, index=index, start=start, dropped=flags >> 16,
                exponent=exp, power=w[9:].copy())


def restore_power(power, exponent):
    """BFP right shifts are undone BEFORE global log-mel normalization.

    XFFT mantissa input is integer PCM, so also divide by 32768**2.
    The uint32 power may exceed signed int32; do not reinterpret it as signed.
    """
    return np.ldexp(np.asarray(power, dtype=np.float64), 2 * int(exponent) - 30)


def power_to_mel(power, mel_matrix):
    p = np.asarray(power, dtype=np.float64)
    matrix = np.asarray(mel_matrix)
    if p.shape != (BINS, FRAMES) or matrix.shape != (64, BINS):
        raise ValueError("Expected power (513,63) and saved mel matrix (64,513)")
    if not np.all(np.isfinite(p)) or np.any(p < 0):
        raise ValueError("Invalid power spectrum")
    db = 10.0 * np.log10(np.maximum(1e-10, matrix @ p))
    db -= db.max()  # ONE reference over all 64x63 elements, as in training.
    return np.clip((db + 80.0) / 80.0, 0.0, 1.0).astype(np.float32)


class BatchAssembler:
    """Never splice frames from different segments, including uint32 wrap."""
    def __init__(self):
        self.frames = []

    def push(self, frame):
        index = len(self.frames)
        if frame["index"] != index:
            self.frames = []
            raise ProtocolError("Missing/repeated frame; discard batch and reload overlay")
        if index and any(frame[k] != self.frames[0][k] for k in ("segment", "start", "dropped")):
            self.frames = []
            raise ProtocolError("Segment metadata changed inside one batch")
        self.frames.append(frame)
        if len(self.frames) < FRAMES:
            return None
        frames, self.frames = self.frames, []
        power = np.stack([restore_power(f["power"], f["exponent"]) for f in frames], axis=1)
        return dict(segment=frames[0]["segment"], start=frames[0]["start"],
                    dropped=frames[0]["dropped"], power=power,
                    exponents=np.array([f["exponent"] for f in frames], dtype=np.uint8))


class FFTReceiver:
    """Own DMA1 exclusively. Finite MMIO polling; no interrupt/wait dependency.

    Create once immediately after loading the matching overlay. Do not create
    another reader midway through a batch: DMA reset does not reset PL state.
    After ANY receive/protocol error, close safely, then reload the overlay.
    """
    def __init__(self, mmio=None, buffer=None, timeout=3.0):
        if mmio is None or buffer is None:
            from pynq import MMIO, allocate
            mmio = MMIO(DMA_BASE, 0x10000) if mmio is None else mmio
            buffer = allocate(shape=(WORDS,), dtype=np.uint32) if buffer is None else buffer
        self.mmio, self.buffer = mmio, buffer
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        self.failed = False
        self.assembler = BatchAssembler()
        try:
            self._reset()
            self.mmio.write(0x30, 1)  # S2MM_DMACR RS; interrupts disabled.
            self._until(lambda: not self.mmio.read(0x34) & 1, "DMA start")
        except BaseException:
            self.failed = True  # Buffer retained if reset cannot confirm quiescence.
            raise

    def _until(self, predicate, operation):
        deadline = time.monotonic() + self.timeout
        while not predicate():
            if time.monotonic() >= deadline:
                raise TimeoutError(operation + " timeout")
            time.sleep(0.0001)

    def _reset(self):
        self.mmio.write(0x30, 4)
        self._until(lambda: not self.mmio.read(0x30) & 4, "DMA reset")
        self._until(lambda: bool(self.mmio.read(0x34) & 1), "DMA halt")

    def receive_frame(self):
        if self.buffer is None or self.failed:
            raise RuntimeError("Receiver closed/failed; reload overlay before another session")
        try:
            self.buffer.flush()  # Avoid later dirty-cache writeback over DMA output.
            self.mmio.write(0x34, 0x7000)  # W1C IOC/delay/error IRQ status.
            address = int(self.buffer.physical_address)
            if address >> 32:
                raise RuntimeError("This design has a 32-bit DMA address port")
            self.mmio.write(0x48, address)
            self.mmio.write(0x58, WORDS * 4)

            def completed():
                status = self.mmio.read(0x34)
                if status & ERROR_MASK:
                    raise RuntimeError("S2MM error status=0x%08X" % status)
                return (status & 0x1002) == 0x1002  # IOC and IDLE.

            self._until(completed, "FFT frame (2088 bytes)")
            if self.mmio.read(0x58) != WORDS * 4:
                raise ProtocolError("Short packet: TLAST/length mismatch")
            self.buffer.invalidate()
            return decode_frame(np.array(self.buffer, dtype=np.uint32, copy=True))
        except BaseException:
            self.failed = True
            raise

    def receive_batch(self):
        try:
            while True:
                batch = self.assembler.push(self.receive_frame())
                if batch is not None:
                    return batch
        except BaseException:
            self.failed = True
            self.assembler = BatchAssembler()
            raise

    def close(self):
        if self.buffer is not None:
            self._reset()  # Must succeed before releasing physical memory.
            self.buffer.freebuffer()
            self.buffer = None


class InstrumentSession:
    def __init__(self, receiver, model_dir="models", silence_rms=0.003):
        from infer_numpy import NumpyInstrumentClassifier
        model_dir = Path(model_dir)
        self.receiver = receiver
        self.matrix = np.load(str(model_dir / "mel_matrix.npy"))
        self.model = NumpyInstrumentClassifier(str(model_dir / "cnn_weights.npz"),
                                              str(model_dir / "model_meta.json"))
        self.silence_rms = float(silence_rms)
        self.previous_segment = None
        self.capture_features = False
        self.last_features = None

    def next(self):
        self.last_features = None
        started = time.monotonic()
        batch = self.receiver.receive_batch()
        received = time.monotonic()
        p = batch["power"]
        # Parseval on interior frames with periodic-Hann energy=3N/8.
        # This is a window-weighted level estimate, NOT an exact PCM RMS.
        energy = p[0] + p[-1] + 2.0 * p[1:-1].sum(axis=0)
        rms_est = float(np.sqrt(np.mean(energy[2:-2]) / (1024 * 384)))
        gap = (self.previous_segment is not None and
               batch["segment"] != (self.previous_segment + 1) & 0xFFFFFFFF)
        self.previous_segment = batch["segment"]
        result = dict(segment=batch["segment"], dropped=batch["dropped"], gap=gap,
                      rms_est=rms_est, receive_ms=(received-started)*1000,
                      exponent_range=[int(batch["exponents"].min()), int(batch["exponents"].max())])
        mel = power_to_mel(p, self.matrix) if self.capture_features or rms_est >= self.silence_rms else None
        if self.capture_features:
            self.last_features = dict(power=p,mel=mel,exponents=batch['exponents'])
        if rms_est < self.silence_rms:
            result.update(label="silence", confidence=None, probabilities=None, compute_ms=0.0)
            return result
        index, probs = self.model.infer(mel)
        result.update(label=self.model.labels[index], confidence=float(probs[index]),
                      probabilities={k: float(v) for k, v in zip(self.model.labels, probs)},
                      compute_ms=(time.monotonic()-received)*1000)
        return result
