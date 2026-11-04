"""Check all listed skill files; extra user-generated test outputs are ignored."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def main():
    manifest=json.loads((ROOT/'skill_manifest.json').read_text(encoding='utf-8'));errors=[]
    for name,value in manifest['files'].items():
        path=(ROOT/name).resolve()
        if ROOT.resolve() not in path.parents or not path.is_file():errors.append('missing/unsafe '+name)
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=value['sha256']:errors.append('changed '+name)
    if errors:raise SystemExit('\n'.join(errors))
    print('SKILL_PACKAGE_VERIFY_OK',len(manifest['files']))
if __name__=='__main__':main()
