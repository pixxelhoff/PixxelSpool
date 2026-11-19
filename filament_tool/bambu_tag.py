"""Decrypt and decode Bambu Lab spool tags (MIFARE Classic 1K).

Key derivation and block layout as documented in
https://github.com/Bambu-Research-Group/RFID-Tag-Guide
"""
from __future__ import annotations

import hashlib
import hmac
import struct
from dataclasses import dataclass, asdict

# salt for HKDF-SHA256 (from the RFID Tag Guide)
_MASTER = bytes([0x9A, 0x75, 0x9C, 0xF2, 0xC4, 0xF7, 0xCA, 0xFF,
                 0x22, 0x2C, 0xB9, 0x76, 0x9B, 0x41, 0xBC, 0x96])
_CONTEXT = b"RFID-A\0"


def derive_keys(uid: bytes) -> list[bytes]:
    """Derive the 16 sector keys (key A, 6 bytes each) from the 4-byte UID."""
    prk = hmac.new(_MASTER, uid, hashlib.sha256).digest()
    okm, t, i = b"", b"", 1
    while len(okm) < 16 * 6:
        t = hmac.new(prk, t + _CONTEXT + bytes([i]), hashlib.sha256).digest()
        okm += t
        i += 1
    return [okm[k * 6:(k + 1) * 6] for k in range(16)]


def _s(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("ascii", "replace").strip()


def _u16(b: bytes, off: int) -> int:
    return struct.unpack_from("<H", b, off)[0]


@dataclass
class SpoolTag:
    uid: str
    variant_id: str        # block 1, e.g. "A00-W1"
    material_id: str       # block 1, e.g. "GFA00"
    filament_type: str     # block 2, e.g. "PLA"
    detailed_type: str     # block 4, e.g. "PLA Basic"
    color_rgba: str        # block 5
    weight_g: int          # block 5
    diameter_mm: float     # block 5
    drying_temp_c: int     # block 6
    drying_time_h: int     # block 6
    bed_temp_c: int        # block 6
    hotend_max_c: int      # block 6
    hotend_min_c: int      # block 6
    tray_uid: str          # block 9, the spool's serial number (hex)
    spool_width_mm: float  # block 10
    production: str        # block 12
    length_m: int          # block 14
    color_count: int       # block 16
    second_color_rgba: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def decode(uid: bytes, blocks: dict[int, bytes]) -> SpoolTag:
    """Turn the raw blocks of a Bambu tag into a SpoolTag."""
    b = blocks
    color_count = _u16(b[16], 2) if 16 in b and _u16(b[16], 0) == 2 else 1
    second = None
    if color_count > 1:
        second = b[16][4:8][::-1].hex().upper()  # stored as ABGR on the tag
    return SpoolTag(
        uid=uid.hex().upper(),
        variant_id=_s(b[1][0:8]),
        material_id=_s(b[1][8:16]),
        filament_type=_s(b[2]),
        detailed_type=_s(b[4]),
        color_rgba=b[5][0:4].hex().upper(),
        weight_g=_u16(b[5], 4),
        diameter_mm=round(struct.unpack_from("<f", b[5], 8)[0], 2),
        drying_temp_c=_u16(b[6], 0),
        drying_time_h=_u16(b[6], 2),
        bed_temp_c=_u16(b[6], 6),
        hotend_max_c=_u16(b[6], 8),
        hotend_min_c=_u16(b[6], 10),
        tray_uid=b[9].hex().upper(),
        spool_width_mm=_u16(b[10], 4) / 100,
        production=_s(b[12]),
        length_m=_u16(b[14], 4),
        color_count=color_count,
        second_color_rgba=second,
    )
