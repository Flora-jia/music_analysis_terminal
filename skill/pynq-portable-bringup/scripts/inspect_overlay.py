"""Offline artifact + HWH register-map inspection. No PYNQ import/download.
Contract paths are relative to --root; no board, IP instance or address is fixed.
"""
from pathlib import Path
import argparse,hashlib,json,xml.etree.ElementTree as ET

def safe_path(root,name):
    p=(root/name).resolve()
    if root.resolve() not in p.parents:raise ValueError('Artifact escapes root: '+name)
    return p

def inspect(root,spec):
    root=Path(root).resolve();errors=[];checked=[]
    for name,digest in spec['artifacts'].items():
        p=safe_path(root,name)
        if not p.is_file():errors.append('missing:'+name);continue
        actual=hashlib.sha256(p.read_bytes()).hexdigest();checked.append(name)
        if actual!=digest:errors.append('hash_mismatch:'+name)
    hwh=safe_path(root,spec['hwh'])
    if spec['hwh'] not in spec['artifacts']:errors.append('hwh_not_hash_bound')
    registers={}
    for node in ET.parse(hwh).getroot().iter():
        if node.tag.rsplit('}',1)[-1]!='MEMRANGE' or node.get('MEMTYPE')!='REGISTER':continue
        name=node.get('INSTANCE');base=node.get('BASEVALUE')
        if name and base:registers.setdefault(name,set()).add(int(base,0))
    for name,expected in spec.get('expected_ips',{}).items():
        wanted=int(expected,0) if isinstance(expected,str) else int(expected)
        if registers.get(name)!= {wanted}:errors.append('ip_address_mismatch:'+name)
    return {'passed':not errors,'errors':errors,'checked_files':checked,
            'register_map':{k:[hex(v) for v in sorted(a)] for k,a in registers.items()},
            'scope':'offline bytes and HWH metadata only; does not prove the bit encodes this HWH or is loaded on hardware'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args();r=inspect(a.root,json.loads(a.spec.read_text(encoding='utf-8')))
    text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
    if not r['passed']:raise SystemExit(1)
if __name__=='__main__':main()
