"""Create a submission manifest for the directories present after validating runtime pairing."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[2]
SCOPE = [name for name in ("src", "sim", "build", "board", "data", "skill", "report")
         if (ROOT / name).is_dir()]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "release_manifest.json")
    args = parser.parse_args()
    output = args.out.resolve()
    if output.exists():
        raise SystemExit("Manifest already exists; use a new --out path")
    runtime = ROOT / "board/runtime"
    board = json.loads((runtime / "manifest_board.json").read_text(encoding="utf-8"))
    for name, value in board["files"].items():
        if sha256(runtime / name) != value["sha256"]:
            raise ValueError("Runtime pairing mismatch " + name)
    files = {}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path.resolve() in (output, ROOT / "release_manifest.json"):
            continue
        relative = path.relative_to(ROOT)
        if set(relative.parts) & {".git", ".Xil", "__pycache__", ".cache", "node_modules"}:
            continue
        if relative.parts[:2] == ("build", "work") or path.suffix in (".pyc", ".pyo"):
            continue
        name = relative.as_posix()
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", name):
            raise ValueError("Use an English filename " + name)
        files[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    manifest = {
        "schema": "music.submission.release.v1",
        "release": "20261104-r6-submission",
        "software_release": board["software_release"],
        "scope": SCOPE,
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runtime_manifest_sha256": sha256(runtime / "manifest_board.json"),
        "artifact_hashes": {name: sha256(runtime / name) for name in (
            "audio_merged.bit", "audio_merged.hwh", "models/cnn_weights.npz", "dsp/libmusic_ps.so")},
        "files": files,
    }
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SUBMISSION_MANIFEST_CREATED", len(files), output)


if __name__ == "__main__":
    main()
