# Packet protocol

Status: **draft v1**, not yet frozen. Implemented on the host in `gateway/packet_decoder.py`. The node and receiver C code must match this document. If they disagree, this document is the reference and the code gets fixed.

## 1. Principles

- Binary over the air, not JSON (decision 5).
- **Explicit field-by-field serialisation.** Never `memcpy` a struct onto the wire; compiler layout and padding are not part of the protocol.
- **Little-endian** for all multi-byte fields, including the CRC.
- One-way telemetry, no acks or retries in v1 (decision 7). Loss is measured from `sequence` gaps.
- `rainfall_tips` is cumulative (decision 6), so loss doesn't lose rainfall.

## 2. Over-the-air frame (version 1)

The frame is 22 bytes: a 20-byte payload plus a 2-byte CRC.

| Offset | Size | Field | Type | Units / meaning |
|---:|---:|---|---|---|
| 0 | 1 | `version` | uint8 | Protocol version, `0x01` for this layout |
| 1 | 2 | `station_id` | uint16 | Node identifier |
| 3 | 4 | `sequence` | uint32 | Increments by 1 per transmitted packet |
| 7 | 2 | `temperature_centi_c` | int16 | °C × 100 (−327.68 to +327.67) |
| 9 | 2 | `humidity_centi_pct` | uint16 | %RH × 100 (0–10000) |
| 11 | 4 | `pressure_pa` | uint32 | Pa (e.g. 101325) |
| 15 | 2 | `rainfall_tips` | uint16 | **Cumulative** tip count, wraps at 65536 |
| 17 | 2 | `battery_mv` | uint16 | Battery voltage in mV |
| 19 | 1 | `status` | uint8 | Flag bits, see §4 |
| 20 | 2 | `crc16` | uint16 | CRC over bytes 0–19, see §3 |

The LoRa physical-layer packet length is 22. The receiver rejects nothing on length alone. It forwards everything and the gateway decides, so malformed packets are visible in the logs.

### Example

`station_id=1, sequence=42, 21.50 °C, 65.00 %RH, 101325 Pa, 17 tips, 3700 mV, status=0`

```
01 0100 2a000000 6608 6419 cd8b0100 1100 740e 00 12ce
```

Groups are: version, station_id, sequence, temperature, humidity, pressure, tips, battery, status, CRC (0xCE12, little-endian). The test suite (`gateway/tests/test_packet_decoder.py`) pins the exact bytes, including the CRC.

## 3. CRC

**CRC-16/CCITT-FALSE**: poly `0x1021`, init `0xFFFF`, no input/output reflection, xorout `0x0000`. Check value: `"123456789"` → `0x29B1`.

- Computed over the 20 payload bytes, appended little-endian.
- Why: it's small, widely documented, cheap bit-wise or table-driven on a Cortex-M4, and gives end-to-end integrity across the radio, receiver MCU and USB serial hops. The SX1262's own LoRa payload CRC should **also** be enabled, but it only covers the radio hop.
- A CRC is not authentication (see §6).

## 4. Status flags (draft)

| Bit | Name | Meaning |
|---:|---|---|
| 0 | `BOOT` | First packet since reset (sequence and rain counter may have restarted) |
| 1 | `SENSOR_ERR` | BME280 read failed. T/RH/P fields are not valid. |
| 2 | `LOW_BATT` | Battery below the node's low threshold |
| 3 | `WDT_RESET` | Last reset was caused by the IWDG |
| 4–7 | reserved | Send as 0. The gateway ignores them. |

## 5. Sequence, gaps, duplicates and resets

Gateway rules per `station_id`:

| Condition (`seq` vs last seen `last`) | Classification |
|---|---|
| No previous packet | `first` |
| `seq == last + 1` | `ok` |
| `seq == last` and same `rainfall_tips` | `duplicate`: logged in a separate table, not double-counted for rain (checked before `BOOT`, so a repeated boot packet is still a duplicate) |
| `BOOT` flag set, or `seq <= last` | `reset`: node rebooted, rain baseline restarts |
| `seq > last + 1` | `gap`: `seq − last − 1` packets missing |

Rain increment between consecutive stored packets is `(tips − last_tips) mod 65536`. After a reset it is the new `tips` value (counted since boot). Rain counted between the last packet before a reboot and the reboot is lost unless the node keeps the counter in a backup domain. **TODO(verify):** can the RTC backup registers on the L432 keep the tip count across resets? That would close this gap.

`sequence` is uint32. At one packet per 300 s it doesn't wrap within any realistic deployment.

## 6. Versioning and future authentication

- `version` is always byte 0. The gateway rejects unknown versions and logs them, and never guesses a layout.
- Any layout change bumps `version`. Frame length is decided by version.
- Planned path for authentication (needed before the node ever **accepts** commands, not for one-way v1 telemetry): a later version appends a truncated MAC (e.g. 4–8 bytes of AES-CMAC or HMAC over header + payload with a per-station key) between payload and CRC, or in place of it. `sequence` then also works as the replay counter, which is another reason not to let it reset freely.

## 7. Receiver → host serial format (draft)

The receiver writes one ASCII line per received LoRa packet on the ST-LINK virtual COM port:

```
RX,<payload hex>,<rssi_dbm>,<snr_db>\n
```

- `payload hex`: the full over-the-air frame (22 bytes → 44 hex chars), lower or upper case.
- `rssi_dbm`: integer, e.g. `-87`.
- `snr_db`: decimal, e.g. `7.25`.
- Example: `RX,0101002a00000066086419cd8b01001100740e0012ce,-87,7.25`

Lines that don't start with `RX,` are receiver diagnostics. The gateway logs and ignores them. ASCII hex costs about 2× the bytes, which doesn't matter at one packet per 5 minutes, and it is easy to read in a serial terminal.

The **host** adds the UTC reception timestamp. Measurement time (as opposed to reception time) is a later addition.

Baud rate: **TODO(verify)** when the receiver firmware is written (115200 assumed in `gateway/config.yaml`).
