"""Simulated receiver output so gateway work can proceed without hardware.

Produces the same ``RX,<hex>,<rssi>,<snr>`` lines the receiver firmware will
emit, with optional packet loss, duplicates, corruption and node reboots.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterator

from packet_decoder import (
    PROTOCOL_VERSION,
    STATUS_BOOT,
    WeatherPacket,
    encode_packet,
    format_receiver_line,
)
from tracking import TIPS_MODULUS

INTERVAL_S = 300


@dataclass
class SimConfig:
    station_id: int = 1
    count: int = 288  # one day at 5-minute intervals
    loss_rate: float = 0.0
    duplicate_rate: float = 0.0
    corrupt_rate: float = 0.0
    reboot_at: int | None = None  # index of the packet at which the node reboots
    start_tips: int = 0
    seed: int | None = None


def simulate_lines(cfg: SimConfig) -> Iterator[str]:
    rng = random.Random(cfg.seed)
    sequence = 0
    tips = cfg.start_tips
    boot = True

    for i in range(cfg.count):
        if cfg.reboot_at is not None and i == cfg.reboot_at:
            sequence, tips, boot = 0, 0, True

        # Rough diurnal cycle for a Canterbury spring day.
        phase = 2 * math.pi * (i * INTERVAL_S) / 86400
        temperature = 12.0 + 6.0 * math.sin(phase - math.pi / 2) + rng.gauss(0, 0.2)
        humidity = min(100.0, max(0.0, 70.0 - 15.0 * math.sin(phase - math.pi / 2) + rng.gauss(0, 1)))
        pressure = 101300 + int(rng.gauss(0, 30))
        if rng.random() < 0.05:
            tips = (tips + rng.randint(1, 3)) % TIPS_MODULUS
        battery = 3700 - i // 50

        packet = WeatherPacket(
            version=PROTOCOL_VERSION,
            station_id=cfg.station_id,
            sequence=sequence,
            temperature_centi_c=round(temperature * 100),
            humidity_centi_pct=round(humidity * 100),
            pressure_pa=pressure,
            rainfall_tips=tips,
            battery_mv=battery,
            status=STATUS_BOOT if boot else 0,
        )
        sequence += 1
        boot = False

        if rng.random() < cfg.loss_rate:
            continue

        frame = bytearray(encode_packet(packet))
        if rng.random() < cfg.corrupt_rate:
            frame[rng.randrange(len(frame))] ^= 1 << rng.randrange(8)
        line = format_receiver_line(bytes(frame), rssi_dbm=rng.randint(-110, -70),
                                    snr_db=round(rng.uniform(-5, 10), 2))
        yield line
        if rng.random() < cfg.duplicate_rate:
            yield line
