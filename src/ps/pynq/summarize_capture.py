"""Summarize one explicitly named capture; never enumerate directories."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import zipfile
import numpy as np
from instrument_capture import LABELS,atomic_json

def summarize(directory,verify=False,low_margin=.15,high_confidence=.8):
    root=Path(directory).resolve()
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema')!='ac820.instrument_capture.v1':raise ValueError('Unknown capture schema')
    index=root/'segments.jsonl'
    rows=[json.loads(line) for line in index.read_text(encoding='utf-8').splitlines() if line.strip()] if index.is_file() else []
    reviewed_correct=0;reviewed_confusion={};reviewed_changes=0
    matrix=None
    if verify:
        pair=manifest.get('metadata',{}).get('paired_artifacts',{}).get('models/mel_matrix.npy')
        if pair:
            matrix_path=Path(__file__).resolve().parent/'models/mel_matrix.npy'
            if hashlib.sha256(matrix_path.read_bytes()).hexdigest()!=pair['sha256']:raise ValueError('Mel matrix hash mismatch')
            matrix=np.load(matrix_path,allow_pickle=False)
    confusion={};close=wrong_high=transitions=adjacent=correct=eligible=verified=0;previous=None;flat=[]
    for row in rows:
        if row['epoch']!=manifest['epoch'] or row['operator_label']!=manifest['operator_label']:
            raise ValueError('Mixed capture label or epoch')
        result=row['result'];d=row['diagnostics'];truth=row['operator_label'];pred=d['top1']
        if verify:
            path=(root/row['features_file']).resolve()
            if path.parent!=root:raise ValueError('Invalid feature path')
            if hashlib.sha256(path.read_bytes()).hexdigest()!=row['features_sha256']:raise ValueError('Feature hash mismatch')
            with np.load(path,allow_pickle=False) as z:
                if z['mel'].shape!=(64,63) or z['power'].shape!=(513,63) or z['exponents'].shape!=(63,):
                    raise ValueError('Feature shape mismatch')
                if z['mel'].dtype!=np.float32 or not all(np.isfinite(z[k]).all() for k in ('power','mel','exponents')):
                    raise ValueError('Invalid feature contents')
                if matrix is not None:
                    from pl_fft import power_to_mel
                    if not np.allclose(power_to_mel(z['power'],matrix),z['mel'],rtol=0,atol=2e-6):raise ValueError('Saved Mel differs from actual power preprocessing')
            verified+=1
        is_eligible=bool(row['training_eligible_three_class'] and pred)
        if is_eligible:
            eligible+=1;correct+=pred==truth
            confusion.setdefault(truth,{})[pred]=confusion.get(truth,{}).get(pred,0)+1
            reviewed=result.get('label',pred)
            reviewed_correct+=reviewed==truth
            reviewed_changes+=reviewed!=pred
            reviewed_confusion.setdefault(truth,{})[reviewed]=reviewed_confusion.get(truth,{}).get(reviewed,0)+1
            close+=d['top1_top2_margin']<low_margin
            wrong_high+=pred!=truth and d['top1_probability']>=high_confidence
        segment=int(result['segment'])
        if previous and pred and previous[1] and not result.get('gap') and (segment-previous[0])&0xffffffff==1:
            adjacent+=1;transitions+=pred!=previous[1]
        previous=(segment,pred)
        probs=result.get('cnn_probabilities') or result.get('probabilities') or {}
        flat.append(dict(record_id=row['record_id'],truth=truth,prediction=pred,reviewed_prediction=result.get('label',pred),
            decision_source=result.get('decision_source','cnn'),piano_review_applied=bool(result.get('piano_review',{}).get('applied')),
            piano_support_applied=bool(result.get('piano_support',{}).get('applied')),segment=segment,
            rms_est=result.get('rms_est'),margin=d['top1_top2_margin'],
            **{k+'_probability':probs.get(k) for k in LABELS},
            reference_label=result.get('reference_label'),reference_similarity=result.get('reference_similarity'),
            capture_to_result_ms=result.get('capture_to_result_ms'),inference_queue_drops=result.get('inference_queue_drops'),
            feature_file=row['features_file'],training_eligible=is_eligible))
    report=dict(schema='ac820.instrument_diagnostics.v1',epoch=manifest['epoch'],operator_label=manifest['operator_label'],
        recorded_segments=len(rows),verified_feature_files=verified,eligible_segments=eligible,correct_segments=correct,
        accuracy=correct/eligible if eligible else None,confusion=confusion,
        reviewed_correct_segments=reviewed_correct,reviewed_accuracy=reviewed_correct/eligible if eligible else None,
        reviewed_confusion=reviewed_confusion,reviewed_changed_segments=reviewed_changes,low_margin_segments=close,
        high_confidence_wrong_segments=wrong_high,adjacent_pairs=adjacent,label_transitions=transitions,
        transition_rate=transitions/adjacent if adjacent else None,capture_status=manifest.get('status'),
        diagnostic_thresholds=dict(low_margin=low_margin,high_confidence=high_confidence),
        caveat='Thresholds are diagnostics only, not calibrated rejection rules; one run is not general accuracy.')
    atomic_json(root/'diagnostic_report.json',report)
    if flat:
        with (root/'diagnostic_segments.csv').open('w',encoding='utf-8-sig',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    return report

def export_capture(directory,target):
    root=Path(directory).resolve()
    rows=[json.loads(line) for line in (root/'segments.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()] if (root/'segments.jsonl').is_file() else []
    names=['manifest.json','segments.jsonl','diagnostic_report.json','diagnostic_segments.csv']
    names+=[row['features_file'] for row in rows]
    with zipfile.ZipFile(target,'x',zipfile.ZIP_DEFLATED) as z:
        for name in dict.fromkeys(names):
            path=(root/name).resolve()
            if path.parent!=root:raise ValueError('Invalid export path')
            if path.is_file():z.write(path,root.name+'/'+name)
    return str(target)

def main():
    p=argparse.ArgumentParser(description='Summarize a completed labeled feature capture')
    p.add_argument('directory');p.add_argument('--verify',action='store_true');p.add_argument('--export',dest='export_path')
    args=p.parse_args()
    print(json.dumps(summarize(args.directory,args.verify),ensure_ascii=True,indent=2))
    if args.export_path:print('CAPTURE_EXPORTED:',export_capture(args.directory,args.export_path))
if __name__=='__main__':main()
