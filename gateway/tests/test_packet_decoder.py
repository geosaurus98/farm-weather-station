import unittest

from packet_decoder import (
    FRAME_LEN,
    PAYLOAD_LEN,
    STATUS_SENSOR_ERR,
    DecodeError,
    WeatherPacket,
    crc16_ccitt_false,
    decode_packet,
    encode_packet,
    format_receiver_line,
    parse_receiver_line,
)

EXAMPLE = WeatherPacket(
    version=1, station_id=1, sequence=42, temperature_centi_c=2150,
    humidity_centi_pct=6500, pressure_pa=101325, rainfall_tips=17,
    battery_mv=3700, status=0,
)
# Pinned bytes from docs/protocol.md; the C implementation must produce the same.
EXAMPLE_FRAME = bytes.fromhex("01 0100 2a000000 6608 6419 cd8b0100 1100 740e 00 12ce")


class Crc16Test(unittest.TestCase):
    def test_standard_check_value(self):
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)

    def test_empty_input_is_init_value(self):
        self.assertEqual(crc16_ccitt_false(b""), 0xFFFF)


class EncodeDecodeTest(unittest.TestCase):
    def test_lengths(self):
        self.assertEqual(PAYLOAD_LEN, 20)
        self.assertEqual(FRAME_LEN, 22)

    def test_encode_matches_pinned_bytes(self):
        self.assertEqual(encode_packet(EXAMPLE), EXAMPLE_FRAME)

    def test_decode_pinned_bytes(self):
        self.assertEqual(decode_packet(EXAMPLE_FRAME), EXAMPLE)

    def test_round_trip_extremes(self):
        for packet in (
            WeatherPacket(1, 0, 0, -32768, 0, 0, 0, 0, 0),
            WeatherPacket(1, 0xFFFF, 0xFFFFFFFF, 32767, 10000, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFF),
        ):
            self.assertEqual(decode_packet(encode_packet(packet)), packet)

    def test_negative_temperature_is_twos_complement_le(self):
        frame = encode_packet(WeatherPacket(1, 1, 0, -550, 0, 0, 0, 0, 0))
        self.assertEqual(frame[7:9], bytes([0xDA, 0xFD]))  # -550 = 0xFDDA
        self.assertAlmostEqual(decode_packet(frame).temperature_c, -5.5)

    def test_encode_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            encode_packet(WeatherPacket(1, 1, 0, 40000, 0, 0, 0, 0, 0))

    def test_every_single_bit_flip_is_detected(self):
        for i in range(FRAME_LEN):
            for bit in range(8):
                corrupted = bytearray(EXAMPLE_FRAME)
                corrupted[i] ^= 1 << bit
                with self.assertRaises(DecodeError):
                    decode_packet(bytes(corrupted))

    def test_bad_length(self):
        with self.assertRaisesRegex(DecodeError, "length"):
            decode_packet(EXAMPLE_FRAME[:-1])

    def test_unknown_version_rejected_even_with_valid_crc(self):
        frame = encode_packet(WeatherPacket(2, 1, 0, 0, 0, 0, 0, 0, 0))
        with self.assertRaisesRegex(DecodeError, "version"):
            decode_packet(frame)

    def test_sensor_error_flag(self):
        packet = WeatherPacket(1, 1, 0, 0, 0, 0, 0, 0, STATUS_SENSOR_ERR)
        self.assertFalse(packet.sensor_valid)
        self.assertTrue(EXAMPLE.sensor_valid)


class ReceiverLineTest(unittest.TestCase):
    def test_round_trip(self):
        line = format_receiver_line(EXAMPLE_FRAME, -87, 7.25)
        rx = parse_receiver_line(line + "\r\n")
        self.assertEqual(rx.frame, EXAMPLE_FRAME)
        self.assertEqual(rx.rssi_dbm, -87)
        self.assertAlmostEqual(rx.snr_db, 7.25)

    def test_uppercase_hex_accepted(self):
        rx = parse_receiver_line(f"RX,{EXAMPLE_FRAME.hex().upper()},-90,-3.5")
        self.assertEqual(rx.frame, EXAMPLE_FRAME)

    def test_diagnostic_line_ignored(self):
        self.assertIsNone(parse_receiver_line("receiver boot ok"))

    def test_malformed_lines(self):
        for line in ("RX,zz,-80,1.0", "RX,0102,-80", "RX,0102,abc,1.0", "RX,0102,-80,1.0,9"):
            with self.subTest(line=line), self.assertRaises(DecodeError):
                parse_receiver_line(line)


if __name__ == "__main__":
    unittest.main()
