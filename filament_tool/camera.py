"""Camera image of the Bambu printer (X1/H2 series: RTSPS on port 322) as small JPEG frames.

Only runs while someone is watching: every call to latest() keeps the stream alive, after IDLE seconds without
viewers the connection to the printer is closed. Two modes:
  "eco"    decode key frames only (about 1 frame per second, hardly any CPU)
  "smooth" decode every frame, output up to 5 frames per second (roughly one CPU core on a Pi)
  "max"    every frame the printer sends at its full resolution in high quality (up to 30 per second,
           several CPU cores on a Pi and much more network traffic)
In "eco" and "smooth" the preview is WIDTH pixels wide. While the large camera window is open (a viewer asks for
"hd"), those frames are also encoded at full resolution in high quality, as often as the mode allows.
The access code is part of the stream URL and is never logged or returned.
"""
from __future__ import annotations

import logging
import threading
import time
from fractions import Fraction
from typing import Callable, Optional

log = logging.getLogger(__name__)

try:
    import av  # PyAV, ships its own FFmpeg
except ImportError:  # pragma: no cover
    av = None

WIDTH = 640
IDLE = 20  # seconds without viewers before disconnecting
HD_IDLE = 6  # seconds without a full-resolution viewer before those frames are no longer encoded


def available() -> bool:
    return av is not None


class Camera:
    def __init__(self, get_cfg: Callable[[], Optional[dict]], get_mode: Callable[[], str]):
        self.get_cfg, self.get_mode = get_cfg, get_mode
        self.frame: Optional[bytes] = None
        self.seq = 0
        self.frame_hd: Optional[bytes] = None
        self.seq_hd = 0
        self._seen_hd = 0.0
        self.status, self.detail = "off", ""
        self._seen = 0.0
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._new = threading.Condition()

    def touch(self) -> None:
        """A viewer is present: start the stream or keep it alive."""
        self._seen = time.time()
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._run, daemon=True, name="camera")
                self._thread.start()

    def wait(self, seq: int, timeout: float = 5, hd: bool = False) -> tuple:
        """Wait for a frame newer than seq. Returns (seq, jpeg or None). hd: full resolution (large window)."""
        if hd and self.get_mode() == "max":
            hd = False   # every frame is full resolution already
        if hd:
            self._seen_hd = time.time()
        self.touch()
        with self._new:
            if hd:
                if self.seq_hd == seq:
                    self._new.wait(timeout)
                return self.seq_hd, self.frame_hd or self.frame   # the preview frame until the first full one
            if self.seq == seq:
                self._new.wait(timeout)
            return self.seq, self.frame

    def info(self) -> dict:
        return {"status": self.status, "detail": self.detail, "available": available()}

    def _set(self, status: str, detail: str = "") -> None:
        self.status, self.detail = status, detail

    def _run(self) -> None:
        while time.time() - self._seen < IDLE:
            cfg, mode = self.get_cfg(), self.get_mode()
            if not available():
                return self._set("error", "PyAV missing (pip install av)")
            if not cfg or mode not in ("eco", "smooth", "max"):
                return self._set("off")
            try:
                self._stream(cfg, mode)
            except Exception as e:  # connection error: wait a little and retry
                msg = str(e).replace(cfg["code"], "***")
                self._set("error", msg[:160] or type(e).__name__)
                log.info("Camera: %s", msg)
                time.sleep(5)
        self._set("off")
        self.frame = self.frame_hd = None

    def _stream(self, cfg: dict, mode: str) -> None:
        url = "rtsps://bblp:%s@%s:322/streaming/live/1" % (cfg["code"], cfg["ip"])
        self._set("starting")
        ct = av.open(url, options={"rtsp_transport": "tcp", "tls_verify": "0"}, timeout=10)
        try:
            vs = ct.streams.video[0]
            if mode == "eco":
                vs.codec_context.skip_frame = "NONKEY"
            else:
                vs.thread_type = "AUTO"
            enc, enc_hd, gap, last, last_hd = None, None, {"eco": 0, "smooth": 0.2}.get(mode, 0), 0.0, 0.0
            for fr in ct.decode(vs):
                if time.time() - self._seen > IDLE or self.get_mode() != mode or self.get_cfg() != cfg:
                    return
                now = time.time()
                if mode != "max" and now - self._seen_hd < HD_IDLE and now - last_hd >= gap:
                    last_hd = now
                    if enc_hd is None or (enc_hd.width, enc_hd.height) != (fr.width // 2 * 2, fr.height // 2 * 2):
                        enc_hd = _jpeg(fr.width // 2 * 2, fr.height // 2 * 2, 3)
                    hd = b"".join(bytes(p) for p in enc_hd.encode(
                        fr.reformat(width=enc_hd.width, height=enc_hd.height, format="yuvj420p")))
                    with self._new:
                        self.frame_hd, self.seq_hd = hd, self.seq_hd + 1
                        self._new.notify_all()
                elif now - self._seen_hd >= HD_IDLE:
                    self.frame_hd = None
                if now - last < gap:
                    continue
                last = now
                if mode == "max":   # the printer's full resolution, quality pinned high
                    w, h, q = fr.width // 2 * 2, fr.height // 2 * 2, 3
                else:
                    w, h, q = WIDTH, int(fr.height * WIDTH / fr.width) // 2 * 2, None
                if enc is None or (enc.width, enc.height) != (w, h):
                    enc = _jpeg(w, h, q)
                jpg = b"".join(bytes(p) for p in enc.encode(fr.reformat(width=w, height=h, format="yuvj420p")))
                with self._new:
                    self.frame, self.seq = jpg, self.seq + 1
                    self._new.notify_all()
                if self.status != "on":
                    self._set("on")
        finally:
            ct.close()


def _jpeg(width: int, height: int, quality: Optional[int] = None):
    """MJPEG encoder with a fixed quantizer (2 = best, 31 = worst). The "qscale" option is ignored by the
    encoder, so the quality is pinned with qmin/qmax. None keeps FFmpeg's default (small preview)."""
    enc = av.CodecContext.create("mjpeg", "w")
    enc.width, enc.height, enc.pix_fmt = width, height, "yuvj420p"
    enc.time_base = Fraction(1, 30)
    if quality:
        enc.qmin = enc.qmax = quality
    return enc
