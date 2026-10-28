import unittest

from tracking import SeqStatus, SequenceTracker, rain_tips_delta, tips_to_mm


class RainTest(unittest.TestCase):
    def test_delta(self):
        self.assertEqual(rain_tips_delta(10, 13), 3)
        self.assertEqual(rain_tips_delta(10, 10), 0)

    def test_delta_wraps_uint16(self):
        self.assertEqual(rain_tips_delta(65534, 1), 3)

    def test_tips_to_mm(self):
        self.assertAlmostEqual(tips_to_mm(5, 0.2), 1.0)
        self.assertEqual(tips_to_mm(0, 0.2), 0.0)


class SequenceTrackerTest(unittest.TestCase):
    def setUp(self):
        self.t = SequenceTracker()

    def test_first_without_boot_has_no_rain_baseline(self):
        r = self.t.update(1, 100, 50, boot=False)
        self.assertEqual(r.status, SeqStatus.FIRST)
        self.assertIsNone(r.rain_tips_delta)

    def test_first_with_boot_counts_tips_since_boot(self):
        r = self.t.update(1, 0, 2, boot=True)
        self.assertEqual(r.status, SeqStatus.FIRST)
        self.assertEqual(r.rain_tips_delta, 2)

    def test_consecutive(self):
        self.t.update(1, 5, 10, boot=False)
        r = self.t.update(1, 6, 12, boot=False)
        self.assertEqual((r.status, r.missing, r.rain_tips_delta), (SeqStatus.OK, 0, 2))

    def test_gap_recovers_rain_from_cumulative_counter(self):
        self.t.update(1, 5, 10, boot=False)
        r = self.t.update(1, 9, 17, boot=False)
        self.assertEqual((r.status, r.missing, r.rain_tips_delta), (SeqStatus.GAP, 3, 7))

    def test_duplicate_not_double_counted(self):
        self.t.update(1, 5, 10, boot=False)
        self.t.update(1, 6, 12, boot=False)
        r = self.t.update(1, 6, 12, boot=False)
        self.assertEqual(r.status, SeqStatus.DUPLICATE)
        self.assertIsNone(r.rain_tips_delta)
        self.assertEqual(self.t.update(1, 7, 12, boot=False).status, SeqStatus.OK)

    def test_duplicate_boot_packet_not_double_counted(self):
        self.t.update(1, 50, 100, boot=False)
        self.assertEqual(self.t.update(1, 0, 3, boot=True).status, SeqStatus.RESET)
        r = self.t.update(1, 0, 3, boot=True)
        self.assertEqual(r.status, SeqStatus.DUPLICATE)

    def test_sequence_going_backwards_is_reset(self):
        self.t.update(1, 50, 100, boot=False)
        r = self.t.update(1, 3, 4, boot=False)  # boot packet lost
        self.assertEqual((r.status, r.rain_tips_delta), (SeqStatus.RESET, 4))

    def test_boot_flag_is_reset(self):
        self.t.update(1, 50, 100, boot=False)
        r = self.t.update(1, 0, 0, boot=True)
        self.assertEqual((r.status, r.rain_tips_delta), (SeqStatus.RESET, 0))
        self.assertEqual(self.t.update(1, 1, 1, boot=False).status, SeqStatus.OK)

    def test_stations_are_independent(self):
        self.t.update(1, 5, 0, boot=False)
        self.assertEqual(self.t.update(2, 5, 0, boot=False).status, SeqStatus.FIRST)

    def test_seed_restores_baseline(self):
        self.t.seed(1, 10, 20)
        r = self.t.update(1, 11, 21, boot=False)
        self.assertEqual((r.status, r.rain_tips_delta), (SeqStatus.OK, 1))


if __name__ == "__main__":
    unittest.main()
