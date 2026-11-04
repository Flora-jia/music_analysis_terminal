"""Read-cache HTTP service. DMA has exactly one owner; HTTP never reads hardware."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

class AudioService:
    def __init__(self,analysis,host='0.0.0.0',port=5002):
        self.analysis=analysis;owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def answer(self,status,obj):
                body=json.dumps(obj,ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def do_GET(self):
                path=urlsplit(self.path).path
                if path in ('/api/state','/api/live'):
                    self.answer(200,owner.analysis.snapshot())
                elif path=='/api/pcm':
                    value=owner.analysis.pcm_snapshot()
                    self.answer(410 if value.get('available') is False else 200,value)
                elif path=='/api/spectrum':
                    s=owner.analysis.snapshot()
                    self.answer(200,dict(schema=s['schema'],data_fresh=s['data_fresh'],spectrum=s['spectrum']))
                elif path=='/api/instrument':
                    s=owner.analysis.snapshot()
                    self.answer(200,s['instrument'])
                elif path=='/api/health':
                    s=owner.analysis.snapshot()
                    self.answer(200,dict(schema=s['schema'],connected=s['connected'],
                        data_fresh=s['data_fresh'],capture=s['capture'],error=s['error'],instrument=s['instrument']))
                else:self.answer(404,dict(error='Unknown endpoint'))
            def do_POST(self):
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<=length<=4096:raise ValueError('Body too large')
                    raw=self.rfile.read(length)
                    data=json.loads(raw or b'{}')
                    path=urlsplit(self.path).path
                    if path=='/api/score/clear':owner.analysis.clear_score()
                    elif path=='/api/calibration/start':owner.analysis.calibrate()
                    elif path=='/api/segmentation':
                        if owner.analysis.snapshot().get('segmentation',{}).get('configurable') is False:
                            self.answer(409,dict(error='Native C thresholds are fixed; use silent calibration'));return
                        owner.analysis.configure(data.get('high'),data.get('low'))
                    else:self.answer(404,dict(error='Unknown endpoint'));return
                    self.answer(200,dict(ok=True))
                except (ValueError,TypeError,AttributeError) as exc:self.answer(400,dict(error=str(exc)))
        self.server=ThreadingHTTPServer((host,port),Handler)
        self.thread=None
    def start(self):
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def close(self):
        if self.thread:self.server.shutdown();self.thread.join(timeout=2)
        self.server.server_close()

class CaptureWorker:
    def __init__(self,receiver,analysis,health=None):
        self.receiver,self.analysis,self.health=receiver,analysis,health
        self.stop_event=threading.Event();self.thread=None
    def start(self,started=None):
        def work():
            from dma_transport import NoPacketYet,ReceiverCancelled
            from spectrum_audio import InvalidSpectrum
            try:
                if started is not None:
                    while not self.stop_event.is_set() and not started.wait(.02):pass
                while not self.stop_event.is_set():
                    try:words=self.receiver.receive()
                    except NoPacketYet:self.analysis.poll_watchdog();continue
                    if self.stop_event.is_set():break
                    if self.health:self.health()
                    self.analysis.feed(words)
                    self.analysis.poll_watchdog()
            except ReceiverCancelled:pass
            except InvalidSpectrum:self.analysis.lifecycle='FAULT'
            except Exception as exc:
                if not self.stop_event.is_set():self.analysis.fail(type(exc).__name__+': '+str(exc))
            finally:
                try:self.analysis.stop('capture_stopped')
                except Exception as exc:self.analysis.error='Native stop: '+str(exc)
                try:self.receiver.halt()
                except Exception as exc:self.analysis.lifecycle='STOP_FAILED';self.analysis.error='DMA0 halt: '+str(exc)
        self.thread=threading.Thread(target=work,name='dma0_audio',daemon=True);self.thread.start()
    def request_stop(self):self.stop_event.set();self.receiver.request_stop()
    def join(self):
        if self.thread:
            self.thread.join(timeout=3)
            if self.thread.is_alive():raise RuntimeError('DMA0 worker still active; retain buffers')
    def close(self):self.request_stop();self.receiver.halt();self.join();self.receiver.release()

def note_to_ui(note,bpm=120):
    options=(.125,.1875,.25,.375,.5,.75,1,1.5,2,3,4,6,8)
    duration=note.get('duration_ms')
    beats=max(.125,(duration if duration is not None else 500)*bpm/60000)
    return dict(degree=note['degree'],octave=note['octave']-4,accidental=note['accidental'],
                beats=min(options,key=lambda x:abs(x-beats)),frequency=note['freq'],
                confidence=note['confidence'],note_name=note['note_name'],note_id=str(note['id']))

class DashboardFeed:
    def __init__(self,analysis):
        self.analysis=analysis;self.frame=-1;self.committed={};self.was_fresh=False
        self.generation=0;self.last_spectrum=0.;self.resync=0
    def step(self,app,now=None,force=False):
        import copy,time
        now=time.monotonic() if now is None else now
        previous=getattr(self,'last_snapshot',None)
        if previous is not None and not force and 0<=now-getattr(self,'last_update',0)<1/60:
            return previous
        visible=getattr(app,'page',None)=='spectrum' and not app.spectrum_frozen
        wants_spectrum=visible and now-self.last_spectrum>=.1
        reader=getattr(self.analysis,'dashboard_snapshot',None)
        state=(reader(score_version=getattr(self,'score_version',None),include_spectrum=wants_spectrum)
               if reader else self.analysis.snapshot())
        self.last_snapshot=state;self.last_update=now
        fresh=state['data_fresh'];generation=state['score_generation']
        if not hasattr(app,'raw_note_records'):app.raw_note_records={}
        if generation!=self.generation:
            self.generation=generation
            app.records.clear();app._tokens.clear();app._seen_ids.clear()
            app.score_page=0;app.score_scroll=0.;app.follow_latest=True;app._last_key=None
            app._held_note=None
            app.raw_note_records.clear();self.committed.clear()
        # Completed events survive even when ON and OFF both occurred between UI ticks.
        for note in state['score'] or ():
            identity=(state['session'],note['id'])
            app.raw_note_records[note['id']]=copy.deepcopy(note)
            signature=(note.get('duration_ms'),note.get('time_quality'),note.get('truncated'))
            if identity not in self.committed or self.committed[identity]!=signature:
                values=note_to_ui(note,app.state.bpm);values['note_id']=state['session']+':'+str(note['id'])
                if identity not in self.committed:app.commit_note(**values)
                else:
                    from music_dashboard import Note
                    for index,item in enumerate(app.records):
                        if item.note_id==values['note_id']:app.records[index]=Note(**values)
                    app._tokens=[]
                    for item in app.records:
                        app._tokens.append(('note',item))
                        app._tokens.extend(('dash',None) for _ in range(max(0,int(item.beats)-1)))
                        if item.bar_end:app._tokens.append(('bar',None))
                    if app.follow_latest:app.score_scroll=app._max_score_scroll()
                    app._last_key=None
            self.committed[identity]=signature
        if 'score_version' in state:self.score_version=state['score_version']
        if state['resync_count']!=self.resync:
            self.resync=state['resync_count'];app.update_note(None)
        if fresh:
            spectrum=state['spectrum']
            if spectrum and wants_spectrum:
                app.update_spectrum(spectrum['freq_hz'],spectrum['mag']);self.last_spectrum=now
            note=state['current_note']
            app.update_note(**note_to_ui(note,app.state.bpm)) if note else app.update_note(None)
        else:
            app.update_note(None)
            if self.was_fresh:app.spectrum=None;app._spectrum_version+=1
        self.was_fresh=fresh
        return state

