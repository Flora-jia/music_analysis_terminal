"""Dependency-free validation of this package's two-scalar SKILL frontmatter.
Not a general YAML parser. Reject unfamiliar metadata instead of guessing.
"""
from pathlib import Path
import argparse,json,re
ROOT=Path(__file__).resolve().parents[1]
NAMES=['pynq-portable-bringup','axis-frame-validation','dsp-feature-alignment','build-evidence-review']
def validate(root):
    results=[]
    for name in NAMES:
        directory=root/name;errors=[];text=(directory/'SKILL.md').read_text(encoding='utf-8')
        m=re.match(r'^---\n(.*?)\n---\n',text,re.S)
        fields={}
        if not m:errors.append('frontmatter missing')
        else:
            for line in m.group(1).splitlines():
                match=re.fullmatch(r'(name|description): ([^\n]+)',line)
                if not match:errors.append('unsupported frontmatter line');continue
                key,value=match.groups()
                if key in fields:errors.append('duplicate field')
                fields[key]=value
        if fields.get('name')!=name or not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',fields.get('name','')) or len(name)>64:errors.append('skill name')
        d=fields.get('description','')
        if not d or len(d)>1024 or '<' in d or '>' in d:errors.append('description')
        if re.search(r'^\s*\[TODO:',text,re.M):errors.append('unfinished scaffold')
        if not (directory/'README.md').is_file():errors.append('README missing')
        results.append({'skill':name,'passed':not errors,'errors':errors})
    return results
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path);a=p.parse_args()
    r={'checks':validate(a.root),'scope':'restricted name/description frontmatter and required files; not generic YAML parsing'}
    text=json.dumps(r,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
    if not all(x['passed'] for x in r['checks']):raise SystemExit(1)
