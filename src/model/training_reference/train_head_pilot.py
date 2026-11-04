from pathlib import Path
import sys,json,zipfile,io,hashlib,collections
import numpy as np
ROOT=Path(r'D:/project/audio_f0923/audio/audio/pl_merge_20261031')
OUT=ROOT/'head_adaptation_20261101';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(ROOT/'runtime'))
from infer_numpy import NumpyInstrumentClassifier
from reference_infer import ReferenceModel
from pl_fft import power_to_mel
BASE=NumpyInstrumentClassifier(ROOT/'runtime/models/cnn_weights.npz',ROOT/'runtime/models/model_meta.json')
REF=ReferenceModel(BASE,ROOT/'runtime/models',ROOT/'runtime/reference')
MATRIX=np.load(ROOT/'runtime/models/mel_matrix.npy')
NOTES=['C4','D4','E4','G4','A4']
rows=[];embeddings=[];mels=[]
for file,label,cutoff,expected in [('piano_phone_1.zip','piano',37,5),('guitar_phone.zip','guitar',None,10),('violin_phone.zip','violin',None,10)]:
    path=Path('D:/project')/file
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        idx=next(n for n in z.namelist() if n.endswith('/segments.jsonl'));prefix=idx.rsplit('/',1)[0]+'/'
        manifest=json.loads(z.read(prefix+'manifest.json'))
        records=[json.loads(l) for l in z.read(idx).decode().splitlines() if l]
        records=[x for x in records if (cutoff is None or x['result']['segment']<=cutoff) and x['diagnostics']['top1']]
        groups=[]
        for record in records:
            if not groups or record['result']['segment']!=groups[-1][-1]['result']['segment']+1:groups.append([])
            groups[-1].append(record)
        assert len(groups)==expected,(file,len(groups))
        for group_index,group in enumerate(groups):
            for record in group:
                raw=z.read(prefix+record['features_file']);assert hashlib.sha256(raw).hexdigest()==record['features_sha256']
                with np.load(io.BytesIO(raw),allow_pickle=False) as a:
                    mel=a['mel'].copy();assert np.allclose(power_to_mel(a['power'],MATRIX),mel,rtol=0,atol=2e-6)
                e,p=REF.encode(mel);note=NOTES[group_index%5]
                embeddings.append(e);mels.append(mel)
                rows.append(dict(label=label,note=note,source_group=label+':'+note,epoch=manifest['epoch'],segment=record['result']['segment'],record_id=record['record_id'],archive=str(path),features_sha256=record['features_sha256'],round=1+group_index//5))
E=np.asarray(embeddings,dtype=np.float64);X=np.asarray(mels,dtype=np.float32);y=np.array([BASE.labels.index(x['label']) for x in rows]);groups=np.array([x['note'] for x in rows])
R=np.load(ROOT/'runtime/reference/reference_bank.npz');A=np.asarray(R['embeddings'],dtype=np.float64);ay=np.asarray(R['label_indices'],dtype=int)
np.savez_compressed(OUT/'verified_features.npz',embeddings=E,mel=X,y=y,note_index=np.array([NOTES.index(x) for x in groups]))
(OUT/'samples.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')

def probs(e,w,b):
    logits=e@w+b;logits-=logits.max(axis=1,keepdims=True);q=np.exp(logits);return q/q.sum(axis=1,keepdims=True)
def balanced(y,src):
    w=np.zeros(len(y))
    for c in range(3):
        ids=sorted(set(src[y==c]))
        for g in ids:
            selected=(y==c)&(src==g);w[selected]=1/(3*len(ids)*selected.sum())
    return w
def fit(e,y,src,anchor_weight=.25):
    inputs=np.r_[e,A];targets=np.r_[y,ay]
    fw=balanced(y,src);aw=balanced(ay,np.array(['old:'+str(c) for c in ay]))
    weight=np.r_[fw*(1-anchor_weight),aw*anchor_weight]
    mean=np.mean(inputs,axis=0);scale=np.maximum(inputs.std(axis=0),.05)
    z=(inputs-mean)/scale
    w0=scale[:,None]*BASE.w['dense_w'];b0=mean@BASE.w['dense_w']+BASE.w['dense_b']
    w=w0.copy();b=b0.copy();mw=np.zeros_like(w);vw=np.zeros_like(w);mb=np.zeros_like(b);vb=np.zeros_like(b)
    target=np.eye(3)[targets]*.98+.02/3
    for step in range(1,801):
        p=probs(z,w,b);g=(p-target)*weight[:,None]
        dw=z.T@g+.001*(w-w0);db=g.sum(axis=0)+.001*(b-b0)
        mw=.9*mw+.1*dw;vw=.999*vw+.001*dw**2;mb=.9*mb+.1*db;vb=.999*vb+.001*db**2
        w-=.02*(mw/(1-.9**step))/(np.sqrt(vw/(1-.999**step))+1e-8)
        b-=.02*(mb/(1-.9**step))/(np.sqrt(vb/(1-.999**step))+1e-8)
    raw=w/scale[:,None];return raw,b-mean@raw

pred0=probs(E,BASE.w['dense_w'],BASE.w['dense_b']).argmax(axis=1)
pred=np.empty(len(y),dtype=int)
for note in NOTES:
    train=groups!=note;test=~train;w,b=fit(E[train],y[train],groups[train]);pred[test]=probs(E[test],w,b).argmax(axis=1)
    print('FOLD',note,'BASE',float(np.mean(pred0[test]==y[test])),'CANDIDATE',float(np.mean(pred[test]==y[test])))
def cm(y,p):
    x=np.zeros((3,3),dtype=int)
    for a,b in zip(y,p):x[a,b]+=1
    return x.tolist()
w,b=fit(E,y,groups)
print('COUNTS',collections.Counter(x['label'] for x in rows))
print('BASE_CM',cm(y,pred0),'CV_CM',cm(y,pred),'FIT_CM',cm(y,probs(E,w,b).argmax(axis=1)))
np.savez(OUT/'head_fit.npz',dense_w=w.astype('f4'),dense_b=b.astype('f4'))
(OUT/'pilot_scores.json').write_text(json.dumps(dict(labels=BASE.labels,baseline_cm=cm(y,pred0),source_note_holdout_cm=cm(y,pred),training_cm=cm(y,probs(E,w,b).argmax(axis=1)),steps=800,anchor_weight=.25,method='frozen convolution; class/source-balanced head Adam; grouped by note across all three classes',scope='small source-note holdout within recorded sessions, not new-room/instrument evaluation'),indent=2),encoding='utf-8')
