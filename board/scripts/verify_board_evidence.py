"""Verify original board archives, extracted records and matching input files."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[2]
BOARD = ROOT / "board"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    directory = BOARD / "results/current_r6"
    index = json.loads((directory / "evidence_index.json").read_text(encoding="utf-8"))
    checked_members = 0
    for case in index["cases"]:
        receipt_path = directory / case["evidence_manifest"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        folder = receipt_path.parent
        archive = folder / receipt["archive_file"]
        if sha256(archive.read_bytes()) != receipt["archive_sha256"]:
            raise ValueError("Archive differs: " + receipt["case"])
        with zipfile.ZipFile(archive) as source:
            if source.testzip():
                raise ValueError("ZIP CRC failure: " + receipt["case"])
            for name, item in receipt["members"].items():
                data = source.read(name)
                if len(data) != item["bytes"] or sha256(data) != item["sha256"]:
                    raise ValueError("Archive member differs: " + name)
                if "extracted_file" in item:
                    target = (folder / item["extracted_file"]).resolve()
                    if folder.resolve() not in target.parents or target.read_bytes() != data:
                        raise ValueError("Extracted record differs: " + name)
                checked_members += 1
        conditions = json.loads((directory / case["test_conditions"]).read_text(encoding="utf-8"))
        for item in conditions["playback_order"]:
            if sha256((ROOT / item["file"]).read_bytes()) != item["sha256"]:
                raise ValueError("Test input differs: " + item["file"])
    environment = json.loads((BOARD / "environment/environment.json").read_text(encoding="utf-8"))
    for name, expected in environment["runtime_hashes"].items():
        if sha256((BOARD / "runtime" / name).read_bytes()) != expected:
            raise ValueError("Environment runtime differs: " + name)
    print("BOARD_EVIDENCE_VERIFY_OK", json.dumps({"cases": len(index["cases"]), "archive_members": checked_members}))


if __name__ == "__main__":
    main()
