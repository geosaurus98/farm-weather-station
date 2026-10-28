"""SQLite storage for received packets and rejected lines."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from packet_decoder import ReceivedFrame, WeatherPacket
from tracking import SeqStatus, TrackResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS packets (
    id              INTEGER PRIMARY KEY,
    received_utc    TEXT    NOT NULL,   -- ISO 8601, added by the gateway
    station_id      INTEGER NOT NULL,
    sequence        INTEGER NOT NULL,
    version         INTEGER NOT NULL,
    temperature_c   REAL,               -- NULL when SENSOR_ERR is set
    humidity_pct    REAL,
    pressure_pa     INTEGER,
    rainfall_tips   INTEGER NOT NULL,   -- cumulative, as sent
    rain_tips_delta INTEGER,            -- NULL when no baseline
    rain_mm         REAL,               -- rain_tips_delta * mm_per_tip
    battery_mv      INTEGER NOT NULL,
    status          INTEGER NOT NULL,
    rssi_dbm        INTEGER NOT NULL,
    snr_db          REAL    NOT NULL,
    seq_status      TEXT    NOT NULL,
    missing_before  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_packets_station_time ON packets (station_id, received_utc);

CREATE TABLE IF NOT EXISTS duplicates (
    id           INTEGER PRIMARY KEY,
    received_utc TEXT    NOT NULL,
    station_id   INTEGER NOT NULL,
    sequence     INTEGER NOT NULL,
    rssi_dbm     INTEGER NOT NULL,
    snr_db       REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS rejects (
    id           INTEGER PRIMARY KEY,
    received_utc TEXT NOT NULL,
    reason       TEXT NOT NULL,
    raw_line     TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class LinkStats:
    received: int  # unique packets stored
    missing: int  # sum of sequence gaps
    duplicates: int
    rejects: int

    @property
    def loss_pct(self) -> float:
        expected = self.received + self.missing
        return 100.0 * self.missing / expected if expected else 0.0


class Storage:
    def __init__(self, path: str | Path) -> None:
        self._conn = sqlite3.connect(str(path))
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Storage":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def store_packet(
        self,
        received_utc: datetime,
        rx: ReceivedFrame,
        packet: WeatherPacket,
        track: TrackResult,
        mm_per_tip: float,
    ) -> None:
        timestamp = received_utc.isoformat()
        if track.status is SeqStatus.DUPLICATE:
            self._conn.execute(
                "INSERT INTO duplicates (received_utc, station_id, sequence, rssi_dbm, snr_db)"
                " VALUES (?, ?, ?, ?, ?)",
                (timestamp, packet.station_id, packet.sequence, rx.rssi_dbm, rx.snr_db),
            )
            self._conn.commit()
            return

        valid = packet.sensor_valid
        delta = track.rain_tips_delta
        self._conn.execute(
            """INSERT INTO packets (
                received_utc, station_id, sequence, version,
                temperature_c, humidity_pct, pressure_pa,
                rainfall_tips, rain_tips_delta, rain_mm,
                battery_mv, status, rssi_dbm, snr_db, seq_status, missing_before
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp,
                packet.station_id,
                packet.sequence,
                packet.version,
                packet.temperature_c if valid else None,
                packet.humidity_pct if valid else None,
                packet.pressure_pa if valid else None,
                packet.rainfall_tips,
                delta,
                delta * mm_per_tip if delta is not None else None,
                packet.battery_mv,
                packet.status,
                rx.rssi_dbm,
                rx.snr_db,
                track.status.value,
                track.missing,
            ),
        )
        self._conn.commit()

    def store_reject(self, received_utc: datetime, reason: str, raw_line: str) -> None:
        self._conn.execute(
            "INSERT INTO rejects (received_utc, reason, raw_line) VALUES (?, ?, ?)",
            (received_utc.isoformat(), reason, raw_line),
        )
        self._conn.commit()

    def last_states(self) -> dict[int, tuple[int, int]]:
        """Latest (sequence, rainfall_tips) per station, to seed the tracker on restart."""
        rows = self._conn.execute(
            """SELECT station_id, sequence, rainfall_tips FROM packets
               WHERE id IN (SELECT MAX(id) FROM packets GROUP BY station_id)"""
        ).fetchall()
        return {station: (seq, tips) for station, seq, tips in rows}

    def link_stats(self, station_id: int) -> LinkStats:
        received, missing = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(missing_before), 0) FROM packets WHERE station_id = ?",
            (station_id,),
        ).fetchone()
        (duplicates,) = self._conn.execute(
            "SELECT COUNT(*) FROM duplicates WHERE station_id = ?", (station_id,)
        ).fetchone()
        (rejects,) = self._conn.execute("SELECT COUNT(*) FROM rejects").fetchone()
        return LinkStats(received, missing, duplicates, rejects)

    def total_rain_mm(self, station_id: int) -> float:
        (total,) = self._conn.execute(
            "SELECT COALESCE(SUM(rain_mm), 0) FROM packets WHERE station_id = ?",
            (station_id,),
        ).fetchone()
        return total
