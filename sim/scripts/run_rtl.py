"""Re-run the actual protocol/stall/drop testbenches with Vivado xsim.
1024 FFT is mocked by its testbench; this does not verify XFFT arithmetic.
"""
from pathlib import Path
import argparse,os,subprocess,sys,json
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'build/scripts'))
from rebuild import vivado_root,tool_command
def main():
    p=argparse.ArgumentParser();p.add_argument('--vivado-root');p.add_argument('--out',type=Path,default=ROOT/'sim/results/rtl_rerun');a=p.parse_args()
    out=a.out.resolve()
    if out.exists():raise SystemExit('Use a NEW --out directory')
    out.mkdir(parents=True);tool=vivado_root(a.vivado_root);rtl=ROOT/'src/rtl';tb=ROOT/'sim/testbench'
    cases=[('spectrum','tb_spectrum_pack',[tb/'tb_spectrum_pack.v',rtl/'spectrum_frame_pack.v'],'SPEC_RTL_PASS'),
           ('model','tb_fft_protocol',[tb/'tb_fft_protocol.v',rtl/'music_fft1024_batch.v',rtl/'music_pcm_segments.v',rtl/'hann_coef_rom.v'],'PASS: 63 frames')]
    summary={}
    for name,top,files,marker in cases:
        work=out/name;work.mkdir();logs=[]
        for app,args in [('xvlog',['--sv']+files),('xelab',[top,'-s',top+'_snapshot']),('xsim',[top+'_snapshot','-runall'])]:
            run=subprocess.run(tool_command(tool,app,args),cwd=work,capture_output=True,text=True)
            text=run.stdout+run.stderr;logs.append(text)
            (work/(app+'.log')).write_text(text,encoding='utf-8')
            if run.returncode:raise SystemExit(name+' '+app+' failed; see '+str(work))
        if marker not in '\n'.join(logs):raise SystemExit(name+' missing pass marker')
        summary[name]={'passed':True,'marker':marker,'scope':'control/protocol simulation; vendor FFT math not verified here'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
if __name__=='__main__':main()
