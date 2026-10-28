# Farm Weather Station: Project Brief for Claude Code

Repo: `geosaurus98/farm-weather-station`
Owner: Jorge (final-year mechatronics student, University of Canterbury, Christchurch NZ). Goal is a portfolio-grade embedded project for graduate firmware/robotics/autonomy applications.

Save this file as `CLAUDE.md` in the repo root. Keep it updated as decisions change.

---

## 1. What we're building

A wireless, battery- and solar-powered weather station for a farm, with logging and a dashboard.

- **Remote node:** STM32L432KC (Nucleo-L432KC for the prototype) reading a BME280 (temperature, humidity, pressure), a tipping-bucket rain gauge and battery voltage. Sleeps in STOP mode, wakes every 5 minutes, transmits one LoRa packet.
- **Radio link:** point-to-point LoRa using SX1262 modules (SPI). Not LoRaWAN for v1.
- **Receiver:** a second STM32 (Nucleo-L432KC) with an SX1262, forwarding received packets over USB serial (ST-LINK virtual COM port) to the host.
- **Host / gateway:** Python service that reads serial, validates packets, and stores them. Runs on a laptop during development and on a Raspberry Pi for deployment.
- **Dashboard:** start with SQLite plus a simple local web page; Grafana (with Mosquitto + InfluxDB) only if time allows.
- **Power:** battery first, solar later, sized from measured current. LiFePO4 or a Li-ion charger with a low-temperature cutoff (Canterbury frosts; never charge Li-ion below 0 °C). Expect a 1–2 W panel and a single cell to be enough.

### v1 scope
Temperature, humidity, pressure, battery voltage, rain count, deep-sleep power management, solar charging, weatherproof enclosure, outdoor deployment, logging, live dashboard.

### Out of scope for v1 (stretch)
Wind speed/direction, multiple nodes, OTA firmware updates, low-battery/dry-soil alerts, custom PCB, LoRaWAN, packet acknowledgements and retries (add only if testing shows they are needed).

### Success criteria
- STM32 reads T/RH/P, transmits every 5 minutes over LoRa, and the host validates and stores it.
- Rain pulses are counted correctly even while the MCU is in STOP mode.
- Measured sleep current with the debugger disconnected, documented in `docs/power-budget.md`. This is the headline portfolio claim.
- At least one documented continuous stability test (1 hour for v0.1, then multi-day).
- Station deployed outdoors on solar before 20 January 2027, ideally with 1+ week of clean data before departure.
- Budget: roughly NZ$200 for station hardware. The Raspberry Pi is shared equipment and tracked separately. The second Nucleo (receiver) should be counted in Order 1.

---

## 2. Decisions already made (do not relitigate without asking)

1. Point-to-point LoRa, SPI SX1262 breakouts (not UART modems).
2. **Use Semtech's SX126x C driver (SWDR001)** and write only the HAL glue (SPI, GPIO, BUSY/DIO1 handling, delays). Do not write a radio driver from scratch.
3. Receiver is a **second STM32 over USB serial**, not an SX1262 wired directly to the Pi. SX126x support in Python on a Pi is patchy.
4. Firmware: STM32CubeIDE + HAL in C, a simple event-driven state machine, **no RTOS** (the node mostly sleeps).
5. Binary packet over the air, not JSON. Explicit serialisation and byte order, not compiler struct layout.
6. `rainfall_tips` is a **cumulative counter**, so a lost packet doesn't lose rainfall.
7. No acknowledgements or retries in v1. Measure reception reliability first.
8. SQLite first; MQTT/InfluxDB/Grafana later if time allows.
9. Measure current before buying solar parts.
10. Custom PCB is deferred to a possible v2.

---

## 3. Hardware

| Part | Notes |
|---|---|
| Nucleo-L432KC (x2) | One node, one receiver. The Nucleo's ST-LINK, LED and regulator inflate sleep current; plan to measure carefully and possibly move to a bare MCU later. |
| SX1262 915 MHz SPI breakout (x2) + antennas | Must expose NSS, SCK, MISO, MOSI, BUSY, DIO1, NRST. Check whether the board needs RF-switch (TXEN/RXEN) or TCXO control; wrong config can look like a successful TX with almost no RF output. Never transmit without an antenna fitted. |
| BME280 breakout | Genuine BME280, not BMP280 (no humidity). Mount in a ventilated radiation shield, away from the enclosure. |
| Tipping-bucket rain gauge | Reed-switch style pulse. Debounce ~50–100 ms; needs mm-per-tip calibration. |
| Battery divider | Switched resistor divider into an ADC pin, so it doesn't drain the battery. Allow settling time. |
| Enclosure / power | IP65 box, cable glands, solar charger with low-temp protection, low-quiescent 3.3 V regulator, 1–2 W panel. Ordered after measuring current. |

### Proposed STM32L432KC pin allocation: UNVERIFIED

These are conventional mappings and **must be checked against the Nucleo-32 user manual and the radio breakout schematic before use**. Some pins are tied to the onboard LED, the ST-LINK VCP, or Arduino-header solder bridges. Record the verified result in `docs/pin-check.md`.

| Signal | Pin |
|---|---|
| I2C1 SCL / SDA | PB6 / PB7 |
| SPI1 SCK / MISO / MOSI | PA5 / PA6 / PA7 |
| Radio NSS | PA4 |
| Radio DIO1 / BUSY / NRST | PB0 / PB1 / PA8 |
| Rain pulse | PA0 (wake source) |
| Battery ADC | PA1 |

Note: PA2/PA3 are normally the ST-LINK VCP UART on this board; plan debug UART accordingly.

### NZ radio compliance
Check frequency, transmit power, antenna gain and equipment against the NZ Short Range Devices General User Radio Licence before transmitting outdoors. Do not assume a US915 configuration is compliant. Flag this in `docs/requirements.md`.

---

## 4. Firmware architecture

Lifecycle: `BOOT/INIT -> SLEEP (STOP, RTC wake every 300 s) -> MEASURE (BME280, rain counter, battery ADC) -> TRANSMIT (build packet, CRC, LoRa TX) -> UPDATE STATE -> SLEEP`.

Rain GPIO interrupts wake the MCU independently of the 5-minute cycle; pulse accounting must not depend on the measurement cycle. Include an independent watchdog (IWDG).

Keep hardware drivers separate from application logic so the BME280, MCU or board can be swapped later.

```
farm-weather-station/
├── firmware/
│   ├── node/                 # remote station project
│   │   ├── Core/{Inc,Src}/
│   │   ├── Drivers/{bme280,sx1262}/   # sx1262 = SWDR001 + HAL glue
│   │   ├── App/
│   │   │   ├── weather_station.c
│   │   │   ├── sensor_manager.c
│   │   │   ├── rain_counter.c
│   │   │   ├── battery_monitor.c
│   │   │   ├── radio_manager.c
│   │   │   ├── packet_protocol.c
│   │   │   └── power_manager.c
│   │   └── tests/
│   └── receiver/             # second STM32: LoRa RX -> USB serial
├── gateway/
│   ├── main.py
│   ├── serial_receiver.py
│   ├── packet_decoder.py
│   ├── storage.py            # SQLite
│   ├── mqtt_publisher.py     # later
│   └── config.yaml
├── dashboard/
├── hardware/{diagrams,datasheets,bom.csv}
└── docs/{requirements,protocol,power-budget,pin-check,test-results}.md
```

Share the packet encode/decode and CRC code between node and receiver where possible, and unit-test it on the host.

### Packet (v1 draft, 20-byte payload before CRC/framing)

```c
typedef struct __attribute__((packed)) {
    uint8_t  version;
    uint16_t station_id;
    uint32_t sequence;
    int16_t  temperature_centi_c;
    uint16_t humidity_centi_pct;
    uint32_t pressure_pa;
    uint16_t rainfall_tips;     // cumulative
    uint16_t battery_mv;
    uint8_t  status;
} WeatherPacket;
```

Serialise field by field in a documented byte order (little-endian unless protocol.md says otherwise); do not memcpy the struct. Add a CRC. Plan for packet authentication (e.g. a truncated MAC) before the node ever accepts commands; not needed for one-way v1 telemetry, but don't design it out.

The receiver appends RSSI/SNR. The host adds a UTC reception timestamp. Later, distinguish reception time from measurement time.

---

## 5. Gateway

- Python reads the receiver's serial stream, validates CRC and version, detects gaps and duplicates via `sequence`, converts rain tips to mm (configurable mm/tip), and writes to SQLite.
- Run as a `systemd` service with automatic restart; persistent database on reliable storage (endurance/A2 SD or USB SSD on the Pi).
- Log packet-loss percentage, battery voltage history and signal quality; these make the deployment data credible.
- Develop and test against **simulated packets** so work isn't blocked on hardware.

---

## 6. Schedule

Constraints: last exam **4 Nov 2026**; Routeburn Track the week of **9 Nov** (no project work); away **20 Jan to 24 Feb 2027**. Part-time work Mon/Tue, so assume ~8–10 hours/week on this project.

| Dates | Focus | Done when |
|---|---|---|
| 28 Oct – 4 Nov | Phase 0: repo skeleton, requirements, pin check, licence check, **order Order 1 by ~30 Oct** | Parts ordered |
| 5 – 8 Nov | Rest / prep; unbox and check parts if they arrive | |
| 9 – 15 Nov | Routeburn, no work | |
| 16 – 22 Nov | STM32 peripherals, BME280 driver | T/RH/P over UART |
| 23 – 29 Nov | SX1262 TX/RX between two STM32s; receiver forwards to laptop | Test packets on laptop |
| 30 Nov – 6 Dec | Binary packet, CRC, sequence, station ID; logger; 1-hour stability test. **Order 2 and buy the Pi** | **v0.1 milestone** |
| 7 – 13 Dec | Rain pulse counting with STOP-mode wake test; battery divider/ADC; move logging to the Pi. **Order 3 by ~10 Dec** | Rain and battery in packets, logging on Pi |
| 14 – 20 Dec | RTC wake every 5 min; measure sleep current; write power budget; basic dashboard | `power-budget.md` with real numbers |
| 21 Dec – 3 Jan | Enclosure, radiation shield, battery/panel integration, cold-charging check (holiday buffer) | Station running on bench |
| 4 – 10 Jan | Outdoor solar run nearby; 500 m range test | Packet loss and battery trend logged |
| 11 – 17 Jan | Deploy by ~13 Jan; **go/no-go on 15 Jan** | 1+ week of clean data before leaving |

Fallback: if go/no-go is "no", run the station in the yard and do the farm deployment after returning in late February.

If behind: use a simple web page instead of Grafana, and skip retries. **Do not cut** the stability test, the power budget, or the cold-charging check.

---

## 7. Working agreements for Claude Code

- **Hardware is mine.** You can write, build and unit-test code, but you cannot flash, probe or measure. When something needs bench verification (RF output, sleep current, wake behaviour), say so and give me a precise test procedure rather than assuming it works.
- **Don't invent pin mappings, register values or datasheet facts.** If unsure, say what needs checking (Nucleo-32 user manual, SX1262 datasheet, breakout schematic) and mark the assumption in code with a `TODO(verify)` comment.
- **Use SWDR001** for the radio; don't hand-roll an SX126x driver.
- **Keep drivers and app logic separate** as per the layout above.
- Prefer small, reviewable commits with clear messages. One logical change per commit.
- Write host-side unit tests for packet encode/decode, CRC, sequence-gap detection and rain-tip conversion.
- Keep `docs/` current as decisions are made (`protocol.md`, `power-budget.md`, `pin-check.md`, `test-results.md`).
- Flag anything that threatens the schedule, the NZ radio compliance, or the low-power goal.
- Ask before changing a decision in section 2.

---

## 8. First tasks (Phase 0)

1. Create the folder skeleton with `.gitkeep` files, a `.gitignore` (CubeIDE `Debug/`/`Release/`, Python caches and venvs, local `.db` files), and a `README.md` with a short description, architecture overview and a "status: planning" line.
2. Write `docs/requirements.md` from section 1: 5-minute interval, 500 m range target, v1 measurements, NZ$200 budget, success criteria, NZ radio compliance note.
3. Write `docs/protocol.md` as a draft from section 4, including byte order, CRC choice and versioning.
4. Create `hardware/bom.csv` with the Order 1 parts (including the second Nucleo) and placeholder columns for supplier, price, and status.
5. Scaffold `gateway/` with a packet decoder and SQLite storage driven by a **simulated packet generator**, plus unit tests, so host-side work can proceed before hardware arrives.
6. Leave `docs/pin-check.md` as a template for me to fill in after reading the Nucleo-32 manual.
