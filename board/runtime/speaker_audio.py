"""AC820 PYNQ speaker driver for ac820_speaker_core (SPK1).
Ported from the user's Vitis main.c and Xilinx iicps_v3_12/i2srx_v2_2.
No overlay download; LCD, touch and audio share the supplied overlay.
"""
import math
import time
from pathlib import Path

CODEC_WRITES = (
    (0x01,0x58),(0x01,0x50),(0x02,0xF3),(0x02,0xF0),
    (0x2B,0x80),(0x00,0x36),(0x08,0x00),(0x03,0x08),
    (0x04,0x00),(0x0D,0x06),(0x18,0x00),(0x05,0x00),
    (0x06,0xC3),(0x0A,0x00),(0x0B,0x02),(0x0C,0x0C),
    (0x17,0x18),(0x10,0x00),(0x11,0x00),(0x1A,0x00),
    (0x1B,0x00),(0x09,0x66),(0x12,0x11),(0x13,0xC0),
    (0x14,0x32),(0x15,0x06),(0x16,0xC2),(0x27,0x60),
    (0x2A,0x60),(0x02,0x00),(0x2E,0x1E),(0x2F,0x1E),
    (0x30,0x1E),(0x31,0x1E),(0x04,0x36),(0x26,0x00),
    (0x03,0x09),(0x2E,0x1E),(0x2F,0x1E),(0x30,0x1E),(0x31,0x1E))

class PSCodecI2C:
    """Finite 1/2-byte FIFO transfers, STOP+START read as in Vitis.
    Owns PS I2C0 exclusively. Refuses a bound Linux cdns-i2c controller.
    """
    def __init__(self, input_clock_hz=111111115, mmio_factory=None):
        if mmio_factory is None:
            from pynq import MMIO
            mmio_factory = MMIO
        driver = Path('/sys/bus/platform/drivers/cdns-i2c')
        if driver.is_dir() and any('e0004000' in p.name.lower() for p in driver.iterdir()):
            raise RuntimeError('Linux owns PS I2C0. Use its driver; do not share raw MMIO.')
        # Linux may gate unused PS peripherals. Preserve PLLs, CPU/DDR and MIO.
        slcr = mmio_factory(0xF8000000, 0x1000)
        aper = int(slcr.read(0x12C))
        reset = int(slcr.read(0x224))
        if reset & 1:
            raise RuntimeError('PS I2C0 is held in reset. Reboot the board before initialization.')
        if not aper & (1 << 18):
            slcr.write(0x008, 0xDF0D)
            try:
                slcr.write(0x12C, aper | (1 << 18))
            finally:
                slcr.write(0x004, 0x767B)
        self.mmio = mmio_factory(0xE0004000, 0x1000)
        self.address = 0x10
        # Match the Vitis driver's <=90kHz workaround. BSP CPU_1x is 111111115Hz.
        # input_clock_hz is explicit because another Linux image may differ.
        candidates = [(input_clock_hz/(22*(a+1)*(b+1)),a,b)
                      for a in range(4) for b in range(64)]
        candidates = [v for v in candidates if v[0] <= 90000]
        if not candidates:
            raise ValueError('Cannot obtain <=90kHz PS I2C clock.')
        self.scl_hz,a,b = max(candidates)
        self.divisor = (a << 14) | (b << 8)
        self._cleanup()  # Start with the controller's master state disabled.

    def _wait_idle(self, deadline):
        while int(self.mmio.read(0x04)) & 0x100:
            if time.monotonic() >= deadline:
                raise TimeoutError('PS I2C0 bus remains active.')
            time.sleep(0.0001)

    def _transfer(self, data, receive, deadline):
        self._wait_idle(deadline)
        self.mmio.write(0x00, self.divisor | 0x4E | int(receive))
        self.mmio.write(0x28, 0x2FF)
        self.mmio.write(0x10, 0x2FF)
        if receive:
            self.mmio.write(0x14, len(data))
        else:
            for byte in data:
                self.mmio.write(0x0C, byte)
        self.mmio.write(0x08, self.address)
        result = []
        while True:
            isr = int(self.mmio.read(0x10))
            if isr & 0x2EC:
                raise IOError('ES8388 I2C NACK/ARB/timeout/FIFO error ISR=0x%X' % isr)
            if time.monotonic() >= deadline:
                raise TimeoutError('ES8388 I2C transaction deadline (100ms).')
            if receive and len(result) < len(data) and int(self.mmio.read(0x04)) & 0x20:
                result.append(int(self.mmio.read(0x0C)) & 255)
            if isr & 1 and (not receive or len(result) == len(data)):
                break
            time.sleep(0.0001)
        self._wait_idle(deadline)
        if int(self.mmio.read(0x10)) & 0x2EC:
            raise IOError('ES8388 late I2C controller error.')
        self.mmio.write(0x10, 0x2FF)
        return result

    def _cleanup(self):
        # Match the local Vitis iicps_v3_12 XIicPs_ResetHw sequence.
        # Clearing FIFO alone while retaining MS=1 can leave a failed transfer
        # owning SDA. Abort the controller before a later transfer sets MS again.
        # Never pulse SLCR I2C_RST_CTRL from this Linux driver.
        self.mmio.write(0x28, 0x2FF)
        self.mmio.write(0x10, int(self.mmio.read(0x10)))
        control = int(self.mmio.read(0x00))
        self.mmio.write(0x00, (control & ~0x1A) | 0x40)
        self.mmio.write(0x1C, 0xFF)
        self.mmio.write(0x14, 0)
        self.mmio.write(0x04, int(self.mmio.read(0x04)))
        self.mmio.write(0x00, 0)
        # Restore only the divisor and 7-bit addressing, not master/ACK/HOLD.
        self.mmio.write(0x00, self.divisor | 0x04)

    def write(self, register, value):
        try:
            self._transfer([register, value], False, time.monotonic()+0.1)
        except Exception:
            self._cleanup()
            raise

    def read(self, register):
        deadline = time.monotonic()+0.1
        try:
            self._transfer([register], False, deadline)
            return self._transfer([0], True, deadline)[0]
        except Exception:
            self._cleanup()
            raise

    def checked(self, register, value):
        self.write(register,value)
        actual = self.read(register)
        if actual != value:
            raise IOError('ES8388 R%02X=%02X expected %02X' % (register,actual,value))
        return actual

    def configure(self):
        self.write(0x00,0x80)
        self.write(0x00,0x00)
        time.sleep(0.001)
        for register,value in CODEC_WRITES:
            self.write(register,value)
        # Digital DAC path, not the old analog bypass. Preserve ADC configuration.
        self.checked(0x27,0x80)
        self.checked(0x2A,0x80)
        # ES8388 Rev 5 lists R28/R29 defaults as 0x28, with no writable fields.
        # Leave them at chip defaults instead of requiring a zero readback.
        self.checked(0x04,0x3C)  # DACs and both LOUT/ROUT pairs enabled.
        self.checked(0x17,0x18)  # 16-bit standard I2S; slave uses RX clocks.
        self.checked(0x18,0x06)  # 12.288MHz / 16kHz = 768, same ratio as ADC.
        self.checked(0x19,self.read(0x19) & ~0x04)
        for register,value in ((0x08,0x00),(0x0C,0x0C),(0x0D,0x06),(0x2B,0x80)):
            if self.read(register) != value:
                raise IOError('ES8388 shared clock/ADC readback failed at %02X' % register)
        time.sleep(0.05)
        return {('R%02X' % r):hex(self.read(r)) for r in (0x04,0x08,0x17,0x18,0x19,0x27,0x2A,0x2B)}

    def mute(self):
        self.checked(0x19,self.read(0x19) | 0x04)

class PLCodecI2C(PSCodecI2C):
    """ES8388 register protocol over explicit PL open-drain controls.
    Uses only the speaker AXI slave. Does not access PS I2C/APB/SLCR.
    GPIO mode is exclusive; callers must serialize all codec operations.
    """
    def __init__(self, overlay, mmio_factory=None, half_period=0.00002, timeout=1.0):
        desc = overlay.ip_dict.get('speaker_core', {})
        version = desc.get('parameters', {}).get('IIC_DIAG_VERSION', '0')
        if int(str(version), 0) != 1:
            raise RuntimeError('Requires the new audio_lcd_speaker_pl_iic.bit and matching .hwh.')
        if mmio_factory is None:
            from pynq import MMIO
            mmio_factory = MMIO
        if not math.isfinite(half_period) or not 0.000005 <= half_period <= 0.001:
            raise ValueError('half_period must be 5..1000 microseconds.')
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('timeout must be positive.')
        self.mmio = mmio_factory(desc['phys_addr'], desc['addr_range'])
        if int(self.mmio.read(0x38)) != 0x49494331:
            raise RuntimeError('PL IIC signature mismatch; check matching bit/hwh.')
        self.address = 0x10
        self.half_period, self.timeout = half_period, timeout
        self._scl = self._sda = True
        self._deadline = None
        self.release()

    def levels(self):
        value = int(self.mmio.read(0x34))
        return {'scl':value & 1, 'sda':(value >> 3) & 1,
                'scl_release':(value >> 2) & 1,'sda_release':(value >> 5) & 1,
                'ps_scl_t':(value >> 7) & 1,'ps_sda_t':(value >> 9) & 1,
                'raw':hex(value)}

    def _set(self, scl=None, sda=None):
        if scl is not None:self._scl=bool(scl)
        if sda is not None:self._sda=bool(sda)
        self.mmio.write(0x30,1 | (int(self._scl) << 1) | (int(self._sda) << 2))

    def release(self):
        self._set(True, True)
        time.sleep(self.half_period)

    def _delay(self):
        if self._deadline is not None and time.monotonic() >= self._deadline:
            raise TimeoutError('PL codec I2C transaction deadline.')
        time.sleep(self.half_period)

    def _clock_high(self):
        self._set(scl=True)
        limit = min(time.monotonic()+0.05, self._deadline or float('inf'))
        while not int(self.mmio.read(0x34)) & 1:
            if time.monotonic() >= limit:
                raise TimeoutError('PL codec SCL stays low while released: '+str(self.levels()))
            time.sleep(self.half_period)
        self._delay()

    def _start(self):
        self._set(sda=True)
        self._clock_high()
        if not int(self.mmio.read(0x34)) & 8:
            raise IOError('PL codec SDA stays low while released: '+str(self.levels()))
        self._set(sda=False)
        self._delay()
        self._set(scl=False)
        self._delay()

    def _stop(self):
        self._set(scl=False)
        self._set(sda=False)
        self._delay()
        self._clock_high()
        self._set(sda=True)
        self._delay()

    def _write_byte(self, value):
        for bit in range(7,-1,-1):
            high=bool(value & (1 << bit))
            self._set(sda=high)
            self._delay()
            self._clock_high()
            if high and not int(self.mmio.read(0x34)) & 8:
                raise IOError('PL codec SDA low while sending 1: '+str(self.levels()))
            self._set(scl=False)
            self._delay()
        self._set(sda=True)
        self._delay()
        self._clock_high()
        ack=not bool(int(self.mmio.read(0x34)) & 8)
        self._set(scl=False)
        self._delay()
        if not ack:
            raise IOError('ES8388 NACK for byte 0x%02X at 7-bit address 0x10.' % value)

    def _read_byte(self):
        self._set(sda=True)
        self._delay()
        value=0
        for _ in range(8):
            self._clock_high()
            value=(value << 1) | ((int(self.mmio.read(0x34)) >> 3) & 1)
            self._set(scl=False)
            self._delay()
        # One-byte read ends with master NACK, then STOP.
        self._set(sda=True)
        self._delay()
        self._clock_high()
        self._set(scl=False)
        self._delay()
        return value

    def write(self, register, value):
        self._deadline=time.monotonic()+self.timeout
        try:
            self._start()
            for byte in (self.address << 1,register,value):self._write_byte(byte)
            self._stop()
        finally:
            self._deadline=None
            self.release()

    def read(self, register):
        self._deadline=time.monotonic()+self.timeout
        try:
            # Same STOP + START register-read form as the original Vitis program.
            self._start()
            self._write_byte(self.address << 1)
            self._write_byte(register)
            self._stop()
            self._start()
            self._write_byte((self.address << 1) | 1)
            value=self._read_byte()
            self._stop()
            return value
        finally:
            self._deadline=None
            self.release()

    def _cleanup(self):
        self.release()


class Speaker:
    """PL owns beat deadlines; poll()/UI only supplies heartbeat and status."""
    def __init__(self, overlay, mmio_factory=None):
        if mmio_factory is None:
            from pynq import MMIO
            mmio_factory = MMIO
        if 'speaker_core' not in overlay.ip_dict:
            raise RuntimeError('This overlay has no speaker_core. Build/upload the speaker bit+hwh first.')
        self.overlay = overlay
        self._mmio_factory = mmio_factory
        def ip(name):
            desc = overlay.ip_dict[name]
            return mmio_factory(desc['phys_addr'], desc['addr_range'])
        self.mmio = ip('speaker_core')
        if int(self.mmio.read(0x1C)) != 0x53504B31:
            raise RuntimeError('Speaker SPK1 signature mismatch; check matching bit/hwh.')
        self.fclk_hz = int(self.mmio.read(0x20))
        from pynq import Clocks
        if abs(float(Clocks.fclk0_mhz)*1e6-self.fclk_hz) > self.fclk_hz*0.01:
            raise RuntimeError('FCLK0 mismatch. Start calibrated LCDColorbars before Speaker.')
        self.rx, self.tx = ip('i2s_receiver_0'),ip('i2s_transmitter_0')
        self.codec = None
        self.prepared = False
        self._last_heartbeat = float('-inf')
        self.stop()

    def prepare(self, i2c_input_hz=111111115, start_rx=True):
        """Initialize codec through PL IIC before starting an audio producer.
        i2c_input_hz is retained for API compatibility; PL mode does not use it.
        """
        self.stop()
        self.prepared = False
        self.tx.write(0x08,int(self.tx.read(0x08)) & ~1)
        self.rx.write(0x08,int(self.rx.read(0x08)) & ~1)
        try:
            cfg = int(self.rx.read(0x04))
            if not cfg & 1:
                raise RuntimeError('RX must be the I2S clock master.')
            params = self.overlay.ip_dict['i2s_receiver_0'].get('parameters',{})
            if int(str(params.get('C_DWIDTH','16')),0) != 16:
                raise RuntimeError('Requires 16-bit RX.')
            slots = 32 if int(str(params.get('C_32BIT_LR','0')),0) else 16
            divider = 12288000//(2*16000*slots)//2
            if not 1 <= divider <= 15:
                raise RuntimeError('I2S divider out of range.')
            self.rx.write(0x10,0)  # polling; no IRQ handler installed.
            self.rx.write(0x20,divider)
            self.codec = PLCodecI2C(self.overlay,self._mmio_factory)
            codec_status = self.codec.configure()
            self.frontend_info={'codec':codec_status,'i2c_backend':'pl_open_drain',
                                'i2c_half_period_us':self.codec.half_period*1e6,'rx_divider':divider,'slot_bits':slots}
            if start_rx:return self.start_capture()
            return dict(self.frontend_info,rx_enabled=False)
        except Exception:
            self.stop()
            self.rx.write(0x08,int(self.rx.read(0x08)) & ~1)
            raise

    def start_capture(self):
        if self.codec is None:raise RuntimeError('Configure codec before enabling RX')
        self.rx.write(0x08,1)
        deadline=time.monotonic()+.5
        while not self.status()['clock_ok']:
            if time.monotonic()>=deadline:raise TimeoutError('No usable I2S clock')
            time.sleep(.005)
        self.prepared=True
        return dict(self.frontend_info,rx_enabled=True,**self.measure_clocks())

    def stop_capture(self):
        self.stop();self.rx.write(0x08,int(self.rx.read(0x08))&~1);self.prepared=False

    def configure(self,bpm=120,meter=4,volume=16,running=True,restart=True):
        bpm=float(bpm)
        if not math.isfinite(bpm) or not 30 <= bpm <= 240:
            raise ValueError('BPM must be 30..240.')
        if meter not in (2,3,4,6) or int(volume)!=volume or not 0 <= volume <= 128:
            raise ValueError('meter=2/3/4/6; volume=0..128.')
        if running and not self.prepared:
            raise RuntimeError('Call speaker.prepare() first.')
        self.mmio.write(0x04,round(self.fclk_hz*60/bpm))
        self.mmio.write(0x08,int(meter))
        self.mmio.write(0x0C,int(volume))
        self.mmio.write(0x00,(1 if running else 0)|(8 if restart and running else 0))
        self._last_heartbeat=time.monotonic()

    def start(self,bpm=120,meter=4,volume=16):
        self.configure(bpm,meter,volume,True,True)

    def stop(self):
        self.mmio.write(0x00,0)

    def poll(self):
        now=time.monotonic()
        if now-self._last_heartbeat>=0.25:
            self.mmio.write(0x2C,1)
            self._last_heartbeat=now
        return self.status()

    def status(self):
        # Retry around a beat transition to pair beat index and count coherently.
        for _ in range(3):
            count=int(self.mmio.read(0x14))
            flags=int(self.mmio.read(0x10))
            if int(self.mmio.read(0x14))==count:
                break
        return {'beat_index':flags&7,'beat_count':count,'enabled':bool(flags&256),
                'clock_ok':bool(flags&512),'watchdog_fault':bool(flags&1024),
                'fast_clock_fault':bool(flags&2048),'frame_count':int(self.mmio.read(0x18)),
                'bclk_count':int(self.mmio.read(0x24))}

    def measure_clocks(self,seconds=0.15):
        if not 0.05<=seconds<=1:
            raise ValueError('Measurement interval must be .05..1 second.')
        self.poll()
        t0=time.monotonic();a=self.status()
        time.sleep(seconds)
        b=self.poll();elapsed=time.monotonic()-t0
        fs=((b['frame_count']-a['frame_count']) & 0xFFFFFFFF)/elapsed
        bclk=((b['bclk_count']-a['bclk_count']) & 0xFFFFFFFF)/elapsed
        return {'measured_lrclk_hz':round(fs,1),'measured_bclk_hz':round(bclk,1),
                'bclk_per_frame':round(bclk/fs,2) if fs else None,'status':b}

    def test_tone(self,seconds=0.5,volume=16):
        if not self.prepared:
            raise RuntimeError('Call speaker.prepare() first.')
        if not math.isfinite(float(seconds)) or not 0<seconds<=10:
            raise ValueError('Test duration must be 0..10 seconds.')
        if int(volume)!=volume or not 0<=volume<=128:
            raise ValueError('volume must be 0..128.')
        try:
            self.mmio.write(0x0C,int(volume));self.mmio.write(0x00,2)
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                info=self.poll()
                if not info['clock_ok']:
                    raise RuntimeError('Lost I2S clock: '+str(info))
                time.sleep(0.02)
        finally:
            self.stop()

    def play(self,bpm=120,meter=4,seconds=10,volume=16):
        if not math.isfinite(float(seconds)) or seconds<=0:
            raise ValueError('seconds must be positive.')
        self.start(bpm,meter,volume)
        try:
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                info=self.poll()
                if not info['clock_ok'] or info['watchdog_fault']:
                    raise RuntimeError('Speaker fault: '+str(info))
                time.sleep(0.02)
        finally:
            self.stop()

    def close(self):
        # Keep shared RX clocks alive for capture. Codec mute would also affect
        # other playback clients, so ownership is explicit and no global mute here.
        self.stop()
