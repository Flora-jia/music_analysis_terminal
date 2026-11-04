"""AC820 touch bring-up: GPIO character-device I2C, no kernel I2C driver.

Requires add_touch_reset.tcl hardware: GPIO EMIO[0] -> R15 (TP_RST).
MIO50=SCL, MIO51=SDA, MIO0=INT. Keeps audio I2C0 on EMIO.
Does not load any Overlay or change clocks. SCL/SDA use kernel open-drain GPIO.
"""
from pathlib import Path
import errno
import os
import struct
import time


class _Line:
    def __init__(self, chip, offset, output=False, open_drain=False, value=0):
        import fcntl
        request = bytearray(364)  # Linux gpiohandle_request, GPIO uAPI v1.
        struct.pack_into('=II', request, 0, offset, 0)
        flags = 2 if output else 1
        if open_drain:
            flags |= 8
        struct.pack_into('=I', request, 256, flags)
        request[260] = int(bool(value))
        request[324:335] = b'ac820-touch'
        struct.pack_into('=I', request, 356, 1)
        fcntl.ioctl(chip, 0xC16CB403, request, True)
        self.fd = struct.unpack_from('=i', request, 360)[0]
        self._ioctl = fcntl.ioctl
        self._values = bytearray(64)

    def set(self, value):
        self._values[0] = int(bool(value))
        self._ioctl(self.fd, 0xC040B409, self._values, True)

    def get(self):
        self._ioctl(self.fd, 0xC040B408, self._values, True)
        return self._values[0]

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


def _open_gpiochip():
    import fcntl
    for path in sorted(Path('/dev').glob('gpiochip*'))[:16]:
        fd = os.open(str(path), os.O_RDONLY | os.O_CLOEXEC)
        try:
            info = bytearray(68)
            fcntl.ioctl(fd, 0x8044B401, info, True)
            label = bytes(info[32:64]).split(b'\0')[0].decode('ascii', 'replace')
            lines = struct.unpack_from('=I', info, 64)[0]
            if 'zynq' in label.lower() and lines >= 55:
                return fd, str(path), label
        except BaseException:
            os.close(fd)
            raise
        os.close(fd)
    raise RuntimeError('No Zynq /dev/gpiochip device. Send ls /dev/gpiochip* output; do not install packages yet.')


def _gpio_mux_value(value):
    # Linux pinctrl-zynq: mux bits 1..7, tristate bit0, receiver-disable bit13.
    # Preserve existing I/O voltage type and slew; enable weak pull-up.
    return (value & ~0x20FF) | 0x1000


class _SoftwareI2C:
    def __init__(self, scl, sda, address=0x5D, half_period=0.00001):
        self.scl, self.sda, self.address = scl, sda, address
        self.half_period = half_period

    def _delay(self):
        end = time.perf_counter() + self.half_period
        while time.perf_counter() < end:
            pass

    def _high(self):
        self.scl.set(1)  # open-drain: release, never push-pull high.
        end = time.monotonic() + 0.05
        while not self.scl.get():
            if time.monotonic() >= end:
                raise TimeoutError('TP_SCL stays low (MIO50): check reset/pull-up/wiring.')

    def _start(self):
        self.sda.set(1)
        self._high()
        self._delay()
        if not self.sda.get():
            raise RuntimeError('TP_SDA stays low (MIO51).')
        self.sda.set(0)
        self._delay()
        self.scl.set(0)

    def _stop(self):
        self.scl.set(0)
        self.sda.set(0)
        self._delay()
        self._high()
        self._delay()
        self.sda.set(1)
        self._delay()

    def _read_bit(self):
        self.sda.set(1)
        self._delay()
        self._high()
        self._delay()
        value = self.sda.get()
        self.scl.set(0)
        return value

    def _write_bit(self, value):
        self.sda.set(value)
        self._delay()
        self._high()
        self._delay()
        self.scl.set(0)

    def _write_byte(self, value):
        for bit in range(7, -1, -1):
            self._write_bit((value >> bit) & 1)
        if self._read_bit():
            raise OSError(errno.ENXIO, 'GT911 NACK at 0x{:02X}; check new bit/HWH and TP_RST.'.format(self.address))

    def _read_byte(self, acknowledge):
        value = 0
        for _ in range(8):
            value = (value << 1) | self._read_bit()
        self._write_bit(0 if acknowledge else 1)
        self.sda.set(1)
        return value

    def _transfer(self, register, count=None, payload=None):
        if not 0 <= register <= 0xFFFF:
            raise ValueError('Invalid 16-bit GT911 register.')
        if count is not None and not 1 <= count <= 64:
            raise ValueError('Read length must be 1..64.')
        failed = False
        try:
            self._start()
            self._write_byte(self.address << 1)
            self._write_byte(register >> 8)
            self._write_byte(register & 0xFF)
            if count is not None:
                self._start()
                self._write_byte((self.address << 1) | 1)
                return bytes(self._read_byte(i < count - 1) for i in range(count))
            for value in payload:
                self._write_byte(value)
        except BaseException:
            failed = True
            raise
        finally:
            try:
                self._stop()
            except Exception:
                if not failed:
                    raise

    def read(self, register, count):
        return self._transfer(register, count=count)

    def write(self, register, payload):
        return self._transfer(register, payload=bytes(payload))


class GT911Touch:
    """Polling prototype; use after loading the new touch bit and starting LCD.

    Keep this object alive. Call close() before changing Overlay or recreating it.
    GPIO line handles reserve pins so a competing Linux GPIO consumer fails safely.
    """
    def __init__(self):
        self.chip = None
        self.lines = {}
        self.slcr = None
        self.saved_mux = {}
        self.info = None
        try:
            from pynq import MMIO
            self.chip, chip_path, label = _open_gpiochip()
            # Request every line before changing MIO mux. EBUSY means stop.
            self.lines['reset'] = _Line(self.chip, 54, output=True, value=0)
            self.lines['int'] = _Line(self.chip, 0, output=True, value=0)
            self.lines['scl'] = _Line(self.chip, 50, output=True, open_drain=True, value=1)
            self.lines['sda'] = _Line(self.chip, 51, output=True, open_drain=True, value=1)
            self.slcr = MMIO(0xF8000000, 0x1000)
            self.saved_mux = {pin: int(self.slcr.read(0x700 + 4 * pin)) for pin in (0, 50, 51)}
            self._set_mux({pin: _gpio_mux_value(value) for pin, value in self.saved_mux.items()})
            # Linux goodix.c sequence, selecting 7-bit address 0x5D with INT low.
            time.sleep(0.02)
            self.lines['int'].set(0)
            time.sleep(0.001)
            self.lines['reset'].set(1)
            time.sleep(0.01)
            self.lines['int'].set(0)
            time.sleep(0.05)
            self.lines['int'].close()
            self.lines['int'] = _Line(self.chip, 0)
            self.bus = _SoftwareI2C(self.lines['scl'], self.lines['sda'])
            identity = self.bus.read(0x8140, 6)
            product = identity[:4].rstrip(b'\0').decode('ascii', 'replace')
            if product != '911':
                raise RuntimeError('Expected GT911; got product {!r}, raw={}. No config written.'.format(product, identity.hex()))
            resolution = self.bus.read(0x8048, 4)
            width, height = struct.unpack('<HH', resolution)
            self.info = {'product': product, 'firmware': int.from_bytes(identity[4:], 'little'),
                         'address': '0x5D', 'width': width, 'height': height,
                         'gpiochip': chip_path, 'gpio_label': label}
            print('GT911_OK:', self.info)
        except BaseException:
            try:
                self.close()
            except Exception:
                pass
            raise

    def _set_mux(self, values):
        was_locked = bool(int(self.slcr.read(0x0C)) & 1)
        if was_locked:
            self.slcr.write(0x08, 0xDF0D)
        try:
            for pin, value in values.items():
                self.slcr.write(0x700 + 4 * pin, value)
                if int(self.slcr.read(0x700 + 4 * pin)) != value:
                    raise RuntimeError('MIO{} pinmux write did not take effect.'.format(pin))
        finally:
            if was_locked:
                self.slcr.write(0x04, 0x767B)

    def read_points(self):
        """None=no fresh report; []=released; otherwise list of raw touch points."""
        if self.chip is None:
            raise RuntimeError('Touch object is closed.')
        status = self.bus.read(0x814E, 1)[0]
        if not status & 0x80:
            return None
        count = status & 0x0F
        if count > 5:
            self.bus.write(0x814E, b'\0')
            raise RuntimeError('GT911 reported invalid touch count: {}'.format(count))
        data = self.bus.read(0x814F, count * 8) if count else b''
        self.bus.write(0x814E, b'\0')  # Acknowledge every ready report, including release.
        return [{'id': data[i] & 0x0F, 'x': int.from_bytes(data[i + 1:i + 3], 'little'),
                 'y': int.from_bytes(data[i + 3:i + 5], 'little'),
                 'size': int.from_bytes(data[i + 5:i + 7], 'little')}
                for i in range(0, len(data), 8)]

    def monitor(self, seconds=15, interval=0.05):
        end = time.monotonic() + seconds
        previous = None
        while time.monotonic() < end:
            points = self.read_points()
            if points is not None and points != previous:
                print(points if points else 'released')
                previous = points
            time.sleep(interval)

    def close(self):
        errors = []
        # Release I2C before restoring mux. Keep reset high until handles are closed.
        for name in ('scl', 'sda', 'reset'):
            if name in self.lines and self.lines[name].fd is not None:
                try:
                    self.lines[name].set(1)
                except Exception as error:
                    errors.append(error)
        for line in self.lines.values():
            try:
                line.close()
            except Exception as error:
                errors.append(error)
        self.lines.clear()
        if self.slcr is not None and self.saved_mux:
            try:
                self._set_mux(self.saved_mux)
                self.saved_mux.clear()
            except Exception as error:
                errors.append(error)
        if self.chip is not None:
            chip, self.chip = self.chip, None
            try:
                os.close(chip)
            except Exception as error:
                errors.append(error)
        if errors:
            raise RuntimeError('Touch cleanup incomplete: {}'.format(errors))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
