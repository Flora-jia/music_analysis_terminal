"""Package all files recorded in the final submission manifest."""
from pathlib import Path
import argparse,hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_release import verify

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    verify(ROOT)
    if args.out.exists():raise SystemExit('Choose a NEW output archive')
    manifest=json.loads((ROOT/'release_manifest.json').read_text(encoding='utf-8'))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for name in list(manifest['files'])+['release_manifest.json']:
            archive.write(ROOT/name,'music_analysis_terminal/'+name)
    with zipfile.ZipFile(args.out) as archive:
        if archive.testzip():raise RuntimeError('Archive CRC check failed')
    digest=hashlib.sha256(args.out.read_bytes()).hexdigest()
    args.out.with_suffix(args.out.suffix+'.sha256').write_text(digest+'  '+args.out.name+'\n',encoding='ascii')
    print('SUBMISSION_ARCHIVE_OK',args.out,args.out.stat().st_size,digest)
if __name__=='__main__':main()
