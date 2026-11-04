"""Single shared overlay: SPEC DMA0 + model DMA1 + LCD/touch + Line Out."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import argparse
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

def verify_bit_pair(bitfile):
    bit=Path(bitfile).expanduser().resolve();root=bit.parent
    manifest=root/'manifest_board.json'
    if not manifest.is_file():raise FileNotFoundError('Upload/extract the complete audio_three_in_one_bundle.zip')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('schema')!='ac820.bundle.v2' or data.get('dma0_protocol')!='SPEC_v2':
        raise ValueError('Expected the three-in-one SPEC v2 bundle')
    required={'spectrum_audio.py','model_stream.py','live_service.py','run_live_system.py',
        'live_dashboard.py','speaker_audio.py','speaker_dashboard.py','lcd_colorbars.py',
        'gt911_touch.py','music_dashboard.py','pl_fft.py','infer_numpy.py','reference_infer.py',
        'models/cnn_weights.npz','models/mel_matrix.npy','models/model_meta.json',
        'reference/reference_bank.npz','reference/reference_meta.json','reference/frozen_config.json',
        'dma_transport.py','system_runtime.py','dsp/__init__.py','dsp/_native.py','dsp/note_engine.py',
        'dsp/libmusic_ps.so','dsp/abi_manifest.json','instrument_capture.py','summarize_capture.py'}
    if not required.issubset(data.get('files',{})):raise ValueError('Incomplete three-in-one bundle manifest')
    # All runtime/model files, not just the two hardware files, are paired.
    for name,item in data['files'].items():
        path=(root/name).resolve()
        if root not in path.parents:raise ValueError('Invalid bundle path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Bundle hash mismatch: '+name)
    for path in (bit,bit.with_suffix('.hwh')):
        if path.name not in data['files']:raise ValueError('Bit/HWH is not covered by this bundle')
    return data

def check_module_origins(root):
    for name in ('spectrum_audio','live_service','live_dashboard','model_stream','speaker_audio',
                 'speaker_dashboard','lcd_colorbars','gt911_touch','music_dashboard','pl_fft',
                 'infer_numpy','reference_infer','dma_transport','system_runtime','instrument_capture','summarize_capture'):
        module=sys.modules.get(name)
        location=getattr(module,'__file__',None)
        if location and Path(location).resolve().parent!=root:
            raise RuntimeError('Old module cached: '+name+'; stop the old app, restart the Jupyter kernel, then run this bundle')

def main():
    parser=argparse.ArgumentParser(description='AC820 SPEC + native C notes + model + LCD/Line Out')
    parser.add_argument('--bit',default=str(Path(__file__).with_name('audio_merged.bit')))
    parser.add_argument('--http-port',type=int,default=5002)
    parser.add_argument('--no-touch',action='store_true');parser.add_argument('--no-model',action='store_true')
    parser.add_argument('--check-only',action='store_true',help='Load/check native library before touching PL')
    parser.add_argument('--no-piano-support',action='store_true',help='Disable learned audio piano support for A/B comparison')
    parser.add_argument('--piano-review',action='store_true',help='Experimental piano verification for the validated field-head model')
    parser.add_argument('--ui-stats',action='store_true',help='Print UI/touch/render timing every five seconds')
    parser.add_argument('--headless',action='store_true');parser.add_argument('--volume',type=int,default=32)
    parser.add_argument('--input',choices=('line','vitis'),default='line')
    parser.add_argument('--record-dir',default=str(Path(__file__).with_name('music_records')))
    parser.add_argument('--capture-label',choices=('piano','guitar','violin','silence','background','unlabeled'))
    parser.add_argument('--capture-note',default='',help='Operator microphone/distance/gain/playing notes')
    parser.add_argument('--capture-dir',default=None)
    parser.add_argument('--capture-limit',type=int,default=120,help='Maximum recorded inferred segments')
    parser.add_argument('--capture-max-mb',type=int,default=256)
    args=parser.parse_args()
    if args.capture_label and args.no_model:parser.error('Feature capture needs DMA1; remove --no-model')
    if args.capture_dir and not args.capture_label:parser.error('--capture-dir requires --capture-label')
    if not 1<=args.capture_limit<=10000 or not 1<=args.capture_max_mb<=4096:parser.error('Invalid capture limits')
    if not 0<=args.volume<=128:parser.error('Volume must be 0..128')
    bundle=verify_bit_pair(args.bit);check_module_origins(Path(__file__).resolve().parent)
    if args.piano_review:
        from model_stream import PIANO_REVIEW_WEIGHTS_SHA
        if bundle['files']['models/cnn_weights.npz']['sha256']!=PIANO_REVIEW_WEIGHTS_SHA:
            parser.error('--piano-review is validated only for the field-head candidate; use its matching bundle')
        print('PIANO_REVIEW: enabled; experimental; raw CNN results preserved',flush=True)
    from spectrum_audio import SpectrumAnalysis
    from system_runtime import MusicSystem,StopFailed
    print('MODEL_CANDIDATE: R6 learned piano support; raw CNN unchanged; board verification pending',flush=True)
    analysis=SpectrumAnalysis();analysis.model_enabled=not args.no_model
    analysis.run_metadata=dict(software_release=bundle.get('software_release','unversioned'),
        model_variant=bundle.get('model_variant','original_frozen'),input_profile=args.input,
        capture_label=args.capture_label,capture_note=args.capture_note,piano_review=args.piano_review,piano_support=not args.no_piano_support,
        artifacts={n:bundle['files'][n] for n in ('models/cnn_weights.npz','models/mel_matrix.npy','audio_merged.bit','audio_merged.hwh')})
    print('SOFTWARE_RELEASE:',analysis.run_metadata['software_release'],flush=True)
    if args.check_only:
        import numpy as np
        analysis.engine.process(np.zeros(2049,dtype='u2'),0,0)
        print('NATIVE_LIBRARY_SELFTEST_OK',flush=True);analysis.close_engine();return
    system=MusicSystem(analysis,args)
    def stop(*unused):raise KeyboardInterrupt()
    signal.signal(signal.SIGTERM,stop)
    try:
        system.start()
        print('LIVE_API: http://0.0.0.0:{}/api/state; backend=C; demo=False'.format(args.http_port),flush=True)
        system.run()
    except KeyboardInterrupt:pass
    finally:
        try:system.close()
        except StopFailed as exc:
            print('STOP_FAILED: '+str(exc),flush=True)
            # Notebook retains the quarantined owner for inspection/retry.
            # CLI must remain alive instead of letting CMA owners be collected.
            try:
                from IPython import get_ipython
                interactive=get_ipython() is not None
            except ImportError:interactive=False
            if not interactive:
                while True:time.sleep(1)
            raise

if __name__=='__main__':main()
