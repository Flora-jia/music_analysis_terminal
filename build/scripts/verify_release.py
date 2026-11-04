"""Verify the frozen release on PC or board without importing PYNQ."""
from pathlib import Path
import argparse,hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for chunk in iter(lambda:stream.read(8*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def verify(root=ROOT):
    data=json.loads((root/'release_manifest.json').read_text(encoding='utf-8'))
    errors=[]
    for n,v in data['files'].items():
        p=(root/n).resolve()
        if root.resolve() not in p.parents or not p.is_file():errors.append('missing/invalid '+n)
        elif digest(p)!=v['sha256']:errors.append('changed '+n)
    runtime=root/'board/runtime'
    bundle=json.loads((runtime/'manifest_board.json').read_text())
    if bundle.get('software_release')!='20261101-R6':errors.append('Wrong software release')
    for n,v in bundle['files'].items():
        if digest(runtime/n)!=v['sha256']:errors.append('runtime manifest '+n)
    for ext in ('bit','hwh'):
        if digest(root/'board/artifacts'/('audio_merged.'+ext))!=digest(runtime/('audio_merged.'+ext)):errors.append('artifact pairing '+ext)
    if errors:raise RuntimeError('\n'.join(errors))
    return {'release':data['release'],'verified_files':len(data['files']),'runtime_release':bundle['software_release']}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);a=p.parse_args()
    print('RELEASE_VERIFY_OK',json.dumps(verify(a.root.resolve())))
