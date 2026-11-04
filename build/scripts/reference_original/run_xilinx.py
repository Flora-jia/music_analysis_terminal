"""Run the local 2020.2 tools without inheriting stale Xilinx patch settings."""
import os
import subprocess
import sys
root='D:/Xilinx/Vivado/2020.2'
env=os.environ.copy()
env.setdefault('SYSTEMROOT','C:\\Windows')
env.setdefault('WINDIR',env['SYSTEMROOT'])
for key in list(env):
    if key.upper() in ('MYVIVADO','MYXILINX','XILINX_PATH') or key.startswith('RDI_'):
        env.pop(key,None)
if '--batch-wrapper' in sys.argv:
    winroot=env.get('SYSTEMROOT','C:/Windows')
    env['SYSTEMROOT']=winroot
    env['PATH']=os.path.join(winroot,'System32')+';'+winroot
    env.pop('XILINX_HLS',None)
    command=subprocess.list2cmdline([os.path.normpath(root+'/bin/'+sys.argv[1]+'.bat')]+sys.argv[2:-1])
    sys.exit(subprocess.run([env.get('COMSPEC','cmd.exe'),'/d','/c',command],env=env).returncode)
env.update(XILINX_VIVADO=root,RDI_APPROOT=root,RDI_BINROOT=root+'/bin',
           RDI_BASEROOT='D:/Xilinx/Vivado',HDI_APPROOT=root,RDI_PROG=sys.argv[1],
           RDI_DATADIR=root+'/data',RDI_LIBDIR=root+'/lib/win64.o',
           RDI_BINDIR=root+'/bin',RDI_PLATFORM='win64',RDI_OPT_EXT='.o',
           XILINX=root,TCL_LIBRARY=root+'/tps/tcl/tcl8.5')
env.update(RDI_JAVAROOT=root+'/tps/win64/jre11.0.2',RDI_JAVA_VERSION='11.0.2',
           RT_LIBPATH=root+'/scripts/rt/data',RT_TCL_PATH=root+'/scripts/rt/base_tcl/tcl',
           RDI_PROGNAME=sys.argv[1]+'.exe')
env.update(XILINX=root+'/ids_lite/ISE',RDI_INSTALLROOT='D:/Xilinx',
           RDI_INSTALLVER='2020.2',RDI_INSTALLVERSION='2020.2',RDI_USE_JDK11='1',RDI_BUILD='yes')
env.update(PYTHONHOME=root+'/tps/win64/python-3.8.3',
           PYTHONPATH=root+'/tps/win64/python-3.8.3/lib;'+root+'/tps/win64/python-3.8.3/lib/site-packages')
env['PATH']=(';'.join((root+'/lib/win64.o',root+'/bin',
    root+'/tps/mingw/6.2.0/win64.o/nt/bin',
    root+'/tps/mingw/6.2.0/win64.o/nt/libexec/gcc/x86_64-w64-mingw32/6.2.0',
    root+'/tps/win64/jre11.0.2/bin/server',root+'/tps/win64/jre11.0.2/bin',
    root+'/tps/win64/python-3.8.3',root+'/tps/win64/python-3.8.3/bin'))
    +';'+env.get('PATH','').replace('"',''))
if sys.argv[1]=='kernel':
    import threading
    child=subprocess.Popen([sys.argv[2]],env=env,stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
    guard=threading.Timer(50,child.kill);guard.start();log=[]
    def wait_for(marker):
        while True:
            line=child.stdout.readline()
            if not line:raise RuntimeError('Kernel closed before '+marker)
            log.append(line)
            if marker in line:return
    try:
        wait_for('elaboration-done')
        child.stdin.write('-exec-run\n');child.stdin.flush();wait_for('*stopped')
        child.stdin.write('-exec-continue -time 20000000000\n');child.stdin.flush();wait_for('*stopped')
        child.stdin.write('-gdb-exit\n');child.stdin.flush()
        remaining=child.communicate(timeout=5)[0];log.append(remaining)
        text=''.join(log);open('rtl_simulation.log','w').write(text);print(text)
        if not any(x in text for x in ('PCM_RTL_PASS','SPEC_RTL_PASS','PASS: 63 frames')):raise RuntimeError('RTL testbench did not pass')
        result=child
    finally:
        guard.cancel()
        if child.poll() is None:child.kill()
else:
    result=subprocess.run([root+'/bin/unwrapped/win64.o/'+sys.argv[1]+'.exe']+sys.argv[2:],env=env)
sys.exit(result.returncode)
