"""Collect one board run through the packaged runtime entry.

The default runtime is board/runtime, relative to this collector's location.
"""
from pathlib import Path
import argparse,datetime,json,os,runpy,signal,sys,threading,zipfile

class Tee:
    def __init__(self,original,file,lock):self.original,self.file,self.lock=original,file,lock
    def write(self,value):
        with self.lock:self.original.write(value);self.file.write(value);self.file.flush()
        return len(value)
    def flush(self):
        with self.lock:self.original.flush();self.file.flush()
    def __getattr__(self,name):return getattr(self.original,name)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--runtime',type=Path,default=Path(__file__).resolve().parents[2]/'runtime')
    p.add_argument('--case',required=True)
    p.add_argument('--input',choices=['line','vitis'],default='line')
    p.add_argument('--piano-review',action='store_true')
    p.add_argument('--no-model',action='store_true')
    p.add_argument('--no-feature-recording',action='store_true',help='Keep model inference enabled, omit extra power/mel recording')
    p.add_argument('--headless',action='store_true')
    p.add_argument('--capture-label',choices=['piano','guitar','violin','silence','background','unlabeled'],default='unlabeled')
    p.add_argument('--capture-limit',type=int,default=120)
    p.add_argument('--note',default='')
    a=p.parse_args();runtime=a.runtime.resolve()
    if not (runtime/'run_live_system.py').is_file():raise SystemExit('Upload this collector beside the frozen run_live_system.py or pass --runtime')
    if not a.case or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in a.case):raise SystemExit('Use English letters, digits, underscore or hyphen in --case')
    folder=runtime/'acceptance_runs'/a.case
    if folder.exists():raise SystemExit('Case already exists; use a NEW --case to preserve evidence')
    folder.mkdir(parents=True)
    cmd=[str(runtime/'run_live_system.py'),'--ui-stats','--input',a.input,'--record-dir',str(folder/'music_records'),
         '--capture-label',a.capture_label,'--capture-limit',str(a.capture_limit),'--capture-dir',str(folder/'features'),'--capture-note',a.note]
    if a.no_model or a.no_feature_recording:
        cmd=cmd[:cmd.index('--capture-label')]
        cmd.extend(['--capture-note',a.note])
        if a.no_model:cmd.append('--no-model')
    if a.headless:cmd.append('--headless')
    if a.piano_review:cmd.append('--piano-review')
    info={'case':a.case,'command_argv':cmd,'runtime':str(runtime),'operator_label':a.capture_label,
          'board_wall_clock_started':datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'model_disabled':a.no_model,'feature_recording_enabled':not (a.no_model or a.no_feature_recording),'headless':a.headless,'state':'running','note':'Operator label is ground truth metadata; it is not supplied as an input to the classifier.'}
    (folder/'run_arguments.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    original_out,original_err=sys.stdout,sys.stderr
    old_argv,old_cwd=sys.argv[:],Path.cwd();old_signal=signal.getsignal(signal.SIGTERM)
    log=(folder/'console.log').open('w',encoding='utf-8');lock=threading.RLock()
    sys.stdout=Tee(original_out,log,lock);sys.stderr=Tee(original_err,log,lock)
    sys.path.insert(0,str(runtime));sys.argv=cmd;os.chdir(runtime)
    try:
        print('ACCEPTANCE_CASE:',a.case,'OUTPUT:',folder,flush=True)
        runpy.run_path(str(runtime/'run_live_system.py'),run_name='__main__')
        info['state']='entry_returned_normally'
    except BaseException as exc:
        info['state']='entry_failed';info['exception']=repr(exc)
        import traceback;traceback.print_exc()
        raise
    finally:
        # Production entry owns and stops hardware. Do not override its stop failure.
        info['board_wall_clock_ended']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        sys.stdout.flush();sys.stderr.flush();sys.stdout,sys.stderr=original_out,original_err
        sys.argv=old_argv;os.chdir(old_cwd);signal.signal(signal.SIGTERM,old_signal);log.close()
        (folder/'run_arguments.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        if info['state']=='entry_returned_normally':
            target=folder.with_suffix('.zip')
            with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
                for f in sorted(folder.rglob('*')):
                    if f.is_file():z.write(f,a.case+'/'+f.relative_to(folder).as_posix())
            print('ACCEPTANCE_SAVED:',target,flush=True)
        else:print('Case failed; keep its directory and console.log. No success ZIP generated:',folder,flush=True)

if __name__=='__main__':main()
