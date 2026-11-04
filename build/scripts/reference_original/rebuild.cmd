@echo off
setlocal
set "MERGE_ROOT=%~dp0"
pushd "%MERGE_ROOT%"
if not exist "%MERGE_ROOT%reports" mkdir "%MERGE_ROOT%reports"
if exist "%MERGE_ROOT%project\audio_merged.xpr" goto project_ready
python -B "%MERGE_ROOT%run_xilinx.py" vivado -mode batch -source "%MERGE_ROOT%create_from_package.tcl" -notrace
if errorlevel 1 goto failed
:project_ready
python -B "%MERGE_ROOT%run_xilinx.py" vivado -mode batch -source "%MERGE_ROOT%prepare_runs.tcl" -notrace
if errorlevel 1 goto failed
pushd "%MERGE_ROOT%project\audio_merged.runs\synth_1"
echo Synthesizing. See reports/synthesis_console.log.
python -B "%MERGE_ROOT%run_xilinx.py" vivado -mode batch -source audio_top.tcl -notrace > "%MERGE_ROOT%reports\synthesis_console.log" 2>&1
if errorlevel 1 goto failed_nested
popd
pushd "%MERGE_ROOT%project\audio_merged.runs\impl_1"
echo Implementing. See reports/implementation_console.log.
python -B "%MERGE_ROOT%run_xilinx.py" vivado -mode batch -source "%MERGE_ROOT%finish_implementation.tcl" -notrace > "%MERGE_ROOT%reports\implementation_console.log" 2>&1
if errorlevel 1 goto failed_nested
popd
python -B "%MERGE_ROOT%run_xilinx.py" vivado -mode batch -source "%MERGE_ROOT%check_project.tcl" -notrace > "%MERGE_ROOT%reports\project_reopen.log" 2>&1
if errorlevel 1 goto failed
python -B "%MERGE_ROOT%accept_build.py"
if errorlevel 1 goto failed
python -B "%MERGE_ROOT%package_merged.py"
if errorlevel 1 goto failed
popd
exit /b 0
:failed_nested
popd
:failed
popd
exit /b 1
