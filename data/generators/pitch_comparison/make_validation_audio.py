"""Deterministic monophonic test sources. These are not real instrument recordings."""
import json,wave
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
OUT=HERE/'validation_audio';OUT.mkdir(exist_ok=True)
SR=16000
def tone(f,harmonics,duration):
    t=np.arange(int(duration*SR))/SR
    y=sum(a*np.sin(2*np.pi*f*h*t+.13*h) for h,a in harmonics.items())
    y=y/max(1.,sum(abs(a) for a in harmonics.values()))*.35
    fade=min(160,len(y)//2);env=np.ones(len(y));env[:fade]=np.linspace(0,1,fade);env[-fade:]=np.linspace(1,0,fade)
    return y*env
def save(name,notes,duration=1.5,gap=.75):
    y=[np.zeros(SR)];events=[];start=1.
    for label,f,partials in notes:
        y.extend([tone(f,partials,duration),np.zeros(int(gap*SR))])
        events.append(dict(label=label,f0_hz=f,harmonics=partials,start_s=start,end_s=start+duration))
        start+=duration+gap
    data=np.rint(np.concatenate(y)*32767).astype('<i2')
    with wave.open(str(OUT/(name+'.wav')),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(data.tobytes())
    (OUT/(name+'.json')).write_text(json.dumps(dict(sr=SR,synthetic=True,events=events),indent=2))
    return str(OUT/(name+'.wav'))
paths=[]
paths.append(save('01_pure_tones_slow',[(s,f,{1:1}) for s,f in [
 ('500Hz',500),('A4',440),('C4',261.625565),('E2',82.406889),('G3',195.997718),('E5',659.255114)]]))
paths.append(save('02_harmonics_220',[
 ('A3_pure',220,{1:1}),('A3_second_strong',220,{1:.12,2:1,3:.5,4:.35}),
 ('A3_missing_fundamental',220,{2:.8,3:.6,4:.4,5:.3,6:.2}),('A2_third_strong',110,{1:.1,2:.15,3:1,4:.4,5:.3})],duration=2,gap=1))
paths.append(save('03_octaves_and_limits',[(s,f,{1:1}) for s,f in [
 ('A0',27.5),('C1',32.703196),('C2',65.406391),('C3',130.812783),('C4',261.625565),
 ('C5',523.251131),('C6',1046.502261),('C7',2093.004522),('C8',4186.009045)]]))
notes=[(s,440*2**((m-69)/12),{1:1,2:.2,3:.1}) for s,m in [('C4',60),('D4',62),('E4',64),('F4',65),('G4',67),('A4',69),('B4',71),('C5',72)]]
paths.append(save('04_scale_half_second',notes,duration=.5,gap=.25))
paths.append(save('05_scale_fast_expected_limits',notes,duration=.15,gap=.03))
print('\n'.join(paths))
