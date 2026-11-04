"""Long versions of existing fixtures for debugger snapshots; no firmware edits."""
import hashlib
import json
import math
import struct
import wave
from pathlib import Path

OUT = Path(__file__).resolve().parent / 'focus_audio'
SR = 16000
CASES = [
    ('E5_pure_20s', 659.255114, {1: 1.0}),
    ('A2_third_strong_20s', 110.0, {1: .1, 2: .15, 3: 1., 4: .4, 5: .3}),
    ('A3_missing_fundamental_20s', 220.0, {2: .8, 3: .6, 4: .4, 5: .3, 6: .2}),
]


def main():
    OUT.mkdir(exist_ok=True)
    manifest = []
    for name, f0, harmonics in CASES:
        count = 20 * SR
        scale = .35 / max(1., sum(abs(v) for v in harmonics.values()))
        pcm = bytearray(2 * SR)
        for i in range(count):
            sample = sum(a * math.sin(2 * math.pi * f0 * h * i / SR + .13 * h)
                         for h, a in harmonics.items())
            # Same 160-sample endpoint ramps as make_validation_audio.py.
            envelope = min(1., i / 159., (count - 1 - i) / 159.)
            pcm.extend(struct.pack('<h', round(sample * scale * envelope * 32767)))
        pcm.extend(bytes(2 * SR))
        path = OUT / (name + '.wav')
        with wave.open(str(path), 'wb') as target:
            target.setnchannels(1)
            target.setsampwidth(2)
            target.setframerate(SR)
            target.writeframes(pcm)
        with wave.open(str(path), 'rb') as check:
            assert (check.getnchannels(), check.getsampwidth(), check.getframerate(),
                    check.getnframes()) == (1, 2, SR, 22 * SR)
        manifest.append(dict(file=path.name, sr=SR, synthetic=True, f0_hz=f0,
                             harmonics=harmonics, start_s=1., end_s=21., duration_s=22.,
                             sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    for item in manifest:
        print(item['file'], item['duration_s'], 'seconds', item['sha256'])


if __name__ == '__main__':
    main()
