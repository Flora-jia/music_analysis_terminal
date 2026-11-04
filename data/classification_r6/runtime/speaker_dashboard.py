"""Hardware-clocked sound with the existing framebuffer dashboard.
Hardware beat counters remain authoritative across pages.
"""
from music_dashboard import MusicDashboardUI

class SpeakerDashboardUI(MusicDashboardUI):
    def __init__(self,lcd,touch,speaker,demo=False,volume=16,**kwargs):
        if not speaker.prepared:
            raise RuntimeError('Call speaker.prepare() before creating the UI.')
        if speaker.overlay is not lcd.overlay:
            raise RuntimeError('LCD and speaker must share one Overlay object.')
        if int(volume)!=volume or not 0<=volume<=128:
            raise ValueError('volume must be 0..128.')
        super().__init__(lcd,touch,demo=demo,**kwargs)
        self.speaker=speaker
        self.volume=int(volume)
        self._speaker_config=None
        self._speaker_count=None
        self._speaker_tick_time=None
        self.speaker.stop()

    def step(self,now,points=None):
        self._drain(now)
        if self._demo_feed is not None:
            self._demo_feed.tick(self,now)
        # Only PL advances the audible beat. Do not call state.advance(now).
        contact_before=(self.page,self._pressed,self._down)
        self._touch_report(points,now)
        input_changed=contact_before!=(self.page,self._pressed,self._down)
        if self.page=='metronome':
            self._repeat(now)
        wanted=(self.state.running,self.state.bpm,self.state.meter,self.volume)
        if wanted!=self._speaker_config:
            self.speaker.configure(bpm=self.state.bpm,meter=self.state.meter,
                                   volume=self.volume,running=self.state.running,restart=True)
            self._speaker_config=wanted
            self._speaker_count=None
        info=self.speaker.poll()
        if info['watchdog_fault'] or info['fast_clock_fault'] or not info['clock_ok']:
            self.speaker.stop()
            self.state.pause()
            raise RuntimeError('Speaker clock/watchdog fault: '+str(info))
        beat_changed=False
        if self.state.running:
            self.state.beat_index=info['beat_index']
            if info['beat_count']!=self._speaker_count:
                beat_changed=True
                self._speaker_count=info['beat_count']
                self._speaker_tick_time=now
                self.state.last_tick=now
                self.state.pulse_until=now+min(0.12,self.state.period*0.45)
            # Touch handlers use this estimate when changing tempo. PL status is
            # authoritative on the next step; display is not a timing instrument.
            self.state.next_tick=(self._speaker_tick_time or now)+self.state.period
        interval={'home':.2,'spectrum':.1,'notation':.05,'instrument':.1,'metronome':1/30}.get(self.page,1/15)
        if self._key(now)!=self._last_key and (self.closed or beat_changed or input_changed or now-self._last_paint>=interval):
            self.paint(now)

    def paint(self,now=None):
        from music_dashboard import _draw_beat_strip
        import numpy as np,time
        now=self.clock() if now is None else now
        key=(self.page,self.state.bpm,self.state.meter,self.state.running,self._pressed,
             self.closed,getattr(self,'model_label',None),getattr(self,'source_label',None),
             self._notice if now<self._notice_until else None)
        partial=(self.page=='metronome' and not self.closed and
                 key==getattr(self,'_paint_layout_key',None) and self._notice_until<=now)
        if not partial:
            super().paint(now)
        else:
            if self.lcd.frame is not self._owner or not self.lcd.running:
                raise RuntimeError('LCD framebuffer changed or stopped.')
            started=time.perf_counter()
            _draw_beat_strip(self.canvas,self.state,now)
            rendered=time.perf_counter()
            np.copyto(self._display[342:394],self.canvas.image[342:394])
            self.lcd.frame[342:394].flush()
            self._last_key=self._key(now);self._last_paint=now
            if self.ui_stats:
                ended=time.perf_counter()
                self._timings['paint'].append((ended-started)*1000)
                self._timings['render'].append((rendered-started)*1000)
                self._timings['copy_flush'].append((ended-rendered)*1000)
        self._paint_layout_key=key

    def stop(self):
        self.speaker.stop()
        super().stop()
