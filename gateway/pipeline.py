"""Receiver line -> decoded, tracked, stored packet."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from packet_decoder import DecodeError, decode_packet, parse_receiver_line
from storage import Storage
from tracking import SeqStatus, SequenceTracker

log = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Pipeline:
    def __init__(
        self,
        storage: Storage,
        mm_per_tip: float,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._storage = storage
        self._mm_per_tip = mm_per_tip
        self._clock = clock
        self._tracker = SequenceTracker()
        for station, (sequence, tips) in storage.last_states().items():
            self._tracker.seed(station, sequence, tips)

    def handle_line(self, line: str) -> None:
        received = self._clock()
        line = line.strip()
        if not line:
            return
        try:
            rx = parse_receiver_line(line)
            if rx is None:
                log.info("receiver: %s", line)
                return
            packet = decode_packet(rx.frame)
        except DecodeError as exc:
            log.warning("rejected line (%s): %s", exc, line)
            self._storage.store_reject(received, str(exc), line)
            return

        track = self._tracker.update(
            packet.station_id, packet.sequence, packet.rainfall_tips, packet.is_boot
        )
        self._storage.store_packet(received, rx, packet, track, self._mm_per_tip)

        if track.status is SeqStatus.GAP:
            log.warning("station %d: %d packet(s) missing before seq %d",
                        packet.station_id, track.missing, packet.sequence)
        elif track.status is SeqStatus.RESET:
            log.warning("station %d: reset detected at seq %d", packet.station_id, packet.sequence)
        log.debug("station %d seq %d %s rssi %d snr %.2f", packet.station_id,
                  packet.sequence, track.status.value, rx.rssi_dbm, rx.snr_db)
