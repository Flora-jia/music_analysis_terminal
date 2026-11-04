"""Recompile native code into a new directory; do not alter frozen .so/manifest."""
from pathlib import Path
import argparse,ctypes,hashlib,json,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--host-cc',default=os.getenv('MUSIC_HOST_CC'))
    p.add_argument('--arm-cc',default=os.getenv('MUSIC_ARM_CC'));p.add_argument('--out',type=Path,default=ROOT/'build/work/native')
    a=p.parse_args();src=ROOT/'src/ps/native';out=a.out.resolve()
    if out.exists():raise SystemExit('Use a NEW --out directory')
    if not a.host_cc and not a.arm_cc:raise SystemExit('Pass --host-cc and/or --arm-cc (or MUSIC_HOST_CC / MUSIC_ARM_CC)')
    manifest=json.loads((src/'core_manifest.json').read_text())
    for n,h in manifest.items():
        if hashlib.sha256((src/'core'/n).read_bytes()).hexdigest()!=h:raise SystemExit('Core changed: '+n)
    out.mkdir(parents=True)
    sources=[src/'pynq_wrapper.c']+[src/'core'/(n+'.c') for n in ['pitch_compare','onset_detector','note_tracker','note_event_queue','jianpu_map']]
    common=['-std=c99','-Wall','-Wextra','-O2','-I'+str(src),'-I'+str(src/'core')]+list(map(str,sources))
    results={}
    for kind,cc in [('host',a.host_cc),('arm',a.arm_cc)]:
        if not cc:continue
        cc=Path(cc).resolve()
        if kind=='host':
            target=out/('libmusic_ps_host.dll' if os.name=='nt' else 'libmusic_ps.so')
            flags=['-shared','-static-libgcc','-march=x86-64','-mtune=generic','-mno-avx','-fno-tree-vectorize']
            if os.name!='nt':flags+=['-fPIC']
        else:
            target=out/'libmusic_ps_arm.so'
            flags=['-include',str(src/'arm_compat.h'),'-shared','-fPIC','-mcpu=cortex-a9','-mfpu=vfpv3','-mfloat-abi=hard','-Wl,--no-undefined']
        env=os.environ.copy();env['PATH']=str(cc.parent)+os.pathsep+env.get('PATH','')
        cmd=[str(cc)]+common+flags+['-o',str(target),'-lm']
        run=subprocess.run(cmd,env=env,capture_output=True,text=True)
        (out/(kind+'_build.log')).write_text(subprocess.list2cmdline(cmd)+'\n'+run.stdout+run.stderr,encoding='utf-8')
        if run.returncode:raise SystemExit(kind+' compilation failed; see '+str(out))
        results[kind]={'file':target.name,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        if kind=='host':
            lib=ctypes.CDLL(str(target));lib.mp_abi_version.restype=ctypes.c_uint32
            if lib.mp_abi_version()!=2:raise SystemExit('Unexpected native ABI')
    (out/'build_results.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
if __name__=='__main__':main()
