"""Launch the unmodified frozen runtime and tee CLI output to a new log.
Use Jupyter START.ipynb for interactive control; do not run both entries.
"""
from pathlib import Path
import argparse,datetime,os,subprocess,sys,json
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--log-dir',type=Path);a,forward=p.parse_known_args()
    if forward[:1]==['--']:forward=forward[1:]
    folder=a.log_dir or ROOT/'board/results/current_r6'/datetime.datetime.now().strftime('run_%Y%m%d_%H%M%S')
    folder.mkdir(parents=True,exist_ok=False)
    cmd=[sys.executable,'-B','-u',str(ROOT/'board/runtime/run_live_system.py')]+forward
    (folder/'run_arguments.json').write_text(json.dumps({'arguments':forward,'command':cmd},ensure_ascii=False,indent=2),encoding='utf-8')
    # SIGINT reaches both foreground processes; keep reading the child's graceful stop log.
    child=subprocess.Popen(cmd,cwd=ROOT/'board/runtime',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    with (folder/'console.log').open('w',encoding='utf-8') as log:
        while True:
            try:
                line=child.stdout.readline()
                if not line:break
                print(line,end='',flush=True);log.write(line);log.flush()
            except KeyboardInterrupt:
                if os.name=='nt':child.terminate()
                continue
    rc=child.wait();print('Board entry exit:',rc,'log:',folder)
    raise SystemExit(rc)
if __name__=='__main__':main()
