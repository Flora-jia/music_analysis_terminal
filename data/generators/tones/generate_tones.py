"""Generate controlled, identical L/R PCM test tones using only Python stdlib.

Run: python generate_tones.py
WAV files are written to the adjacent tones directory. This does not modify RTL,
the Vivado project, the Vitis application, or any downloaded hardware image.
"""

import json
import math
from pathlib import Path
import struct
import wave


RATE = 48000
DURATION = 6.0
RAMP_SECONDS = 0.05
OUTPUT = Path(__file__).resolve().parent / "tones"
CASES = [
    ("01_500Hz.wav", [(500.0, 0.25)]),
    ("02_1000Hz.wav", [(1000.0, 0.25)]),
    ("03_440Hz.wav", [(440.0, 0.25)]),
    ("04_silence.wav", []),
    ("05_220Hz_weak_fundamental_440Hz.wav", [(220.0, 0.04), (440.0, 0.20)]),
]


def generate():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    count = round(RATE * DURATION)
    ramp = round(RATE * RAMP_SECONDS)
    manifest = {"sample_rate": RATE, "channels": 2, "bits": 16,
                "duration_seconds": DURATION, "identical_channels": True,
                "note": "PC WAV rate differs from FPGA acquisition rate; tones retain their physical frequency.",
                "files": []}
    for name, components in CASES:
        frames = bytearray()
        maximum = 0
        for i in range(count):
            envelope = min(1.0, i / ramp, (count - 1 - i) / ramp)
            value = sum(gain * math.sin(2.0 * math.pi * frequency * i / RATE)
                        for frequency, gain in components)
            sample = round(value * envelope * 32767)
            if not -32768 <= sample <= 32767:
                raise ValueError(f"Clipping in {name}: {sample}")
            maximum = max(maximum, abs(sample))
            frames.extend(struct.pack("<hh", sample, sample))
        path = OUTPUT / name
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(frames)
        manifest["files"].append({"name": name, "components_hz_and_peak_gain": components,
                                  "digital_peak": maximum, "frames": count})
        print(f"{name}: {count} stereo frames, peak={maximum}")
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                                          encoding="utf-8")


if __name__ == "__main__":
    generate()
