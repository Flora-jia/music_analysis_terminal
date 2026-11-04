"""Check packaged reference audio without importing PYNQ or changing hardware."""
from pathlib import Path
import csv
import hashlib
import json
import wave


def main():
    root = Path(__file__).resolve().parent
    manifest = json.loads((root/'audio_manifest.json').read_text(encoding='utf-8'))
    names = set()
    wav_count = 0
    for item in manifest['files']:
        path = (root/item['file']).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError('Missing or invalid audio path: '+item['file'])
        if item['file'] in names:
            raise ValueError('Duplicate manifest entry: '+item['file'])
        names.add(item['file'])
        data = path.read_bytes()
        if len(data) != item['bytes'] or hashlib.sha256(data).hexdigest() != item['sha256']:
            raise ValueError('Audio content differs: '+item['file'])
        if path.suffix.lower() == '.wav':
            with wave.open(str(path),'rb') as wav:
                if (wav.getframerate(),wav.getnchannels(),wav.getsampwidth()*8,wav.getnframes()) != (
                        item['sample_rate'],item['channels'],item['bits'],item['frames']):
                    raise ValueError('WAV format differs: '+item['file'])
                if len(wav.readframes(wav.getnframes())) != item['frames']*item['channels']*wav.getsampwidth():
                    raise ValueError('Truncated WAV: '+item['file'])
            wav_count += 1
    with (root/'labels/expected_events.csv').open(encoding='utf-8-sig',newline='') as f:
        labels = list(csv.DictReader(f))
    by_name = {item['file']:item for item in manifest['files']}
    for row in labels:
        if row['file'] not in names:
            raise ValueError('Label references missing audio: '+row['file'])
        if row['start_s'] and row['end_s']:
            if not 0 <= float(row['start_s']) < float(row['end_s']) <= by_name[row['file']]['duration_s']+1e-6:
                raise ValueError('Label outside audio duration: '+str(row))
    print('REFERENCE_AUDIO_VERIFY_OK',json.dumps(dict(files=len(names),wav_files=wav_count,
          label_rows=len(labels),board_run=False)))


if __name__ == '__main__':
    main()
