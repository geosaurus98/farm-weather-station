"""Read lines from the receiver's USB serial port (ST-LINK virtual COM port)."""

from __future__ import annotations

import logging
import time
from typing import Iterator

log = logging.getLogger(__name__)


def serial_lines(port: str, baudrate: int, reconnect_delay_s: float = 5.0) -> Iterator[str]:
    """Yield decoded lines forever, reconnecting if the port disappears."""
    import serial  # pyserial; imported here so tests and simulation don't need it

    while True:
        try:
            with serial.Serial(port, baudrate, timeout=1) as ser:
                log.info("opened %s at %d baud", port, baudrate)
                while True:
                    raw = ser.readline()
                    if raw:
                        yield raw.decode("ascii", errors="replace")
        except serial.SerialException as exc:
            log.error("serial error on %s: %s; retrying in %.0f s", port, exc, reconnect_delay_s)
            time.sleep(reconnect_delay_s)
