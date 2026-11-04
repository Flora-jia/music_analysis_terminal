"""Parse Vivado text timing summary + enforce a caller-supplied file receipt.
Positive constrained slack and IO constraint completeness are separate results.
"""
from pathlib import Path
import argparse,hashlib,json,re

def timing_metrics(text):
    lines=text.splitlines();metrics=None
    for i,line in enumerate(lines):
        if line.strip().startswith('WNS(ns)') and 'WHS(ns)' in line:
            for candidate in lines[i+1:i+7]:
                fields=candidate.split()
                if len(fields)>=8:
                    try:values=[float(v) for v in fields]
                    except ValueError:continue
                    metrics=dict(wns_ns=values[0],tns_ns=values[1],whs_ns=values[4],ths_ns=values[5]);break
            if metrics:break
    if metrics is None:raise ValueError('Unsupported/missing Vivado timing summary table; do not assume pass')
    coverage={}
    for key in ['no_clock','unconstrained_internal_endpoints','no_input_delay','no_output_delay','partial_input_delay','partial_output_delay']:
        found=re.search(r'checking\s+'+key+r'\s*\((\d+)\)',text)
        coverage[key]=int(found.group(1)) if found else None
    clocks=[]
    for line in lines:
        match=re.match(r'\s*(\S+)\s+\{[^}]+\}\s+([0-9.]+)\s+([0-9.]+)\s*$',line)
        if match:clocks.append({'name':match.group(1),'period_ns':float(match.group(2)),'frequency_mhz':float(match.group(3))})
    return metrics,coverage,clocks
def audit(root,spec):
    root=Path(root).resolve();errors=[]
    def path(name):
        p=(root/name).resolve()
        if root not in p.parents:raise ValueError('path escapes root')
        return p
    for n,h in spec['files'].items():
        p=path(n)
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=h:errors.append('receipt_mismatch:'+n)
    if spec['timing_report'] not in spec['files']:errors.append('timing_report_not_bound_to_receipt')
    metrics,coverage,clocks=timing_metrics(path(spec['timing_report']).read_text(encoding='utf-8',errors='replace'))
    if any(metrics[k]<0 for k in ('wns_ns','whs_ns')) or any(metrics[k]!=0 for k in ('tns_ns','ths_ns')):errors.append('constrained_timing_failed')
    missing=[k for k,v in coverage.items() if v is None or v>0]
    if spec.get('require_complete_constraints',True) and missing:errors.append('constraint_coverage_requires_review')
    return {'passed':not errors,'errors':errors,'timing':metrics,'constraint_checks':coverage,'constraint_review_items':missing,'clocks':clocks,
            'scope':'receipt and parsed timing checks only; does not prove source-to-bit regeneration, CDC correctness or board electrical timing'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args();r=audit(a.root,json.loads(a.spec.read_text(encoding='utf-8')));text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
    if not r['passed']:raise SystemExit(1)
if __name__=='__main__':main()
