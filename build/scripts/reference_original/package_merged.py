"""Create an explicit-file PL delivery, with no recursive directory reads."""
from pathlib import Path
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as E

ROOT=Path(__file__).resolve().parent
HARDWARE=ROOT/'hardware'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

inputs=json.loads((ROOT/'merged_input_manifest.json').read_text(encoding='utf-8'))
for name,entry in inputs.items():
    if sha(ROOT/'merged_inputs'/name)!=entry['sha256']:raise RuntimeError('Source changed: '+name)
addresses={'axi_dma_0':0x40400000,'axi_dma_1':0x40410000,'lcd_vdma':0x43000000,
           'i2s_transmitter_0':0x43C00000,'i2s_receiver_0':0x43C10000,
           'lcd_vtc':0x43C20000,'speaker_core':0x43C30000}
root=E.parse(HARDWARE/'audio_merged.hwh').getroot()
actual={r.get('INSTANCE'):int(r.get('BASEVALUE'),16) for r in root.iter('MEMRANGE') if r.get('MEMTYPE')=='REGISTER'}
if actual!=addresses:raise RuntimeError('HWH address mismatch: '+repr(actual))
timing=(ROOT/'reports/timing_summary.rpt').read_text(encoding='utf-8',errors='replace')
if 'All user specified timing constraints are met.' not in timing:raise RuntimeError('Timing not passed')
skew=(ROOT/'reports/bus_skew.rpt').read_text(encoding='utf-8',errors='replace')
if 'VIOLATED' in skew:raise RuntimeError('Bus skew violation')
accepted=json.loads((ROOT/'reports/build_acceptance.json').read_text(encoding='utf-8'))
if not accepted['implementation_passed'] or sha(HARDWARE/'audio_merged.bit')!=accepted['bit_sha256'] or sha(HARDWARE/'audio_merged.hwh')!=accepted['hwh_sha256']:raise RuntimeError('Hardware acceptance mismatch')
if not (ROOT/'reports/project_reopen.log').is_file():raise RuntimeError('Missing project reopen check')
if 'MERGED_PROJECT_REOPEN_OK' not in (ROOT/'reports/project_reopen.log').read_text(encoding='utf-8',errors='replace'):raise RuntimeError('Project reopen check did not pass')
if 'PORTABLE_PROJECT_READY' not in (ROOT/'reports/portable_rebuild.log').read_text(encoding='utf-8',errors='replace'):raise RuntimeError('Portable BD rebuild did not pass')
for path,marker in [('reports/model_rtl.log','PASS: 63 frames'),('reports/spectrum_rtl.log','SPEC_RTL_PASS')]:
    if marker not in (ROOT/path).read_text(encoding='utf-8',errors='replace'):raise RuntimeError('Missing RTL pass '+path)

files=['hardware/audio_merged.bit','hardware/audio_merged.hwh','README_MERGED.md','START_HERE.md','API_INTERFACE.md',
       'merged_input_manifest.json','reports/timing_summary.rpt','reports/utilization.rpt',
       'reports/resources.rpt','reports/drc.rpt','reports/bus_skew.rpt','reports/build_acceptance.json',
       'reports/model_rtl.log','reports/spectrum_rtl.log',
       'tests/test_spectrum_protocol.c','tests/tb_spectrum_pack.v','tests/fixtures/spectrum_packets.hex',
       'reports/project_reopen.log','reports/portable_rebuild.log',
       'create_from_package.tcl','prepare_runs.tcl','finish_implementation.tcl','check_project.tcl',
       'run_xilinx.py','rebuild.cmd','package_merged.py','accept_build.py']
files+=['merged_inputs/'+name for name in inputs]
manifest={'schema':'ac820.three_in_one.pl.v1','date':'2026-10-31',
  'state':'hardware_and_software_integrated_offline_passed; board_acceptance_pending',
  'model_archive':'model_1024_peer_revision_2','addresses':{k:hex(v) for k,v in addresses.items()},
  'dma0':{'protocol':'SPEC v2','words':2065,'bytes':8260,'bins':2049,'fft_n':4096,'hop':512},
  'dma1':{'magic':'0xA55A0402','words':522,'bytes':2088,'bins':513,'frames_per_segment':63},
  'project':str(ROOT/'project/audio_merged.xpr'),'files':{}}
for name in files:
    p=ROOT/name;manifest['files'][name]={'sha256':sha(p),'bytes':p.stat().st_size}
(ROOT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
with zipfile.ZipFile(ROOT/'audio_three_in_one_PL.zip','w',zipfile.ZIP_DEFLATED) as z:
    for name in files+['delivery_manifest.json']:z.write(ROOT/name,'audio_three_in_one_PL/'+name)
with zipfile.ZipFile(ROOT/'audio_three_in_one_PL.zip') as z:
    if z.testzip():raise RuntimeError('Archive CRC mismatch')
print('THREE_IN_ONE_PACKAGE_READY',len(files),'files')
for name in ['audio_merged.bit','audio_merged.hwh']:print(name,sha(HARDWARE/name))
