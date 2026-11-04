# -*- coding: utf-8 -*-
"""Generate the missing stage-B test WAVs (16 kHz, mono, 16-bit).

These are synthetic signals, not real instruments. They cover cases the board
folder does not already provide: same-note repeats (with/without silence),
vibrato, slow crescendo, strong harmonic, silence.
"""
import math
import wave
from pathlib import Path

SR = 16000
OUT = Path(__file__).resolve().parent.parent / "test_audio"
OUT.mkdir(parents=True, exist_ok=True)


def write_wav(name, samples):
    peak = max(1e-9, max(abs(x) for x in samples))
    if peak > 0.95:
        samples = [x * 0.95 / peak for x in samples]
    data = bytearray()
    for x in samples:
        v = int(max(-32767, min(32767, round(x * 32767))))
        data += int(v).to_bytes(2, "little", signed=True)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(bytes(data))
    print("wrote", OUT / name, f"{len(samples)/SR:.2f}s")


def silence(sec):
    return [0.0] * int(SR * sec)


def tone(freq, sec, amp=0.5, phase0=0.0):
    n = int(SR * sec)
    return [amp * math.sin(2 * math.pi * freq * i / SR + phase0) for i in range(n)]


def fade(samples, ms=8):
    k = int(SR * ms / 1000)
    for i in range(min(k, len(samples))):
        g = i / k
        samples[i] *= g
        samples[-1 - i] *= g
    return samples


def env_tone(freq, sec, amp_fn):
    n = int(SR * sec)
    return [amp_fn(i / SR) * math.sin(2 * math.pi * freq * i / SR) for i in range(n)]


# 1) same note repeated, with silence (0.5 s on / 0.2 s off, three times)
s = silence(1.0)
for _ in range(3):
    s += fade(tone(261.6256, 0.5, 0.5))
    s += silence(0.2)
s += silence(1.0)
write_wav("same_note_repeat.wav", s)

# 2) same note repeated legato (no silence, 10 ms crossfade)
s = silence(1.0)
for _ in range(3):
    s += fade(tone(261.6256, 0.5, 0.5), 10)
s += silence(1.0)
write_wav("same_note_legato.wav", s)

# 3) vibrato: 440 Hz, 5 Hz, +/-30 cents
n = int(SR * 3.0)
vib = []
phase = 0.0
for i in range(n):
    cents = 30.0 * math.sin(2 * math.pi * 5.0 * i / SR)
    f = 440.0 * (2 ** (cents / 1200.0))
    phase += 2 * math.pi * f / SR
    vib.append(0.45 * math.sin(phase))
write_wav("vibrato_440.wav", silence(1.0) + fade(vib) + silence(1.0))

# 4) slow crescendo: 440 Hz, -26 dB to -2 dB over 3 s
s = silence(1.0)
s += env_tone(440.0, 3.0, lambda t: 0.05 * (10 ** ((24.0 * t / 3.0) / 20.0)))
s += silence(1.0)
write_wav("crescendo_440.wav", s)

# 5) strong third harmonic: 220 Hz weak, 660 Hz strong
s = silence(1.0)
a = tone(220.0, 2.0, 0.08)
b = tone(660.0, 2.0, 0.55)
s += fade([x + y for x, y in zip(a, b)])
s += silence(1.0)
write_wav("strong_third_220.wav", s)

# 6) silence reference
write_wav("silence_2s.wav", silence(2.0))

# 7) 500 ms C-major scale for a quick board sanity check
s = silence(1.0)
for f in (261.6256, 293.6648, 329.6276, 349.2282, 391.9954, 440.0):
    s += fade(tone(f, 0.5, 0.5))
    s += silence(0.1)
s += silence(1.0)
write_wav("scale_500ms_c.wav", s)
