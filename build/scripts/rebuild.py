"""Portable Vivado entry. New build outputs never replace the frozen runtime."""
from pathlib import Path
import argparse,os,shutil,subprocess,sys,hashlib,json,datetime
ROOT=Path(__file__).resolve().parents[2]
def vivado_root(explicit=None):
    choices=[explicit,os.getenv('MUSIC_VIVADO_ROOT'),os.getenv('XILINX_VIVADO')]
    exe=shutil.which('vivado') or shutil.which('vivado.bat')
    if exe:choices.append(str(Path(exe).resolve().parents[1]))
    for x in choices:
        if x and (Path(x)/'bin'/('vivado.bat' if os.name=='nt' else 'vivado')).is_file():return Path(x).resolve()
    raise SystemExit('Set MUSIC_VIVADO_ROOT to Vivado 2020.2 installation (or pass --vivado-root).')
def tool_command(root,tool,args):
    entry=root/'bin'/(tool+('.bat' if os.name=='nt' else ''))
    if os.name=='nt':return [os.environ.get('COMSPEC','cmd.exe'),'/d','/s','/c',subprocess.list2cmdline([str(entry)]+list(map(str,args)))]
    return [str(entry)]+list(map(str,args))
def main():
    p=argparse.ArgumentParser();p.add_argument('--vivado-root');p.add_argument('--out',type=Path,default=ROOT/'build/work/pl_rebuild')
    p.add_argument('--create-only',action='store_true');p.add_argument('--jobs',type=int,default=4);a=p.parse_args()
    out=a.out.resolve()
    if out.exists():raise SystemExit('Use a NEW output directory; refusing to overwrite '+str(out))
    if not 1<=a.jobs<=32:raise SystemExit('jobs must be 1..32')
    tool=vivado_root(a.vivado_root);out.mkdir(parents=True)
    env=os.environ.copy()
    # Remove stale patch lookup overrides; leave licensing and installed tool setup intact.
    for k in list(env):
        if k.upper() in ('MYVIVADO','MYXILINX','XILINX_PATH') or k.startswith('RDI_'):env.pop(k,None)
    args=['-mode','batch','-notrace','-source',ROOT/'build/scripts/rebuild.tcl','-log',out/'vivado.log','-journal',out/'vivado.jou',
          '-tclargs','create' if a.create_only else 'full',out,str(a.jobs)]
    rc=subprocess.run(tool_command(tool,'vivado',args),cwd=out,env=env).returncode
    if rc:raise SystemExit(rc)
    receipt={'date_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'mode':'create' if a.create_only else 'full',
             'vivado_root':str(tool),'source_release':'20261102-r6-freeze','board_runtime_modified':False}
    if not a.create_only:
        receipt['artifacts']={n:{'sha256':hashlib.sha256((out/'artifacts'/n).read_bytes()).hexdigest(),
                                'matches_frozen':(out/'artifacts'/n).read_bytes()==(ROOT/'board/artifacts'/n).read_bytes()}
                              for n in ['audio_merged.bit','audio_merged.hwh']}
    (out/'build_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('CREATE_PROJECT_OK' if a.create_only else 'REBUILD_OK',out)
if __name__=='__main__':main()
