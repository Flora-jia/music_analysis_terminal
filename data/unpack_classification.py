"""Extract the checked classification corpus provided in the platform package."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parent


def main():
    source = ROOT / 'classification_archive.zip'
    receipt = json.loads((ROOT / 'classification_archive.json').read_text(encoding='utf-8'))
    if hashlib.sha256(source.read_bytes()).hexdigest() != receipt['sha256']:
        raise ValueError('Classification archive mismatch')
    target = ROOT / 'classification_replay'
    if target.exists():
        raise ValueError('Use a new extraction destination')
    with zipfile.ZipFile(source) as archive:
        if archive.testzip():
            raise ValueError('Classification archive CRC error')
        for item in archive.infolist():
            if target.resolve() not in (target / item.filename).resolve().parents:
                raise ValueError('Invalid archive member')
        archive.extractall(target)
    print('CLASSIFICATION_READY', target / 'r6_audio_evaluation_20261104')


if __name__ == '__main__':
    main()
