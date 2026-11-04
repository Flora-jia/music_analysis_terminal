"""Re-run all portable CLI examples and recorded-data cases from this directory."""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args();out=a.out.resolve()
    if out.exists():raise SystemExit('Use a new output directory')
    out.mkdir(parents=True)
    cases=[
        ('layout',['tests/validate_layout.py'],0),
        ('overlay',['pynq-portable-bringup/scripts/inspect_overlay.py','--root','pynq-portable-bringup/examples/offline_fixture','--spec','pynq-portable-bringup/examples/offline_fixture/spec.json'],0),
        ('frames',['axis-frame-validation/scripts/check_frames.py','--frames','axis-frame-validation/examples/frames.jsonl','--contract','axis-frame-validation/examples/contract.json'],0),
        ('features',['dsp-feature-alignment/scripts/check_features.py','--actual','dsp-feature-alignment/examples/actual.npy','--expected','dsp-feature-alignment/examples/expected.npy','--atol','1e-6'],0),
        ('timing',['build-evidence-review/scripts/audit_build.py','--root','build-evidence-review/examples/complete','--spec','build-evidence-review/examples/complete/receipt.json'],0),
        ('historical_timing',['build-evidence-review/scripts/audit_build.py','--root','evidence','--spec','validation/historical_timing_spec.json'],1),
        ('historical_magnitude',['dsp-feature-alignment/scripts/check_features.py','--actual','evidence/historical_magnitude_actual.npy','--expected','evidence/historical_magnitude_expected.npy','--atol','8'],0),
        ('historical_adapter',['examples/project_adapters/spec_v2_to_jsonl.py','--input','evidence/spectrum_packets.hex','--out',str(out/'frames.jsonl')],0),
        ('historical_frames',['axis-frame-validation/scripts/check_frames.py','--frames',str(out/'frames.jsonl'),'--contract','validation/historical_frame_contract.json'],0),
    ]
    results=[]
    for name,args,expected in cases:
        run=subprocess.run([sys.executable,'-B','-X','utf8']+args,cwd=ROOT,capture_output=True,text=True)
        (out/(name+'.log')).write_text(run.stdout+run.stderr,encoding='utf-8')
        results.append({'case':name,'expected_exit':expected,'actual_exit':run.returncode,'passed':run.returncode==expected})
        if run.returncode!=expected:raise RuntimeError(name+': inspect '+str(out))
    (out/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print('CLI_REPLAY_OK',len(results))
if __name__=='__main__':main()
