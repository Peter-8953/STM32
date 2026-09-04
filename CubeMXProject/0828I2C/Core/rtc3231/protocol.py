"""Wire protocol for rtc3231: frame constants, CRC16, and (de)serialization.

This module only talks to bytes -- it knows nothing about the serial
port or about what a CMD means at the application level. That keeps it
independently testable (work-plan stage 1).
"""

from __future__ import annotations

from .exceptions import FrameError, CrcError

# --- Frame constants --------------------------------------------------------

SOF = b'\xAA\x55'           # Start-of-frame marker
VERSION = 0x01               # Protocol version, currently fixed
FRAME_OVERHEAD = 12          # SOF+VER+SRC+DST+CMD+SEQ+LEN+FLAGS+CRC (payload not included)

# Matches FRAME_PAYLOAD_MAX in frame_parser.h. The firmware's rx_buf is a
# fixed FRAME_MIN_LEN(12) + FRAME_PAYLOAD_MAX(32) = 44 bytes -- the LEN
# byte alone would technically allow payloads up to 255, but anything over
# 32 bytes built from this end would just get silently dropped by the
# firmware's recv_frame() (total > out_buf_size -> returns 0, frame never
# even reaches frame_parse()). From the PC side that looks exactly like an
# unexplained timeout with no indication of what actually went wrong, so
# build_frame() below fails fast instead, at the point the oversized frame
# is constructed.
FRAME_PAYLOAD_MAX = 32

# --- ID allocation -----------------------------------------------------------

ID_BROADCAST = 0x00
ID_PC = 0x01
# 0x02-0xFE: Arduino devices, assigned at flash time
ID_RESERVED = 0xFF           # must never be used as DST

# --- CMD codes -----------------------------------------------------------------

# PC -> Arduino
CMD_GET_TIME = 0x01
CMD_SET_TIME = 0x02
CMD_GET_TEMP = 0x03
CMD_GET_ID = 0x04

# Arduino -> PC
CMD_ACK = 0x10
CMD_DATA_TIME = 0x11
CMD_DATA_TEMP = 0x12
CMD_DATA_ID = 0x13

# Bidirectional
CMD_ERR = 0xFF

# --- FLAGS bits ------------------------------------------------------------------

FLAG_NEED_ACK = 0x01   # bit 0: peer must reply with ACK
FLAG_IS_ERROR = 0x02   # bit 1: this frame is an error response

# --- CMD_ERR payload[0] error codes (matches ERR_* in frame_parser.h) ------

ERR_UNKNOWN_CMD = 0x01         # unrecognized CMD value
ERR_PAYLOAD_TOO_SHORT = 0x02   # payload shorter than the command requires (currently only CMD_SET_TIME)


# --- CRC16 -------------------------------------------------------------------------

def crc16(data: bytes) -> int:
    """CRC16-CCITT (False variant): poly=0x1021, init=0xFFFF, no
    input/output reflection, no final XOR.

    Verification vector: crc16(b'123456789') == 0x29B1
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
        crc &= 0xFFFF
    return crc


# --- Frame (de)serialization ---------------------------------------------------------

def build_frame(src: int, dst: int, cmd: int, seq: int, payload: bytes, flags: int) -> bytes:
    """Build a complete binary frame ready to write to the serial port.

    Raises ValueError if any field doesn't fit its byte width, if the
    payload exceeds FRAME_PAYLOAD_MAX, or if dst is the reserved value
    0xFF.
    """
    for name, value in (("src", src), ("dst", dst), ("cmd", cmd), ("flags", flags)):
        if not (0 <= value <= 0xFF):
            raise ValueError(f"{name} out of range (0-255): {value}")
    if dst == ID_RESERVED:
        raise ValueError(f"dst must not be {ID_RESERVED:#04x} (reserved, forbidden for DST)")
    if not (0 <= seq <= 0xFFFF):
        raise ValueError(f"seq out of range (0-65535): {seq}")
    if len(payload) > FRAME_PAYLOAD_MAX:
        raise ValueError(
            f"payload too long: {len(payload)} bytes (firmware's rx_buf only has "
            f"room for FRAME_PAYLOAD_MAX={FRAME_PAYLOAD_MAX} bytes of payload -- "
            f"see frame_parser.h; a bigger payload would just look like an "
            f"unexplained timeout on the firmware side, not a clear error)"
        )

    body = bytes((
        VERSION,
        src,
        dst,
        cmd,
        (seq >> 8) & 0xFF,
        seq & 0xFF,
        len(payload),
    )) + payload + bytes((flags,))

    crc = crc16(body)
    return SOF + body + bytes(((crc >> 8) & 0xFF, crc & 0xFF))


def parse_frame(raw: bytes) -> tuple[int, int, bytes, int]:
    """Parse a complete binary frame, e.g. as returned by
    ``SerialTransport.recv()``.

    Returns (cmd, seq, payload, flags).
    Raises FrameError on malformed frames, CrcError on CRC mismatch.
    """
    if len(raw) < FRAME_OVERHEAD:
        raise FrameError(f"Frame too short: {len(raw)} bytes")
    if raw[0:2] != SOF:
        raise FrameError(f"Bad SOF: {raw[0:2]!r}")
    if raw[2] != VERSION:
        raise FrameError(f"Unsupported protocol version: {raw[2]:#04x}")

    cmd = raw[5]
    seq = (raw[6] << 8) | raw[7]
    length = raw[8]

    expected_total = FRAME_OVERHEAD + length
    if len(raw) != expected_total:
        raise FrameError(
            f"Length mismatch: LEN={length} implies {expected_total} total "
            f"bytes, got {len(raw)}"
        )

    payload = raw[9:9 + length]
    flags = raw[9 + length]
    received_crc = (raw[10 + length] << 8) | raw[11 + length]

    body = raw[2:10 + length]  # VER..FLAGS -- the range CRC is computed over
    calculated_crc = crc16(body)
    if calculated_crc != received_crc:
        raise CrcError(
            f"CRC mismatch: calculated {calculated_crc:#06x}, "
            f"received {received_crc:#06x}"
        )

    return cmd, seq, payload, flags