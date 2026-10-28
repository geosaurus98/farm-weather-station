"""End-to-end: simulated receiver lines -> pipeline -> SQLite."""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from packet_decoder import STATUS_SENSOR_ERR, WeatherPacket, encode_packet, format_receiver_line
from pipeline import Pipeline
from simulator import SimConfig, simulate_lines
from storage import Storage

MM_PER_TIP = 0.2
FIXED_TIME = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def line_for(seq, tips, status=0, station=1):
    packet = WeatherPacket(1, station, seq, 1500, 6000, 101000, tips, 3600, status)
    return format_receiver_line(encode_packet(packet), -90, 5.0)


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmp.name) / "test.db"
        self.storage = Storage(self.db_path)

    def tearDown(self):
        self.storage.close()
        self._tmp.cleanup()

    def pipeline(self):
        return Pipeline(self.storage, MM_PER_TIP, clock=lambda: FIXED_TIME)

    def rows(self, sql):
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql).fetchall()

    def test_clean_simulation_stores_everything(self):
        p = self.pipeline()
        for line in simulate_lines(SimConfig(count=50, seed=1)):
            p.handle_line(line)
        stats = self.storage.link_stats(1)
        self.assertEqual((stats.received, stats.missing, stats.duplicates, stats.rejects),
                         (50, 0, 0, 0))

    def test_lossy_simulation_accounts_for_every_packet(self):
        p = self.pipeline()
        cfg = SimConfig(count=500, loss_rate=0.1, duplicate_rate=0.05, seed=7)
        for line in simulate_lines(cfg):
            p.handle_line(line)
        stats = self.storage.link_stats(1)
        # Without corruption, the last packet decides: unless it was lost, every
        # sequence number is either stored or counted as missing.
        (last_seq,) = self.rows("SELECT MAX(sequence) FROM packets")[0]
        self.assertEqual(stats.received + stats.missing, last_seq + 1)
        self.assertGreater(stats.missing, 0)
        self.assertGreater(stats.duplicates, 0)
        self.assertGreater(stats.loss_pct, 0)

    def test_rain_total_survives_packet_loss(self):
        # Cumulative counter: tips 0 -> 3 -> (lost 5) -> 9 must total 9 tips.
        p = self.pipeline()
        p.handle_line(line_for(0, 0, status=1))
        p.handle_line(line_for(1, 3))
        p.handle_line(line_for(3, 9))
        self.assertAlmostEqual(self.storage.total_rain_mm(1), 9 * MM_PER_TIP)

    def test_corrupt_and_diagnostic_lines(self):
        p = self.pipeline()
        good = line_for(0, 0)
        bad = good[:-12] + ("0" if good[-12] != "0" else "1") + good[-11:]
        p.handle_line("receiver: radio init ok")
        p.handle_line(bad)
        p.handle_line("RX,nothex,-1,0")
        p.handle_line("")
        self.assertEqual(self.rows("SELECT COUNT(*) FROM packets"), [(0,)])
        self.assertEqual(self.rows("SELECT COUNT(*) FROM rejects"), [(2,)])

    def test_sensor_error_stores_nulls(self):
        p = self.pipeline()
        p.handle_line(line_for(0, 0, status=STATUS_SENSOR_ERR))
        self.assertEqual(
            self.rows("SELECT temperature_c, humidity_pct, pressure_pa, battery_mv FROM packets"),
            [(None, None, None, 3600)],
        )

    def test_gateway_restart_keeps_rain_baseline(self):
        p = self.pipeline()
        p.handle_line(line_for(0, 0, status=1))
        p.handle_line(line_for(1, 4))
        restarted = self.pipeline()  # new tracker, seeded from the database
        restarted.handle_line(line_for(2, 6))
        self.assertEqual(self.rows("SELECT seq_status, rain_tips_delta FROM packets WHERE sequence = 2"),
                         [("ok", 2)])
        self.assertAlmostEqual(self.storage.total_rain_mm(1), 6 * MM_PER_TIP)

    def test_reception_timestamp_is_utc(self):
        p = self.pipeline()
        p.handle_line(line_for(0, 0))
        self.assertEqual(self.rows("SELECT received_utc FROM packets"),
                         [("2026-11-20T12:00:00+00:00",)])


if __name__ == "__main__":
    unittest.main()
