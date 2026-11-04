"""Check the additional reference artifacts before starting DMA or the Codec."""
import hashlib
import json
from pathlib import Path


def verify_reference_bundle(root='.'):
    root=Path(root)
    manifest=json.loads((root/'reference_manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        actual=hashlib.sha256((root/name).read_bytes()).hexdigest()
        if actual!=digest:
            raise RuntimeError('Reference artifact hash mismatch: '+name)
    metadata=json.loads((root/'reference/reference_meta.json').read_text(encoding='utf-8'))
    return dict(method=manifest['method'],reference_count=metadata['reference_count'],
                verified_reference_files=len(manifest['files']),
                note='Reference calibration data are separate from CNN probabilities')
