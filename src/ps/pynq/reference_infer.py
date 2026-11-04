"""Frozen CNN + user-labeled reference embeddings, centered cosine 1-NN.

Reference similarities are not probabilities. No CNN weight is updated, no FFT
is run here, and original CNN decisions are always returned separately.
"""
import hashlib
import json
from pathlib import Path
import time

import numpy as np

METHOD = 'centered_cosine_v1'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReferenceModel:
    def __init__(self, model, model_dir, reference_dir, inference_module=None):
        if inference_module is None:
            import infer_numpy as inference_module
        self.base_model, self.inference = model, inference_module
        self.labels = model.labels
        root, directory = Path(model_dir), Path(reference_dir)
        self.meta = json.loads((directory/'reference_meta.json').read_text(encoding='utf-8'))
        if self.labels != self.meta['labels']:
            raise ValueError('Reference labels differ from CNN labels')
        for name,key in [('cnn_weights.npz','weights_sha256'),('mel_matrix.npy','mel_matrix_sha256')]:
            if sha256(root/name) != self.meta[key]:
                raise ValueError('Reference bank is paired with different '+name)
        with np.load(directory/'reference_bank.npz', allow_pickle=False) as z:
            bank = np.asarray(z['embeddings'],dtype=np.float64)
            self.indices = np.asarray(z['label_indices'])
        if (bank.ndim != 2 or bank.shape[1] != 64 or not len(bank)
                or not np.all(np.isfinite(bank)) or self.indices.shape != (len(bank),)
                or self.indices.dtype.kind not in 'iu'
                or set(map(int,self.indices)) != set(range(len(self.labels)))
                or len(self.meta['references']) != len(bank)):
            raise ValueError('Invalid frozen reference bank')
        for i,row in enumerate(self.meta['references']):
            if row['label'] != self.labels[int(self.indices[i])]:
                raise ValueError('Reference annotations and label indices disagree')
        self.center = bank.mean(axis=0)
        shifted = bank-self.center
        norms = np.linalg.norm(shifted,axis=1,keepdims=True)
        if np.any(norms < 1e-12):
            raise ValueError('Degenerate centered reference embedding')
        self.bank = shifted/norms
        self.last_reference = None

    def encode(self,mel):
        x = np.asarray(mel,dtype=np.float32)
        if x.shape != (64,63) or not np.all(np.isfinite(x)):
            raise ValueError('Expected finite mel (64,63)')
        x=x[...,None]
        for key in ('conv2d','conv2d_1','conv2d_2'):
            x=self.inference._maxpool2(self.inference._conv_same_relu(
                x,self.base_model.w[key+'_w'],self.base_model.w[key+'_b']))
        embedding=x.mean(axis=(0,1))
        logits=embedding@self.base_model.w['dense_w']+self.base_model.w['dense_b']
        e=np.exp(logits-logits.max())
        return embedding,(e/e.sum()).astype(np.float32)

    def match(self,embedding):
        x=np.asarray(embedding,dtype=np.float64)-self.center
        norm=np.linalg.norm(x)
        if not np.isfinite(norm) or norm < 1e-12:
            return dict(reference_label='unknown',reference_similarity=None,
                        reference_margin=None,reference_method=METHOD,nearest_reference=None)
        scores=self.bank@(x/norm)
        nearest=int(scores.argmax())
        per_class=np.array([scores[self.indices==i].max() for i in range(len(self.labels))])
        rank=np.sort(per_class)
        return dict(reference_label=self.labels[int(self.indices[nearest])],
                    reference_similarity=float(scores[nearest]),
                    reference_margin=float(rank[-1]-rank[-2]),
                    reference_class_similarities=dict(zip(self.labels,map(float,per_class))),
                    reference_method=METHOD,
                    nearest_reference=dict(index=nearest,**self.meta['references'][nearest]))

    def infer(self,mel):
        started=time.monotonic()
        self.last_reference=None
        embedding,probs=self.encode(mel)
        result=self.match(embedding)
        result['cnn_and_reference_ms']=(time.monotonic()-started)*1000
        self.last_reference=result
        return int(probs.argmax()),probs


class ReferenceSession:
    """One forward pass per audio segment; caller owns Codec/Overlay/DMA."""
    def __init__(self,receiver,model_dir='models',reference_dir='reference',silence_rms=.003):
        from pl_fft import InstrumentSession
        self.base=InstrumentSession(receiver,model_dir=model_dir,silence_rms=silence_rms)
        self.model=ReferenceModel(self.base.model,model_dir,reference_dir)
        self.base.model=self.model
        self.matrix=self.base.matrix

    def next(self):
        try:
            result=self.base.next()
            if result['label']=='silence':
                self.model.last_reference=None
                result.update(reference_label='silence',reference_similarity=None,
                              reference_margin=None,nearest_reference=None,reference_method=METHOD,
                              cnn_and_reference_ms=0.)
            else:
                result.update(self.model.last_reference)
            result.update(cnn_label=result['label'],cnn_confidence=result['confidence'],
                          cnn_probabilities=result['probabilities'])
            return result
        except BaseException:
            self.model.last_reference=None
            raise
