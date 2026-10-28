"""Wire format for weather packets (see docs/protocol.md).

Encoding lives here too so the simulator and tests produce frames with the
same code path the decoder checks against. Every field is packed explicitly,
little-endian, with no reliance on struct padding.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PROTOCOL_VERSION = 1

# version, station_id, sequence, temperature, humidity, pressure, tips, battery, status
_PAYLOAD_FORMAT = "<BHIhHIHHB"
PAYLOAD_LEN = struct.calcsize(_PAYLOAD_FORMAT)  # 20
CRC_LEN = 2
FRAME_LEN = PAYLOAD_LEN + CRC_LEN  # 22

# Status flag bits (docs/protocol.md section 4)
STATUS_BOOT = 1 << 0
STATUS_SENSOR_ERR = 1 << 1
STATUS_LOW_BATT = 1 << 2
STATUS_WDT_RESET = 1 << 3

RECEIVER_LINE_PREFIX = "RX,"


class DecodeError(ValueError):
    """A frame or receiver line could not be decoded."""


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, no reflection, xorout 0."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class WeatherPacket:
    version: int
    station_id: int
    sequence: int
    temperature_centi_c: int
    humidity_centi_pct: int
    pressure_pa: int
    rainfall_tips: int
    battery_mv: int
    status: int

    @property
    def temperature_c(self) -> float:
        return self.temperature_centi_c / 100.0

    @property
    def humidity_pct(self) -> float:
        return self.humidity_centi_pct / 100.0

    @property
    def sensor_valid(self) -> bool:
        return not self.status & STATUS_SENSOR_ERR

    @property
    def is_boot(self) -> bool:
        return bool(self.status & STATUS_BOOT)


@dataclass(frozen=True)
class ReceivedFrame:
    """One line from the receiver: raw frame plus radio metadata."""

    frame: bytes
    rssi_dbm: int
    snr_db: float


def encode_packet(packet: WeatherPacket) -> bytes:
    """Serialise a packet to a full over-the-air frame (payload + CRC)."""
    try:
        payload = struct.pack(
            _PAYLOAD_FORMAT,
            packet.version,
            packet.station_id,
            packet.sequence,
            packet.temperature_centi_c,
            packet.humidity_centi_pct,
            packet.pressure_pa,
            packet.rainfall_tips,
            packet.battery_mv,
            packet.status,
        )
    except struct.error as exc:
        raise ValueError(f"field out of range: {exc}") from exc
    return payload + struct.pack("<H", crc16_ccitt_false(payload))


def decode_packet(frame: bytes) -> WeatherPacket:
    """Validate length, CRC and version, then decode a frame."""
    if len(frame) != FRAME_LEN:
        raise DecodeError(f"bad length: {len(frame)} bytes, expected {FRAME_LEN}")
    payload, crc_bytes = frame[:PAYLOAD_LEN], frame[PAYLOAD_LEN:]
    (received_crc,) = struct.unpack("<H", crc_bytes)
    computed_crc = crc16_ccitt_false(payload)
    if received_crc != computed_crc:
        raise DecodeError(
            f"bad CRC: received 0x{received_crc:04X}, computed 0x{computed_crc:04X}"
        )
    if payload[0] != PROTOCOL_VERSION:
        raise DecodeError(f"unsupported version: {payload[0]}")
    return WeatherPacket(*struct.unpack(_PAYLOAD_FORMAT, payload))


def parse_receiver_line(line: str) -> ReceivedFrame | None:
    """Parse ``RX,<hex>,<rssi>,<snr>``.

    Returns None for receiver diagnostic lines (anything not starting with
    ``RX,``). Raises DecodeError for malformed RX lines.
    """
    line = line.strip()
    if not line.startswith(RECEIVER_LINE_PREFIX):
        return None
    parts = line.split(",")
    if len(parts) != 4:
        raise DecodeError(f"expected 4 comma-separated fields, got {len(parts)}")
    _, hex_frame, rssi, snr = parts
    try:
        frame = bytes.fromhex(hex_frame)
    except ValueError as exc:
        raise DecodeError(f"bad hex payload: {exc}") from exc
    try:
        return ReceivedFrame(frame=frame, rssi_dbm=int(rssi), snr_db=float(snr))
    except ValueError as exc:
        raise DecodeError(f"bad RSSI/SNR: {exc}") from exc


def format_receiver_line(frame: bytes, rssi_dbm: int, snr_db: float) -> str:
    """Inverse of parse_receiver_line, used by the simulator and tests."""
    return f"{RECEIVER_LINE_PREFIX}{frame.hex()},{rssi_dbm},{snr_db:.2f}"
