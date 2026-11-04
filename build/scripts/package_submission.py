"""Package the manifest-covered submission as ZIP or a genuine RAR5 archive."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from verify_release import verify


def stream_sha256(stream):
    digest = hashlib.sha256()
    for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
        digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=("zip", "rar"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rar-exe", type=Path)
    args = parser.parse_args()
    receipt = verify(ROOT)
    manifest = json.loads((ROOT / "release_manifest.json").read_text(encoding="utf-8"))
    archive = args.out.resolve()
    if archive.exists() or ROOT in archive.parents:
        raise SystemExit("Use a new archive path outside the project directory")
    archive.parent.mkdir(parents=True, exist_ok=True)
    names = list(manifest["files"]) + ["release_manifest.json"]
    if args.format == "zip":
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as stream:
            for name in names:
                stream.write(ROOT / name, ROOT.name + "/" + name)
        with zipfile.ZipFile(archive) as stream:
            if stream.testzip() is not None:
                raise RuntimeError("ZIP integrity check failed")
            for name, entry in manifest["files"].items():
                with stream.open(ROOT.name + "/" + name) as member:
                    actual = stream_sha256(member)
                if actual != entry["sha256"]:
                    raise RuntimeError("Archived content mismatch " + name)
    else:
        if args.rar_exe is None or not args.rar_exe.is_file():
            raise SystemExit("Pass the installed RAR command line executable using --rar-exe")
        with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", suffix=".lst", delete=False) as stream:
            listing = Path(stream.name)
            for name in names:
                stream.write(ROOT.name + "/" + name + "\n")
        try:
            command = [str(args.rar_exe.resolve()), "a", "-ma5", "-m5", "-s", "-r", "-idq",
                       str(archive), "@" + str(listing)]
            subprocess.run(command, cwd=ROOT.parent, check=True)
            subprocess.run([str(args.rar_exe.resolve()), "t", "-idq", str(archive)], check=True)
        finally:
            listing.unlink(missing_ok=True)
        with archive.open("rb") as stream:
            if stream.read(8) != bytes.fromhex("526172211a070100"):
                raise RuntimeError("Expected a RAR5 archive")
        if archive.stat().st_size >= 200_000_000:
            raise RuntimeError("Platform archive exceeds the 200M submission limit")
    with archive.open('rb') as archive_stream:
        sha256 = stream_sha256(archive_stream)
    archive.with_suffix(archive.suffix + ".sha256").write_text(
        sha256 + "  " + archive.name + "\n", encoding="ascii")
    print(json.dumps(dict(receipt, archive=str(archive), archive_bytes=archive.stat().st_size,
                          archive_sha256=sha256, archive_format=args.format), indent=2))


if __name__ == "__main__":
    main()
