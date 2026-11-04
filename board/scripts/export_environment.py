"""Read-only environment export; no overlay or DMA access."""
from pathlib import Path
import argparse,datetime,importlib,importlib.metadata,json,platform,sys,os,hashlib
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'board/results/current_r6/environment.json');a=p.parse_args()
    if a.out.exists():raise SystemExit('Refusing to overwrite existing evidence; pass a new --out path')
    versions={}
    for name in ['pynq','numpy','Pillow','cffi','ipykernel','jupyter']:
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:versions[name]=None
    data={'captured_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':sys.version,'executable':sys.executable,
          'platform':platform.platform(),'machine':platform.machine(),'uname':dict(zip(platform.uname()._fields,platform.uname())),
          'packages':versions,'uid':os.getuid() if hasattr(os,'getuid') else None,'board_image_identifier':'RECORD_SD_IMAGE_FILENAME_AND_SOURCE_MANUALLY'}
    data['runtime_hashes']={n:hashlib.sha256((ROOT/'board/runtime'/n).read_bytes()).hexdigest() for n in ['audio_merged.bit','audio_merged.hwh','manifest_board.json']}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    print(a.out)
if __name__=='__main__':main()
