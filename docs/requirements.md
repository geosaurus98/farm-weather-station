# Requirements (v1)

Status: draft, Phase 0. The source of truth for decisions is `CLAUDE.md`. This document turns it into checkable requirements.

## 1. Purpose

A wireless weather station for a farm in Canterbury, NZ, running on battery and solar. It logs data to a gateway and shows it on a live dashboard. It is also a portfolio project, so the low-power and reliability claims must be **measured and documented**, not assumed.

## 2. Functional requirements

| ID | Requirement | Verification |
|---|---|---|
| F-1 | Node measures air temperature, relative humidity and barometric pressure (BME280). | Bench comparison against a reference thermometer/hygrometer |
| F-2 | Node counts tipping-bucket rain gauge pulses, **including while in STOP mode**. Pulse counting does not depend on the measurement cycle. | STOP-mode wake test with N injected pulses → N counted |
| F-3 | Rain pulses are debounced (~50–100 ms window, final value set on the bench). | Bounce test with real reed switch |
| F-4 | Node measures battery voltage through a switched divider (no continuous drain). | Compare ADC reading to multimeter |
| F-5 | Node transmits one LoRa packet every **5 minutes (300 s)**, timed by RTC wake from STOP mode. | Timestamps in gateway log |
| F-6 | `rainfall_tips` is a cumulative counter, so a lost packet loses no rainfall. | Unit test + drop-packet simulation |
| F-7 | Packets use the binary format in `protocol.md` with a version field, station ID, sequence number and CRC. | Host unit tests |
| F-8 | Receiver (second STM32) forwards each received packet with RSSI and SNR over USB serial. | Bench test |
| F-9 | Gateway validates CRC and version, detects gaps and duplicates by sequence number, converts tips to mm (configurable mm/tip), and stores to SQLite with a UTC reception timestamp. | Host unit tests + simulator |
| F-10 | Gateway logs packet-loss percentage, battery voltage history and signal quality. | Dashboard / report |
| F-11 | Live dashboard (local web page over SQLite; Grafana optional). | Demo |
| F-12 | Node runs an independent watchdog (IWDG) and recovers from hangs. | Fault-injection test |

## 3. Non-functional requirements

| ID | Requirement | Notes |
|---|---|---|
| N-1 | **Range: 500 m** line-of-sight-ish farm link with acceptable packet loss. | Range test in 4–10 Jan window. Target loss to be set after first measurements. |
| N-2 | **Sleep current measured with debugger disconnected** and documented in `docs/power-budget.md`. | Headline portfolio claim. Nucleo ST-LINK, LED and regulator will inflate this; document the method. |
| N-3 | Runs indefinitely on a single cell + 1–2 W panel in Canterbury winter conditions. | Sized from measured current (decision 9) |
| N-4 | **Never charge Li-ion below 0 °C.** Use LiFePO4 or a charger with low-temperature cutoff. | Cold-charging check is mandatory |
| N-5 | Weatherproof: IP65 enclosure, cable glands; BME280 in a ventilated radiation shield away from the enclosure. | |
| N-6 | Station hardware budget about **NZ$200** (Raspberry Pi tracked separately; both Nucleos count in Order 1). | Tracked in `hardware/bom.csv` |
| N-7 | Drivers are kept separate from application logic so sensor, MCU or board can be swapped. | Code review |
| N-8 | Packet format leaves room for authentication (e.g. truncated MAC) before the node ever accepts commands. | Versioning in `protocol.md` |

## 4. Success criteria

1. STM32 reads T/RH/P, transmits every 5 minutes over LoRa, and the host validates and stores it.
2. Rain pulses are counted correctly even while the MCU is in STOP mode.
3. Measured sleep current (debugger disconnected) is documented in `docs/power-budget.md`.
4. At least one documented continuous stability test: **1 hour for v0.1**, then multi-day. Results in `docs/test-results.md`.
5. Station deployed outdoors on solar **before 20 January 2027**, ideally with 1+ week of clean data before departure. Go/no-go on 15 Jan 2027.
6. Station hardware within roughly NZ$200.

## 5. Out of scope for v1

Wind speed/direction, multiple nodes, OTA updates, alerts, custom PCB, LoRaWAN, acknowledgements and retries (add only if testing shows they are needed).

## 6. NZ radio compliance: OPEN, must close before outdoor transmission

The SX1262 breakouts are sold as "915 MHz" and example code usually assumes a **US915** configuration. **Do not assume that is legal in New Zealand.**

Before any outdoor transmission, check the current **NZ Radiocommunications (Short Range Devices) General User Radio Licence** (Radio Spectrum Management, rsm.govt.nz) and record here:

- [ ] Permitted frequency range in the 900 MHz band, and the exact centre frequency we'll use
- [ ] Maximum transmit power / EIRP for this modulation type (LoRa chirp spread spectrum)
- [ ] Any duty-cycle, bandwidth, or listen-before-talk conditions
- [ ] Antenna gain and how it counts towards EIRP (SX1262 TX power setting + antenna gain − cable loss)
- [ ] Equipment standards / labelling conditions that apply to hobby or prototype equipment
- [ ] Licence version and date checked

Result: _not yet checked_. Firmware radio config (frequency, power) must reference this section.

Bench rule: **never transmit without an antenna fitted.**
