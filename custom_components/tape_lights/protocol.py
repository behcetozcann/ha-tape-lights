"""Packet encoder for "TAPE LIGHTS" BLE controllers (Rhythm Pro app).

Reverse engineered from the Rhythm Pro Android app (com.jingyuan.rhythm 1.2.8).
Every command is a 17 byte frame written without response to characteristic
0000fff3 inside service 49535343-fe7d-4be5-8fa9-9fafd205e455:

    [seq_lo, seq_hi, 0x20, x3, x4, rnd, cmd_lo, cmd_hi, p0..p7, crc_lo]

x3/x4 are 0x80 0x11, except for 10 byte parameters where the last two
parameter bytes go there. The CRC is CRC-16/CCITT seeded with ~rnd, and the
first 16 bytes are whitened with XOR_TABLE starting at index crc_lo & 31.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

SERVICE_UUID = "49535343-fe7d-4be5-8fa9-9fafd205e455"
WRITE_CHAR_UUID = "0000fff3-0000-1000-8000-00805f9b34fb"

CMD_POWER = 0x10
CMD_COLOR = 0x22
CMD_MIC_MODE = 0x54
CMD_MIC_SENSITIVITY = 0x56

XOR_TABLE = (
    55, 91, 30, 62, 100, 216, 212, 125, 133, 175, 155, 46, 94, 146, 120, 2,
    74, 67, 7, 98, 79, 196, 96, 33, 144, 121, 188, 1, 144, 222, 243, 181,
)


def _build_crc_table() -> tuple[int, ...]:
    table = []
    for index in range(256):
        crc = index << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
        table.append(crc & 0xFFFF)
    return tuple(table)


CRC_TABLE = _build_crc_table()


def _crc_low_byte(data: list[int], rnd: int) -> int:
    crc = (~rnd) & 0xFFFF
    for byte in data:
        crc = ((crc << 8) & 0xFFFF) ^ CRC_TABLE[(byte ^ (crc >> 8)) & 0xFF]
    return crc & 0xFF


def encode(cmd: int, params: list[int], seq: int | None = None, rnd: int | None = None) -> bytes:
    """Build one encrypted 17 byte frame."""
    seq = random.randint(0, 0xFFFF) if seq is None else seq & 0xFFFF
    rnd = random.randint(0, 0xFF) if rnd is None else rnd & 0xFF
    extra = params[8:10] if len(params) == 10 else [0x80, 0x11]
    body = [int(p) & 0xFF for p in params[:8]]
    body += [0] * (8 - len(body))
    frame = [seq & 0xFF, seq >> 8, 0x20, extra[0] & 0xFF, extra[1] & 0xFF, rnd,
             cmd & 0xFF, (cmd >> 8) & 0xFF, *body]
    key = _crc_low_byte(frame, rnd)
    index = key & 31
    for position in range(16):
        frame[position] ^= XOR_TABLE[index]
        index = (index + 1) & 31
    return bytes(frame + [key])


@dataclass(frozen=True)
class Frame:
    """A decoded frame, used by tests and for debugging captures."""

    seq: int
    cmd: int
    x3: int
    x4: int
    params: list[int]
    crc_ok: bool


def decode(raw: bytes) -> Frame:
    """Reverse encode(); raises ValueError on a malformed frame."""
    if len(raw) != 17:
        raise ValueError(f"expected 17 bytes, got {len(raw)}")
    key = raw[16]
    index = key & 31
    frame = list(raw[:16])
    for position in range(16):
        frame[position] ^= XOR_TABLE[index]
        index = (index + 1) & 31
    return Frame(
        seq=frame[0] | frame[1] << 8,
        cmd=frame[6] | frame[7] << 8,
        x3=frame[3],
        x4=frame[4],
        params=frame[8:16],
        crc_ok=frame[2] == 0x20 and _crc_low_byte(frame, frame[5]) == key,
    )


def power(on: bool) -> tuple[int, list[int]]:
    return CMD_POWER, [1 if on else 0]


def color(red: int, green: int, blue: int, brightness: int = 255) -> tuple[int, list[int]]:
    """Static color. The app scales channels by 0.9 * brightness + 0.1."""
    factor = 0.9 * (max(0, min(255, brightness)) / 255) + 0.1
    scaled = [int(channel * factor) for channel in (red, green, blue)]
    if not any(scaled):
        scaled = [1, 1, 1]
    return CMD_COLOR, scaled


def mic_mode(mode: int = 0) -> tuple[int, list[int]]:
    """Let the controller's own microphone drive the strip."""
    return CMD_MIC_MODE, [mode + 1]


def mic_sensitivity(value: int) -> tuple[int, list[int]]:
    """Sensitivity 0-100 around a centre of 50, as the app sends it."""
    value = max(0, min(100, value))
    if value >= 50:
        return CMD_MIC_SENSITIVITY, [1, value - 50]
    return CMD_MIC_SENSITIVITY, [0, 50 - value]
