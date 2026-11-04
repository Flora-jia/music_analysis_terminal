"""Dark five-page touch UI, real PL spectrum/notes and model status."""
from speaker_dashboard import SpeakerDashboardUI
from live_service import DashboardFeed

class LiveDashboardUI(SpeakerDashboardUI):
    def __init__(self,lcd,touch,speaker,analysis,**kwargs):
        self.analysis=analysis;self.feed=DashboardFeed(analysis)
        self.model_label='Instrument: --';self.source_label='SPEC WAIT'
        super().__init__(lcd,touch,speaker,demo=False,**kwargs)
    def step(self,now,points=None):
        state=self.feed.step(self,now=now)
        self._ui_snapshot=state
        model=state['instrument']
        self.source_label='SPEC LIVE' if state['data_fresh'] else 'SPEC WAIT'
        label=None
        if state['instrument_ready'] and not model.get('error') and model.get('enabled'):
            value=model.get('label',model.get('cnn_label'))
            if value in ('piano','guitar','violin'):label=value
        self.instrument_label=label
        self.model_label='Instrument: '+(label.upper() if label else '--')
        super().step(self.clock() if self._active else now,points)

    def _key(self,now):
        return super()._key(now)+(self.model_label,self.source_label,self.instrument_label)
    def _action(self,name,x,now):
        before=len(self.records)
        if name=='freeze' and not self.spectrum_frozen:self._frozen_live_peak=self._peak()
        super()._action(name,x,now)
        if name=='clear_notes' and before and not self.records:self.analysis.clear_score()

    def _peak(self):
        if self.spectrum_frozen:return getattr(self,'_frozen_live_peak',None)
        value=getattr(self,'_ui_snapshot',None)
        if value is None:return None
        k=value['capture'].get('hw_peak_bin',0)
        return k*16000/4096 if value['data_fresh'] and 0<k*16000/4096<=self.spectrum_range else None

    def save_records(self,path=None,now=None):
        import json
        from pathlib import Path
        result=super().save_records(path,now)
        if result:
            original=Path(result);raw=original.with_name(original.stem+'_raw.json')
            with raw.open('x',encoding='utf-8') as stream:
                json.dump(dict(schema='ac820.raw_note_history.v1',notes=list(getattr(self,'raw_note_records',{}).values())),stream,ensure_ascii=False,indent=2)
        return result
