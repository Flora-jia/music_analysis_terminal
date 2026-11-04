"""800x480 LCD smoke test for the lcd_* chain, Python 3 / PYNQ.

Notebook:
    from lcd_colorbars import LCDColorbars
    lcd = LCDColorbars('audio_lcd_fbtest.bit')
    lcd.start()
    lcd.status()
    # Later: lcd.stop()

The matching audio_lcd_fbtest.hwh must be alongside the bitstream. Loading this
overlay reconfigures the entire PL; stop other audio/DMA applications first.
Keep the lcd object alive while displaying, and stop DMA before freeing RAM.

Register references:
https://github.com/Xilinx/embeddedsw/blob/master/XilinxProcessorIPLib/drivers/vtc/src/xvtc_hw.h
https://github.com/Xilinx/embeddedsw/blob/xilinx-v2020.2/XilinxProcessorIPLib/drivers/axivdma/src/xaxivdma_hw.h
"""

from pathlib import Path
import time


WIDTH, HEIGHT = 800, 480
LINE_BYTES = WIDTH * 3
# Explicit register-source bits; bit 19 (interlaced mode) must stay clear.
VTC_SOURCE_SELECT = 0x03F7EF00
DMA_ERROR_MASK = 0x00000FF0


def find_ip(ip_dict, short_name, ip_kind):
    matches = [(name, info) for name, info in ip_dict.items()
               if name.rsplit('/', 1)[-1] == short_name]
    if len(matches) != 1:
        raise ValueError("Expected one {!r} in HWH; found {}. Check the bit/HWH pair."
                         .format(short_name, [name for name, _ in matches]))
    name, info = matches[0]
    if ip_kind not in info.get('type', '').split(':'):
        raise ValueError('Unexpected IP type for {}: {}'.format(name, info.get('type')))
    return name, info


def pair(low, high):
    return (int(high) << 16) | int(low)


def paint_colorbars(frame):
    # RGB labels: white, yellow, cyan, green, magenta, red, blue, black.
    # Memory layout must be B/G/R to match the current top-level bit slicing.
    rgb = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
           (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    for index, (red, green, blue) in enumerate(rgb):
        left, right = index * WIDTH // 8, (index + 1) * WIDTH // 8
        frame[:, left:right, :] = (blue, green, red)
    frame.flush()


class LCDColorbars:
    def __init__(self, bitfile):
        from pynq import Overlay, MMIO, Clocks
        bitfile = Path(bitfile).expanduser().resolve()
        if not bitfile.is_file() or bitfile.suffix.lower() != '.bit':
            raise FileNotFoundError('Expected a .bit file: {}'.format(bitfile))
        if not bitfile.with_suffix('.hwh').is_file():
            raise FileNotFoundError('Missing matching HWH: {}'.format(bitfile.with_suffix('.hwh')))
        self.frame = None
        self.running = False
        self._dma_armed = False
        # Do not access overlay.lcd_vdma: use raw MMIO, without an IRQ-dependent driver.
        self.overlay = Overlay(str(bitfile))
        # AC820 PS reference is 33.333333 MHz. PYNQ 2.7 defaults to 50 MHz.
        # This adjusts Python calculations only, not the CPU/DDR PLL registers.
        clock_instance = getattr(Clocks, "_instance", None)
        if clock_instance is None or not hasattr(clock_instance, "_ref_clk_mhz"):
            raise RuntimeError("Unsupported PYNQ clock API; AC820 clock calibration was not applied")
        clock_instance._ref_clk_mhz = 33.333333
        # Verified boot image: IO PLL = 30 * 33.333333 MHz, FCLK0 source is IO PLL.
        # Apply AFTER Overlay download, which otherwise restores the HWH 6x6 divisors.
        Clocks.set_pl_clk(0, div0=5, div1=4)
        self.fclk0_mhz = float(Clocks.fclk0_mhz)
        if abs(self.fclk0_mhz - 50.0) > 0.1:
            raise RuntimeError("Unexpected FCLK0 {:.6f} MHz; check boot PLL/source before DMA".format(self.fclk0_mhz))
        time.sleep(0.1)
        print("AC820 clock calibration: PS_REF=33.333333 MHz; FCLK0={:.6f} MHz".format(self.fclk0_mhz))
        vdma_name, vdma = find_ip(self.overlay.ip_dict, 'lcd_vdma', 'axi_vdma')
        vtc_name, vtc = find_ip(self.overlay.ip_dict, 'lcd_vtc', 'v_tc')
        self.vdma = MMIO(int(vdma['phys_addr']), int(vdma['addr_range']))
        self.vtc = MMIO(int(vtc['phys_addr']), int(vtc['addr_range']))
        print('{} @ 0x{:08X}; {} @ 0x{:08X}'.format(
            vdma_name, int(vdma['phys_addr']), vtc_name, int(vtc['phys_addr'])))

    def _wait_dma(self, offset, mask, expected, description, timeout=2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = int(self.vdma.read(offset))
            if value & mask == expected:
                return
            time.sleep(0.005)
        raise TimeoutError('{}; register 0x{:02X}=0x{:08X}'.format(description, offset, value))

    def _configure_vtc(self):
        self.vtc.write(0x00, 0)          # Generator disabled during configuration.
        self.vtc.write(0x0C, 0)          # Polling only; no interrupt dependency.
        registers = {
            0x60: pair(800, 480),        # Active width / height.
            0x68: 0,                    # Progressive RGB.
            0x6C: 0x1F,                 # DE, HS, VS and both blanks active-high.
            0x70: 1056,                 # 800 + 40 + 128 + 88.
            0x74: pair(525, 525),        # 480 + 10 + 2 + 33, both fields.
            0x78: pair(840, 968),        # Horizontal sync start / end.
            0x7C: pair(800, 800),        # Vertical blank horizontal offsets.
            0x80: pair(490, 492),        # Field 0 vertical sync start / end.
            0x84: pair(840, 840),        # Align vertical sync to horizontal sync.
            0x88: pair(800, 800),        # Field 1 offsets, unused in progressive mode.
            0x8C: pair(490, 492),
            0x90: pair(840, 840),
            0x94: pair(0, 480),
        }
        for offset, value in registers.items():
            self.vtc.write(offset, value)
        # Select programmed timing/polarity registers and enable register updates.
        self.vtc.write(0x00, VTC_SOURCE_SELECT | 0x02)

    def start(self):
        from pynq import allocate
        if self.frame is not None:
            raise RuntimeError('Call lcd.stop() before starting again.')
        try:
            self.vdma.write(0x00, 0x04)  # MM2S reset, not the separate audio DMA.
            self._wait_dma(0x00, 0x04, 0, 'VDMA reset did not finish')
            self._configure_vtc()
            self.frame = allocate(shape=(HEIGHT, WIDTH, 3), dtype='u1')
            paint_colorbars(self.frame)
            address = int(self.frame.physical_address)
            if address < 0 or address + int(self.frame.nbytes) > (1 << 32) or address % 8:
                raise ValueError('Framebuffer is outside aligned 32-bit VDMA addressing')
            if int(self.frame.strides[0]) != LINE_BYTES:
                raise ValueError('Unexpected framebuffer stride')
            self.vdma.write(0x04, 0x7FF0)  # Clear sticky errors / interrupt flags.
            # All 3 configured frame slots repeat the same static image.
            for offset in (0x5C, 0x60, 0x64):
                self.vdma.write(offset, address)
            self.vdma.write(0x00, 0x03)    # Run, circular mode, genlock disabled.
            self._dma_armed = True
            self.vdma.write(0x58, LINE_BYTES)
            self.vdma.write(0x54, LINE_BYTES)
            self.vdma.write(0x50, HEIGHT)  # VSIZE written last launches MM2S.
            self.vtc.write(0x00, VTC_SOURCE_SELECT | 0x07)
            self._wait_dma(0x04, 0x01, 0, 'VDMA stayed halted')
            time.sleep(0.5)
            status = self.status()
            if status['vdma_status'] & DMA_ERROR_MASK:
                raise RuntimeError('VDMA error flags: 0x{:08X}'.format(status['vdma_status']))
            self.running = True
            print('MM2S running. Check LCD: white/yellow/cyan/green/magenta/red/blue/black.')
            print('Keep lcd alive. Use lcd.stop() before reloading any overlay.')
            return self
        except BaseException:
            self.stop()
            raise

    def status(self):
        result = {
            'vdma_control': int(self.vdma.read(0x00)),
            'vdma_status': int(self.vdma.read(0x04)),
            'vtc_control': int(self.vtc.read(0x00)),
            'vtc_active_size': int(self.vtc.read(0x60)),
        }
        print('; '.join('{}=0x{:08X}'.format(name, value) for name, value in result.items()))
        return result

    def stop(self):
        # Halt the memory master before releasing its physical memory.
        if self._dma_armed:
            self.vdma.write(0x00, int(self.vdma.read(0x00)) & ~0x01)
            try:
                self._wait_dma(0x04, 0x01, 0x01, 'VDMA did not halt')
            except TimeoutError:
                self.vdma.write(0x00, 0x04)
                self._wait_dma(0x00, 0x04, 0, 'VDMA reset did not finish; buffer NOT released')
            self._dma_armed = False
        self.vtc.write(0x00, 0)
        self.running = False
        if self.frame is not None:
            self.frame.freebuffer()
            self.frame = None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='PYNQ 800x480 LCD colorbar test')
    parser.add_argument('bitfile', help='New .bit with same-name .hwh alongside it')
    arguments = parser.parse_args()
    lcd = LCDColorbars(arguments.bitfile)
    try:
        lcd.start()
        input('Press Enter to stop LCD and release the framebuffer...')
    except KeyboardInterrupt:
        pass
    finally:
        lcd.stop()
