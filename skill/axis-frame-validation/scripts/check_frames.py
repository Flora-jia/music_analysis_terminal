"""Validate NORMALIZED complete-packet records, independent of a wire protocol.
Decoder belongs to the caller; sampled console summaries are not full packets.
"""
from pathlib import Path
import argparse,json,math

def check(frames,contract):
    if not all(isinstance(contract.get(k),int) and contract[k]>0 for k in ('bins','window_samples','hop_samples')):raise ValueError('positive integer contract fields required')
    errors=[];gaps=[];previous=None;count=0
    for index,f in enumerate(frames):
        count+=1;tag='record'+str(index)
        if not all(k in f for k in ('sequence','first_sample','sample_count','bins','values')):
            errors.append(tag+':missing_fields');continue
        bins=f['bins'];values=f['values'];n=contract['bins']
        if not all(isinstance(f[k],int) and not isinstance(f[k],bool) and f[k]>=0 for k in ('sequence','first_sample','sample_count')):
            errors.append(tag+':invalid_integer_metadata');continue
        if not isinstance(values,list) or any(not isinstance(v,(int,float)) or isinstance(v,bool) or not math.isfinite(v) or v<0 for v in values):
            errors.append(tag+':invalid_magnitude');continue
        if bins!=list(range(n)) or len(values)!=n:errors.append(tag+':point_count_or_bin_order')
        if f['sample_count']!=contract['window_samples']:errors.append(tag+':window_sample_count')
        if f.get('errors',0):errors.append(tag+':flagged_frame')
        seq=f['sequence'];first=f['first_sample'];epoch=f.get('epoch',0)
        if previous is not None and previous[2]==epoch:
            ds=seq-previous[0];dt=first-previous[1]
            if ds<=0:errors.append(tag+':sequence_not_increasing')
            elif dt!=ds*contract['hop_samples']:errors.append(tag+':sample_time_mismatch')
            elif ds>1:
                gaps.append({'after_sequence':previous[0],'missing_sequences':ds-1,'coverage':contract.get('coverage','all_packets')})
                if contract.get('coverage','all_packets')=='all_packets' and contract.get('require_drop_marker',True) and not f.get('whole_frame_drop',False):errors.append(tag+':unmarked_gap')
        expected=f.get('golden_values')
        if expected is not None and expected!=values:errors.append(tag+':golden_payload_mismatch')
        peak=contract.get('reference_peak')
        if peak and len(values)==n:
            best_bin=0;best=0
            for k in range(peak['first_bin'],peak['last_bin']+1):
                m=values[k]
                if m>=peak['threshold'] and m>best and m>=values[k-1] and m>values[k+1]:best_bin,best=k,m
            if f.get('reference_peak')!={'bin':best_bin,'value':best}:errors.append(tag+':same_frame_peak_mismatch')
        previous=(seq,first,epoch)
    if not count:errors.append('no_packets')
    return {'passed':not errors,'records':count,'errors':errors,'gaps':gaps,
            'scope':'normalized packet/index/time checks; mixed values only detected if distinguishable golden payload is provided'}
def main():
    p=argparse.ArgumentParser();p.add_argument('--frames',type=Path,required=True);p.add_argument('--contract',type=Path,required=True);p.add_argument('--out',type=Path)
    a=p.parse_args();rows=[json.loads(x) for x in a.frames.read_text(encoding='utf-8').splitlines() if x.strip()]
    r=check(rows,json.loads(a.contract.read_text(encoding='utf-8')));text=json.dumps(r,ensure_ascii=False,indent=2)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(text,encoding='utf-8')
    print(text)
    if not r['passed']:raise SystemExit(1)
if __name__=='__main__':main()
