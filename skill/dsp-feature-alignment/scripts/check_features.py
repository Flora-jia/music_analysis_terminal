"""Portable NumPy numerical reference utilities; caller supplies formats/scales."""
from pathlib import Path
import argparse,json
import numpy as np

def restore_bfp(raw,exponents,fractional_bits):
    raw=np.asarray(raw);e=np.asarray(exponents)
    if raw.ndim!=2 or e.shape!=(raw.shape[1],):raise ValueError('expected raw (bins,frames), exponents (frames,)')
    if raw.dtype.kind!='u':raise ValueError('raw power must be UNSIGNED integer; do not reinterpret as signed')
    if not 0<=fractional_bits<=63 or e.dtype.kind not in 'iu' or np.any(e<0) or np.any(e>63):raise ValueError('unsupported exponent/fractional format')
    out=np.ldexp(raw.astype(np.float64),2*e.astype(np.int64)[None,:]-2*fractional_bits)
    if not np.isfinite(out).all():raise ValueError('nonfinite restored power')
    return out
def logmel(power,matrix,range_db=80.):
    p=np.asarray(power,dtype=np.float64);m=np.asarray(matrix,dtype=np.float64)
    if p.ndim!=2 or m.ndim!=2 or m.shape[1]!=p.shape[0] or p.size==0:raise ValueError('mel matrix/bin shape mismatch')
    if range_db<=0 or not np.isfinite(p).all() or not np.isfinite(m).all() or np.any(p<0) or np.any(m<0):raise ValueError('invalid power/mel/range')
    db=10*np.log10(np.maximum(1e-10,m@p));db-=db.max()
    return np.clip((db+range_db)/range_db,0,1).astype(np.float32)
def compare(actual,expected,atol,rtol):
    a=np.asarray(actual);b=np.asarray(expected)
    if a.shape!=b.shape:return {'passed':False,'reason':'shape','actual_shape':list(a.shape),'expected_shape':list(b.shape)}
    if a.size==0 or not np.isfinite(a).all() or not np.isfinite(b).all():return {'passed':False,'reason':'empty_or_nonfinite'}
    # Preserve imaginary parts when comparing complex FFT golden references.
    d=np.abs(a.astype(np.complex128)-b.astype(np.complex128));limit=atol+rtol*np.abs(b)
    return {'passed':bool(np.all(d<=limit)),'max_abs_error':float(d.max()),'mismatched_elements':int(np.sum(d>limit)),
            'shape':list(a.shape),'atol':atol,'rtol':rtol,'scope':'numerical equality of supplied arrays, not task accuracy'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--actual',type=Path,required=True);p.add_argument('--expected',type=Path,required=True)
    p.add_argument('--atol',type=float,required=True);p.add_argument('--rtol',type=float,default=0);p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.atol<0 or a.rtol<0:raise SystemExit('tolerances must be nonnegative')
    r=compare(np.load(a.actual,allow_pickle=False),np.load(a.expected,allow_pickle=False),a.atol,a.rtol);text=json.dumps(r,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
    if not r['passed']:raise SystemExit(1)
if __name__=='__main__':main()
