"""Accept only a completed timing-checked rebuild and pair its runtime files."""
from pathlib import Path
import hashlib,json,re,shutil
ROOT=Path(__file__).resolve().parent
def main():
    text=(ROOT/'reports/implementation_console.log').read_text(encoding='utf-8',errors='replace')
    if 'THREE_IN_ONE_BUILD_OK: exported timing-checked bit/HWH pair.' not in text:raise RuntimeError('Incomplete implementation')
    timing=(ROOT/'reports/timing_summary.rpt').read_text(encoding='utf-8',errors='replace')
    if 'All user specified timing constraints are met.' not in timing:raise RuntimeError('Timing not passed')
    slack={}
    for kind in ('max','min'):
        values=re.findall(r'MERGED_TIMING_'+kind+r'=([-+0-9.eE]+)',text)
        if not values or float(values[-1])<0:raise RuntimeError('Missing/passing slack: '+kind)
        slack[kind]=float(values[-1])
    item={'implementation_passed':True,'setup_ns':slack['max'],'hold_ns':slack['min']}
    for suffix in ('bit','hwh'):
        source=ROOT/'hardware'/('audio_merged.'+suffix)
        item[suffix+'_sha256']=hashlib.sha256(source.read_bytes()).hexdigest()
        if (ROOT/'runtime').is_dir():shutil.copyfile(source,ROOT/'runtime'/source.name)
    (ROOT/'reports/build_acceptance.json').write_text(json.dumps(item,indent=2),encoding='utf-8')
    print('HARDWARE_REBUILD_ACCEPTED')
if __name__=='__main__':main()
