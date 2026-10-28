# Farm Weather Station

**Status: planning** (Phase 0: repo skeleton, requirements, parts ordering)

A wireless, battery- and solar-powered weather station for a farm in Canterbury, New Zealand. A low-power STM32 node measures temperature, humidity, pressure, rainfall and battery voltage, and sends one LoRa packet every 5 minutes to a receiver that forwards it to a logging gateway and dashboard.

## Architecture

```
Remote node (battery/solar, STOP mode, RTC wake every 300 s)
  BME280 (I2C) ─┐
  Rain gauge ───┼─► STM32L432KC ─SPI─► SX1262
  Battery ADC ──┘                        │
                                         │  LoRa, point-to-point, one-way
                                         ▼
Receiver
  SX1262 ─SPI─► STM32L432KC  (appends RSSI/SNR)
                     │
                     │  USB serial (ST-LINK virtual COM port)
                     ▼
Gateway (laptop / Raspberry Pi)
  Python: validate CRC + version → detect gaps/duplicates → rain tips to mm → SQLite → web dashboard
```

- **Node firmware:** STM32CubeIDE + HAL in C, event-driven state machine, no RTOS. Radio via Semtech's SX126x driver (SWDR001) with project-specific HAL glue.
- **Packet:** 20-byte little-endian binary payload plus CRC-16. See [`docs/protocol.md`](docs/protocol.md).
- **Gateway:** Python service on a laptop (development) or Raspberry Pi (deployment), storing to SQLite.
- **Power:** battery first, solar sized from measured sleep current. See `docs/power-budget.md` (to come).

## Repository layout

| Path | Contents |
|---|---|
| `firmware/node/` | Remote station firmware (drivers in `Drivers/`, application logic in `App/`) |
| `firmware/receiver/` | Receiver firmware: LoRa RX → USB serial |
| `gateway/` | Python gateway: serial reader, packet decoder, SQLite storage, packet simulator |
| `dashboard/` | Local web dashboard |
| `hardware/` | BOM, wiring diagrams, datasheets |
| `docs/` | Requirements, protocol, pin check, power budget, test results |

## Gateway quick start (no hardware needed)

```bash
cd gateway
python3 -m unittest discover -s tests -v       # run unit tests
python3 main.py --simulate --count 50 --db sim.db   # simulated packets into SQLite
```

## Documents

- [Requirements](docs/requirements.md)
- [Packet protocol](docs/protocol.md)
- [Pin check](docs/pin-check.md)
- [Bill of materials](hardware/bom.csv)
