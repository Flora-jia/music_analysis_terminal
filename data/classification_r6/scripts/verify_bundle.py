"""Check the exact files listed in this test bundle without loading hardware."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "bundle_manifest.json").read_text(encoding="utf-8"))
    for name, item in manifest["files"].items():
        path = (ROOT / name).resolve()
        if ROOT not in path.parents or not path.is_file():
            raise ValueError("Missing or invalid file " + name)
        data = path.read_bytes()
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("Content mismatch " + name)
    print("TEST_BUNDLE_VERIFY_OK", len(manifest["files"]))


if __name__ == "__main__":
    main()
