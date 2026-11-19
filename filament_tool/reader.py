"""NFC reader: waits for spools and reports every scan.

Two kinds of readers, selected in the settings ("reader"):
- "usb":   USB reader via PC/SC (pyscard), e.g. ACR122U, ACR1252U
- "pn532": PN532 board, either via I2C on the Pi (PN532 V3 or Waveshare PN532 NFC HAT, no extra packages) or via
           USB as a serial port (PN532 boards with a USB-C/USB-UART chip in HSU mode, also on Windows; pyserial)
- "auto":  USB reader first, else PN532

Both return (uid, {block: 16 bytes}) for a spool on the reader; bambu_tag decodes it. Tags with a UID that is not
4 bytes (NTAG stickers) are reported by UID only.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from typing import Callable, Optional

from .bambu_tag import decode, derive_keys

log = logging.getLogger("reader")
BLOCKS = [b for b in range(0, 20) if b % 4 != 3]

# PC/SC also lists readers that cannot read NFC tags: the contact smart card readers built into many laptops
# (ThinkPad, Dell, HP: Alcor, Broadcom, O2Micro, Realtek), the SAM slot of ACS readers, Windows Hello and
# virtual smart cards, security keys. Known contactless readers are preferred; unknown ones are still tried.
_CONTACTLESS = re.compile(r"ACR12|ACR1252|ACR1255|ACR1281|ACR1552|PICC|contactless|\bCL\b|SCL3?7|uTrust|NFC|PN53", re.I)
_NOT_NFC = re.compile(r"\bSAM\b|\bICC\b|contacted|alcor|broadcom|o2 ?micro|realtek|rts5|microsoft|virtual|"
                      r"windows hello|yubi|nitrokey|feitian|smart ?card reader|smartcard reader|ccid", re.I)


def usable_readers(names: list) -> list:
    """Reader names that can read NFC tags, best first (see above)."""
    known = [n for n in names if _CONTACTLESS.search(str(n)) and not re.search(r"\bSAM\b", str(n), re.I)]
    return known + [n for n in names if n not in known and not _NOT_NFC.search(str(n))]

class ApduError(RuntimeError):
    """A tag is present but cannot be read (moved, not a Bambu tag)."""


SCAN_PAUSE = 0.5          # seconds the reader rests after a scan (setting "scan_pause_ms")


def scan_pause() -> float:
    try:
        from . import settings
        return max(0, int(settings.load().get("scan_pause_ms", 500))) / 1000
    except Exception:
        return SCAN_PAUSE
NOT_FOUND = {"No USB reader found", "No PN532 board found on USB"}


class NoReader(RuntimeError):
    """No reader of this kind is connected."""


# ---------------------------------------------------------------- USB / PC/SC

def _tx(conn, apdu):
    data, sw1, sw2 = conn.transmit(apdu)
    if (sw1, sw2) != (0x90, 0x00):
        raise ApduError(f"{bytes(apdu[:4]).hex()} -> {sw1:02X}{sw2:02X}")
    return data


def read_spool(conn):
    """Read UID and all data blocks of a Bambu tag via PC/SC. Returns (uid, None) for non-Bambu tags."""
    uid = bytes(_tx(conn, [0xFF, 0xCA, 0x00, 0x00, 0x00]))
    if len(uid) != 4:   # not a Bambu tag (MIFARE Classic has 4 bytes), e.g. an NTAG sticker: UID only
        return uid, None
    keys = derive_keys(uid[:4])
    out, sector = {}, -1
    for blk in BLOCKS:
        if blk // 4 != sector:
            sector = blk // 4
            _tx(conn, [0xFF, 0x82, 0x00, 0x00, 0x06, *keys[sector]])
            _tx(conn, [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, blk, 0x60, 0x00])
        out[blk] = bytes(_tx(conn, [0xFF, 0xB0, 0x00, blk, 0x10]))
    return uid, out


def plain_tag(uid: bytes) -> dict:
    """Retrofitted tag (e.g. an NTAG215 sticker): only its fixed UID, which gets linked to a spool."""
    h = uid.hex().upper()
    return {"plain": True, "uid": h, "tray_uid": "NFC-" + h}


class PcscBackend:
    kind = "usb"

    def __init__(self):
        try:
            from smartcard.System import readers
            from smartcard.Exceptions import CardConnectionException, NoCardException
        except ImportError:
            raise NoReader("pyscard is not installed")
        self._readers = readers
        self._nocard = (NoCardException, CardConnectionException)
        self.name = ""
        self._buzzer_for = None

    def probe(self) -> str:
        """Find a USB reader. Returns its name or raises NoReader."""
        try:
            rs = self._readers()
        except Exception as e:  # PC/SC service not reachable
            raise NoReader(f"PC/SC: {e}")
        rs = usable_readers(rs)
        if not rs:
            raise NoReader("No USB reader found")
        self._reader = rs[0]
        self.name = str(rs[0])
        return self.name

    def poll(self):
        """None = no spool on the reader, else (uid, blocks)."""
        name = self.name
        self.probe()   # unplugged? (listing readers is cheap)
        if self.name != name and name:
            raise NoReader(f"{name} unplugged")
        conn = self._reader.createConnection()
        try:
            conn.connect()
        except self._nocard[0]:
            return None
        except self._nocard[1] as e:
            # "no card" and "reader gone" both end up here on some systems (macOS): look again whether it is still there
            if self.name not in [str(r) for r in self._readers()]:
                raise NoReader(f"{self.name} unplugged")
            return None
        except Exception as e:
            raise NoReader(str(e))
        try:
            if self._buzzer_for != self.name and "ACR122" in self.name:
                # turn off the ACR122U's own beep; lasts until it is unplugged
                try:
                    conn.transmit([0xFF, 0x00, 0x52, 0x00, 0x00])
                except Exception:
                    pass
                self._buzzer_for = self.name
            return read_spool(conn)
        finally:
            try:
                conn.disconnect()
            except Exception:
                pass

    def close(self):
        self._buzzer_for = None


# ---------------------------------------------------------------- PN532 via I2C

I2C_SLAVE = 0x0703


class PN532Error(RuntimeError):
    pass


class PN532I2C:
    """Minimal PN532 driver (NXP UM0701-02) over /dev/i2c-N with just what MIFARE Classic needs."""

    def __init__(self, bus: int = 1, addr: int = 0x24):
        path = f"/dev/i2c-{bus}"
        if not os.path.exists(path):
            raise NoReader(f"{path} missing (I2C not enabled?)")
        try:
            import fcntl          # POSIX only; Windows has no I2C reader
            self.fd = os.open(path, os.O_RDWR)
            fcntl.ioctl(self.fd, I2C_SLAVE, addr)
        except OSError as e:
            raise NoReader(f"I2C {path}: {e.strerror}")
        self.addr = addr

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass

    def _write(self, data: bytes):
        try:
            os.write(self.fd, data)
        except OSError:
            # PN532 is in power-down – the first access wakes it, wait briefly and retry
            time.sleep(0.05)
            os.write(self.fd, data)

    def _read(self, n: int) -> bytes:
        return os.read(self.fd, n + 1)

    def _wait_ready(self, timeout: float) -> None:
        end = time.monotonic() + timeout
        while True:
            try:
                if self._read(0)[:1] == b"\x01":
                    return
            except OSError:
                pass
            if time.monotonic() > end:
                raise PN532Error("no response")
            time.sleep(0.005)

    def call(self, cmd: int, params: bytes = b"", n_resp: int = 32, timeout: float = 1.0) -> bytes:
        """Send one PN532 command frame, check the ACK and return the response payload."""
        body = bytes([0xD4, cmd]) + params
        ln = len(body)
        frame = bytes([0x00, 0x00, 0xFF, ln, (-ln) & 0xFF]) + body + bytes([(-sum(body)) & 0xFF, 0x00])
        self._write(frame)
        self._wait_ready(timeout)
        ack = self._read(6)[1:]
        if ack != b"\x00\x00\xFF\x00\xFF\x00":
            raise PN532Error(f"no ACK ({ack.hex()})")
        self._wait_ready(timeout)
        raw = self._read(n_resp + 8)[1:]
        i = raw.find(b"\x00\xFF")
        if i < 0 or i + 3 >= len(raw):
            raise PN532Error("invalid response")
        ln, lcs = raw[i + 2], raw[i + 3]
        if (ln + lcs) & 0xFF:
            raise PN532Error("length checksum")
        body = raw[i + 4:i + 4 + ln]
        if len(body) < 2 or body[0] != 0xD5 or body[1] != cmd + 1:
            raise PN532Error("wrong response")
        return body[2:]

    # --- commands
    def firmware(self) -> str:
        r = self.call(0x02, n_resp=6)
        return f"PN5{r[0]:02X} v{r[1]}.{r[2]}"

    def setup(self) -> None:
        self.call(0x14, bytes([0x01, 0x14, 0x01]))          # SAMConfiguration: normal mode, no IRQ
        self.call(0x32, bytes([0x05, 0xFF, 0x01, 0x02]))    # RFConfiguration: short search, returns without a card

    def select(self) -> Optional[bytes]:
        r = self.call(0x4A, bytes([0x01, 0x00]), n_resp=20, timeout=0.5)  # InListPassiveTarget, type A
        if not r or r[0] == 0:
            return None
        uid_len = r[5]
        return bytes(r[6:6 + uid_len])

    def auth(self, block: int, key: bytes, uid4: bytes) -> bool:
        r = self.call(0x40, bytes([0x01, 0x60, block]) + key + uid4, n_resp=4)
        return bool(r) and r[0] == 0x00

    def read_block(self, block: int) -> bytes:
        r = self.call(0x40, bytes([0x01, 0x30, block]), n_resp=20)
        if not r or r[0] != 0x00 or len(r) < 17:
            raise ApduError(f"Block {block} not readable")
        return bytes(r[1:17])

    def release(self) -> None:
        try:
            self.call(0x52, bytes([0x01]), n_resp=4)   # InRelease: put the card to sleep until it is removed
        except PN532Error:
            pass


class PN532Backend:
    kind = "pn532"

    def __init__(self, bus: int = 1, addr: int = 0x24):
        self.bus, self.addr = bus, addr
        self.dev: Optional[PN532I2C] = None
        self.name = ""

    def probe(self) -> str:
        """Open the PN532 on I2C if needed. Returns a description or raises NoReader."""
        if self.dev is None:
            dev = PN532I2C(self.bus, self.addr)
            try:
                fw = dev.firmware()
                dev.setup()
            except (PN532Error, OSError) as e:
                dev.close()
                raise NoReader(f"PN532 not responding on I2C-{self.bus} 0x{self.addr:02X} ({e})")
            self.dev = dev
            self.name = f"{fw} (I2C)"
        return self.name

    def poll(self):
        if self.dev is None:
            raise NoReader("PN532 not open")
        try:
            uid = self.dev.select()
            if uid is None:
                return None
            if len(uid) != 4:   # NTAG stickers and similar: UID only
                self.dev.release()
                return uid, None
            keys = derive_keys(uid[:4])
            out, sector = {}, -1
            for blk in BLOCKS:
                if blk // 4 != sector:
                    sector = blk // 4
                    if not self.dev.auth(blk, keys[sector], uid[:4]):
                        raise ApduError(f"Authentication of sector {sector} rejected")
                out[blk] = self.dev.read_block(blk)
            self.dev.release()
            return uid, out
        except ApduError:
            raise
        except Exception as e:      # PN532Error, OSError, serial and termios errors after unplugging
            self.close()
            raise NoReader(f"PN532: {e}")

    def close(self):
        if self.dev:
            self.dev.close()
        self.dev = None


# ---------------------------------------------------------------- PN532 over USB (serial, HSU mode)

# USB-to-serial chips found on PN532 boards with a USB port: CH340/CH341, CP210x, FTDI, PL2303.
# Only these ports are probed in "auto", so other serial devices (printers, microcontrollers) are left alone.
USB_UART_VIDS = {0x1A86, 0x10C4, 0x0403, 0x067B}
HSU_WAKEUP = b"\x55\x55" + b"\x00" * 14


def serial_ports(configured: str = "") -> list:
    """Serial ports that may hold a PN532: the configured one, else USB-UART adapters."""
    if configured:
        return [configured]
    try:
        from serial.tools import list_ports
    except ImportError:
        return []
    return [p.device for p in list_ports.comports() if p.vid in USB_UART_VIDS]


class PN532Serial(PN532I2C):
    """The PN532 driver above over a serial port (HSU, 115200 baud): same frames, no I2C status byte."""

    def __init__(self, port: str):
        try:
            import serial
        except ImportError:
            raise NoReader("pyserial is not installed")
        try:
            self.ser = serial.Serial(port, 115200, timeout=0.05, write_timeout=1)
        except (serial.SerialException, OSError) as e:
            raise NoReader(f"{port}: {e}")
        self.port = port
        self._awake = False

    def close(self):
        try:
            self.ser.close()
        except Exception:
            pass

    def _read_exact(self, n: int, end: float) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if chunk:
                buf += chunk
            elif time.monotonic() > end:
                raise PN532Error("no response")
        return buf

    def _sync(self, end: float) -> None:
        """Skip bytes up to and including the start code 00 FF."""
        prev = None
        while True:
            if time.monotonic() > end:            # steady noise without a start code must not loop forever
                raise PN532Error("no start code")
            b = self._read_exact(1, end)
            if prev == b"\x00" and b == b"\xff":
                return
            prev = b

    def call(self, cmd: int, params: bytes = b"", n_resp: int = 32, timeout: float = 1.0) -> bytes:
        body = bytes([0xD4, cmd]) + params
        ln = len(body)
        frame = bytes([0x00, 0x00, 0xFF, ln, (-ln) & 0xFF]) + body + bytes([(-sum(body)) & 0xFF, 0x00])
        if not self._awake:                       # the PN532 sleeps until it sees a long preamble
            frame = HSU_WAKEUP + frame
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self._awake = True
        end = time.monotonic() + timeout
        self._sync(end)                           # ACK: 00 00 FF 00 FF 00
        if self._read_exact(3, end) != b"\x00\xff\x00":
            raise PN532Error("no ACK")
        self._sync(end)                           # response: 00 00 FF LEN LCS D5 cmd+1 ... DCS 00
        ln, lcs = self._read_exact(2, end)
        if (ln + lcs) & 0xFF:
            raise PN532Error("length checksum")
        body = self._read_exact(ln + 2, end)[:ln]
        if len(body) < 2 or body[0] != 0xD5 or body[1] != cmd + 1:
            raise PN532Error("wrong response")
        return body[2:]


class PN532SerialBackend(PN532Backend):
    """PN532 on a USB serial port. Finds the port by itself unless one is configured (pn532_port)."""
    kind = "usb"

    def __init__(self, port: str = ""):
        self.port_cfg = port
        self.dev: Optional[PN532Serial] = None
        self.name = ""

    def probe(self) -> str:
        if self.dev is None:
            ports = serial_ports(self.port_cfg)
            if not ports:
                raise NoReader("No PN532 board found on USB")
            errors = []
            for port in ports:
                try:
                    dev = PN532Serial(port)
                except NoReader as e:
                    errors.append(str(e))
                    continue
                try:
                    dev.setup()              # after the wake-up the PN532 expects SAMConfiguration first
                    fw = dev.firmware()
                except Exception as e:       # PN532Error, OSError, termios errors while the port is still settling
                    dev.close()
                    errors.append(f"{port}: PN532 not responding ({e})")
                    continue
                self.dev = dev
                self.name = f"{fw} (USB, {port})"
                break
            if self.dev is None:
                raise NoReader(" · ".join(errors) + " (switch set to HSU/UART?)")
        return self.name

    def poll(self):
        # an unplugged USB-serial adapter often does not raise an error right away (reads just time out)
        if self.dev is not None and self.dev.port not in serial_ports(self.port_cfg) and not os.path.exists(self.dev.port):
            port = self.dev.port
            self.close()
            raise NoReader(f"{port} unplugged")
        return super().poll()


# ---------------------------------------------------------------- Thread

def make_backends(cfg: dict) -> list:
    """Reader backends to try for the configured mode, in order."""
    mode = cfg.get("reader", "auto")
    out = []
    if mode in ("auto", "usb"):                 # USB: PC/SC readers and PN532 boards with a USB-serial chip
        try:
            out.append(PcscBackend())
        except NoReader as e:
            log.info("PC/SC reader not available: %s", e)
        out.append(PN532SerialBackend(str(cfg.get("pn532_port") or "")))
    if mode in ("auto", "pn532") and sys.platform.startswith("linux"):     # I2C exists only on the Pi
        out.append(PN532Backend(int(cfg.get("pn532_bus", 1)), int(cfg.get("pn532_addr", 0x24))))
    return out


class ReaderThread(threading.Thread):
    """Calls on_tag(dict) for every newly placed spool and on_status(str, detail) when the status changes.

    get_cfg() returns the current settings; reload() picks the reader again (after a change in the options).
    """

    def __init__(self, on_tag: Callable[[dict], None], on_status: Callable[[str, str], None],
                 get_cfg: Callable[[], dict] = lambda: {}):
        super().__init__(daemon=True, name="reader")
        self.on_tag, self.on_status, self.get_cfg = on_tag, on_status, get_cfg
        self.status: Optional[str] = None
        self.kind: Optional[str] = None
        self._reload = threading.Event()

    def reload(self) -> None:
        self.status = None      # main.py reports "starting" meanwhile; the next status must be sent again even if it is "ready"
        self._reload.set()

    def _set(self, status: str, detail: str = "") -> None:
        if status != self.status or (status != "ready" and detail != getattr(self, "_detail", "")):
            log.debug("Reader status %s %s", status, detail)
            self.status, self._detail = status, detail
            self.on_status(status, detail)

    def _wait(self, sec: float) -> bool:
        """Sleep; returns True when the reader should be reloaded."""
        return self._reload.wait(sec)

    def run(self) -> None:
        while True:
            self._reload.clear()
            cfg = self.get_cfg() or {}
            try:
                backends = make_backends(cfg)
            except NoReader as e:
                self.kind = None
                self._set("missing", str(e))
                self._wait(10)
                continue
            try:
                self._loop(backends, cfg.get("reader", "auto"))
            except Exception as e:     # never let the thread die: the status would stay "ready" until a restart
                log.exception("Reader loop crashed, starting again: %s", e)
                self.kind = None
                self._set("disconnected", str(e))
                self._wait(2)
            for b in backends:
                try:
                    b.close()
                except Exception:
                    pass

    def _loop(self, backends: list, mode: str) -> None:
        # a spool that lay on the reader before a reload (e.g. switching the reader in the options) is not scanned again
        keep = getattr(self, "_last_uid", None) if time.monotonic() - getattr(self, "_seen", 0.0) < 5 else None
        last_uid, active, seen = keep, None, time.monotonic() if keep else 0.0
        fails = 0                # unexpected errors in a row
        pause_until = 0.0        # after a successful scan the reader rests a moment (no second read, no error beep)
        while not self._reload.is_set():
            self._last_uid, self._seen = last_uid, seen
            if active is None:
                errors = []
                for b in backends:
                    try:
                        b.probe()
                        active = b
                        break
                    except NoReader as e:
                        errors.append(str(e))
                    except Exception as e:      # e.g. a USB device still starting up right after plugging in
                        log.warning("Reader probe failed: %s", e)
                        errors.append(str(e))
                if active is None:
                    self.kind = None
                    errors = [e for e in errors if e not in NOT_FOUND]     # "nothing plugged in" needs no details
                    self._set("disconnected", " · ".join(errors) or "No reader found")
                    last_uid = None
                    if self._wait(2):
                        return
                    continue
                self.kind = active.kind
                self._set("ready", active.name)
            if time.monotonic() < pause_until:
                seen = time.monotonic()           # the spool still counts as lying on the reader
                if self._wait(0.2):
                    return
                continue
            try:
                res = active.poll()
            except NoReader as e:
                log.info("Reader gone: %s", e)
                active.close()
                active, last_uid = None, None
                self._set("disconnected", str(e))
                if self._wait(1):
                    return
                continue
            except ApduError as e:
                if last_uid is not None and time.monotonic() - seen < 3:
                    # glitch while the scanned spool is lifted or shifted: not worth an error beep
                    log.info("Read error right after a scan, ignored: %s", e)
                    if self._wait(0.5):
                        return
                    continue
                log.warning("Read error: %s", e)
                self.on_status("read_error", "Tag not readable (not a Bambu tag, or slipped)")
                if self._wait(1):
                    return
                continue
            except Exception as e:
                fails += 1
                log.warning("Error while reading (%d): %s", fails, e)
                if fails >= 3:      # keeps failing: treat it as unplugged, the probe above finds it again
                    active.close()
                    active, last_uid, fails = None, None, 0
                    self._set("disconnected", str(e))
                    if self._wait(1):
                        return
                    continue
                res = None
            else:
                fails = 0
            if res is None:
                if time.monotonic() - seen > 1.5:   # a spool counts as removed only after 1.5 s without it
                    last_uid = None
            else:
                uid, raw = res
                seen = time.monotonic()
                if uid != last_uid:
                    log.debug("Tag %s on %s (%s)", uid.hex() if isinstance(uid, bytes) else uid, active.name, "plain" if raw is None else "Bambu data")
                    last_uid = uid
                    try:
                        if raw is None:
                            self.on_tag(plain_tag(uid))
                        else:
                            self.on_tag(decode(uid, raw).to_dict())
                    except Exception as e:
                        log.warning("Tag decoding: %s", e)
                    pause_until = time.monotonic() + scan_pause()
            if self._wait(0.3):
                return
