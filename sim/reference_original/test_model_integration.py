import re
import sys
from pathlib import Path
import unittest
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path[:0] = [str(ROOT / 'board'), str(ROOT), str(REPO / 'deploy')]
from pl_fft import (MAGIC, WORDS, decode_frame, restore_power, power_to_mel,
                    BatchAssembler, FFTReceiver, ProtocolError)
from frontend import Codec, choose_divider, WRITES, READBACKS
from infer_numpy import mel_spectrogram_np
from dds_reference import make_reference


def packet(index=0, segment=2, start=32000, exp=3):
    return np.array([MAGIC,segment,index,start,0,513,1,0,exp] + list(range(513)), dtype=np.uint32)


class Buffer(np.ndarray):
    def __new__(cls):
        obj = np.zeros(WORDS, dtype=np.uint32).view(cls)
        obj.physical_address, obj.freed, obj.events = 0x10000000, False, []
        return obj

    def flush(self): self.events.append('flush')
    def invalidate(self): self.events.append('invalidate')
    def freebuffer(self): self.freed = True


class DMA:
    def __init__(self, buffer, complete=True, error=0, short=False):
        self.buffer, self.complete, self.error, self.short = buffer, complete, error, short
        self.regs = {0x30: 0, 0x34: 1, 0x58: 0}
        self.stuck_reset = False

    def write(self, off, value):
        if off == 0x30 and value == 4:
            self.regs[off] = 4 if self.stuck_reset else 0
            self.regs[0x34] = 1
        elif off == 0x30 and value == 1:
            self.regs[off], self.regs[0x34] = 1, 0
        elif off == 0x34:
            self.regs[off] &= ~value
        elif off == 0x58:
            self.regs[off] = value - 4 if self.short else value
            self.buffer[:] = packet()
            self.regs[0x34] = self.error or (0x1002 if self.complete else 0)
        else:
            self.regs[off] = value

    def read(self, off): return self.regs.get(off, 0)


class IIC:
    def __init__(self, fail=False, busy=False):
        self.writes, self.ctrl, self.irq = [], 0, 0
        self.fail, self.busy = fail, busy

    def read(self, off):
        if off == 0x10: return self.irq
        if off == 0x04: return 0x100 if self.busy else (0x20 if self.ctrl & 1 else 0)
        if off == 0x0C: return 0x66
        return 0

    def write(self, off, value):
        self.writes.append((off, value))
        if off == 0: self.ctrl = value
        if off == 0x10: self.irq &= ~value
        if off == 8: self.irq = 4 if self.fail else 1


class IntegrationTests(unittest.TestCase):
    def test_training_features_without_repeating_model_validation(self):
        y = np.random.default_rng(4).normal(0, .1, 16000).astype(np.float32)
        idx = np.arange(1024)[None, :] + np.arange(63)[:, None] * 256
        frames = np.pad(y, 512)[idx] * (.5-.5*np.cos(2*np.pi*np.arange(1024)/1024))
        reference_power = np.abs(np.fft.rfft(frames, axis=1)).T ** 2
        matrix = np.load(REPO / 'models/mel_matrix.npy')
        np.testing.assert_allclose(power_to_mel(reference_power, matrix),
                                   mel_spectrogram_np(y, matrix), atol=1e-6)

    def test_exponent_and_unsigned_power(self):
        p = np.array([0x80000000, 7], dtype=np.uint32)
        np.testing.assert_allclose(restore_power(p, 3), [128., 448./2**30])
        self.assertEqual(restore_power([123], 5)[0] / restore_power([123], 2)[0], 64)

    def test_segment_assembly_and_wrap_metadata(self):
        assembler = BatchAssembler()
        for i in range(63):
            result = assembler.push(decode_frame(packet(i, segment=0xFFFFFFFF, start=0xFFFFFF00, exp=i%6)))
        self.assertEqual(result['power'].shape, (513,63))
        for i in range(63):
            np.testing.assert_allclose(result['power'][:,i], restore_power(np.arange(513), i%6))

    def test_old_protocol_and_error_rejected(self):
        for word, value in [(0,0xA55A0401),(4,2),(8,32),(5,512),(2,63)]:
            w = packet(); w[word] = value
            with self.assertRaises(ProtocolError): decode_frame(w)

    def test_missing_or_spliced_frames_rejected(self):
        for change in ('index','segment','start','dropped'):
            assembler = BatchAssembler(); assembler.push(decode_frame(packet()))
            frame = decode_frame(packet(1)); frame[change] += 1
            with self.assertRaises(ProtocolError): assembler.push(frame)

    def test_dma_success_and_cache_ownership(self):
        buf = Buffer(); dma = DMA(buf); receiver = FFTReceiver(dma, buf, .01)
        self.assertEqual(receiver.receive_frame()['segment'], 2)
        self.assertEqual(buf.events, ['flush', 'invalidate'])
        receiver.close(); self.assertTrue(buf.freed)

    def test_dma_timeout_error_and_short_packet(self):
        for kwargs, error in [({'complete':False},TimeoutError),({'error':0x20},RuntimeError),
                              ({'short':True},ProtocolError)]:
            buf = Buffer(); receiver = FFTReceiver(DMA(buf, **kwargs), buf, .002)
            with self.assertRaises(error): receiver.receive_frame()
            self.assertTrue(receiver.failed)
            receiver.close(); self.assertTrue(buf.freed)

    def test_do_not_free_live_dma_on_reset_failure(self):
        buf = Buffer(); dma = DMA(buf); receiver = FFTReceiver(dma, buf, .002)
        dma.stuck_reset = True
        with self.assertRaises(TimeoutError): receiver.close()
        self.assertFalse(buf.freed)
        dma.stuck_reset = False; receiver.close()

    def test_iic_address_ack_and_finite_errors(self):
        mmio = IIC(); codec = Codec(mmio, 100e6, .002)
        self.assertEqual(codec.read(9), 0x66)
        self.assertEqual([v for off,v in mmio.writes if off==8], [0x10,0x10])
        cr = [v for off,v in mmio.writes if off==0]
        self.assertTrue(all(v & 8 and not v & 16 for v in cr))
        self.assertFalse(cr[0]&1); self.assertTrue(cr[1]&1)
        for kwargs in ({'fail':True}, {'busy':True}):
            with self.assertRaises(RuntimeError): Codec(IIC(**kwargs), 50e6, .002).read(9)
        for hz in (50e6, 100e6, 111111111):
            self.assertLessEqual(choose_divider(hz)[1], 100000)

    def test_register_tables_match_frozen_upstream_c(self):
        source = ROOT / 'reference/frontend_main.c'
        c = source.read_text(encoding='utf-8')
        for name, expected in [('writes',WRITES),('readbacks',READBACKS)]:
            table = c.split('static const CodecRegister '+name+'[] = {',1)[1].split('};',1)[0]
            actual = [(int(a,16),int(b,16)) for a,b in re.findall(r'\{(0x[0-9A-Fa-f]+),\s*(0x[0-9A-Fa-f]+)\}', table)]
            self.assertEqual(actual, expected)

    def test_exact_dds_oracle_center_edges(self):
        reference = make_reference()
        self.assertEqual(reference['power'].shape, (513,63))
        self.assertEqual(int(reference['power'][:,10].argmax()), 32)
        self.assertLess(reference['power'][:,0].sum(), reference['power'][:,10].sum())
        self.assertEqual(int(reference['pcm'][0]), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
