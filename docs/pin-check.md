# Pin check: STM32L432KC (Nucleo-32)

Status: **TEMPLATE, not yet verified.** Jorge fills this in from the Nucleo-32 user manual (UM1956), the STM32L432KC datasheet, and the radio and BME280 breakout schematics. Firmware must not use a pin until its row is marked verified.

## Sources checked

| Document | Revision / date | Link or file |
|---|---|---|
| Nucleo-32 user manual (UM1956) | | |
| STM32L432KC datasheet (alternate-function table) | | |
| SX1262 breakout schematic | | |
| BME280 breakout schematic | | |

Board revision (printed on the Nucleo, e.g. MB1180 rev): ____

## Pin allocation

Proposed pins are from CLAUDE.md section 3 and are **unverified**.

| Signal | Proposed pin | Nucleo header pin (Arduino name) | Peripheral / AF | Solder bridge / conflict? | EXTI line | Verified? | Notes |
|---|---|---|---|---|---|---|---|
| I2C1 SCL | PB6 | | | | | ☐ | |
| I2C1 SDA | PB7 | | | | | ☐ | |
| SPI1 SCK | PA5 | | | | | ☐ | |
| SPI1 MISO | PA6 | | | | | ☐ | |
| SPI1 MOSI | PA7 | | | | | ☐ | |
| Radio NSS | PA4 | | | | | ☐ | |
| Radio DIO1 | PB0 | | | | | ☐ | Interrupt input |
| Radio BUSY | PB1 | | | | | ☐ | Input |
| Radio NRST | PA8 | | | | | ☐ | Output |
| Rain pulse | PA0 | | | | | ☐ | STOP-mode wake source. Debounce. Check EXTI line doesn't clash with DIO1. |
| Battery ADC | PA1 | | | | | ☐ | ADC channel: ___ |
| Battery divider enable | _TBD_ | | | | | ☐ | Switched divider gate |
| Radio TXEN / RXEN | _TBD_ | | | | | ☐ | Only if breakout needs them |
| Debug UART TX/RX | PA2 / PA15? | | | | | ☐ | PA2/PA3 are normally ST-LINK VCP. Confirm. |

## Things to check

- [ ] **Possible I2C/SPI clash, check first.** From memory (unverified), some Nucleo-32 boards ship with solder bridges (SB16/SB18) that link PA5/PA6 to PB6/PB7 for Arduino Nano compatibility. If that applies to this board, the proposed SPI1 SCK/MISO and I2C1 SCL/SDA are shorted together. Either remove the bridges or move I2C. Confirm the bridge IDs and default state in UM1956.
- [ ] Which pins are tied to the user LED (LD3), the ST-LINK VCP, or other solder bridges.
- [ ] That each proposed pin has the needed alternate function (I2C1, SPI1, ADC channel) in the datasheet AF table.
- [ ] EXTI line allocation: DIO1 and rain pulse must be on different EXTI lines, and both must be able to wake from STOP.
- [ ] Whether the rain input needs internal or external pull-up, and its effect on sleep current.
- [ ] The radio breakout's RF switch control (DIO2 as RF switch, or separate TXEN/RXEN) and TCXO supply (DIO3 voltage), which set `SetDIO2AsRfSwitchCtrl` / `SetDIO3AsTcxoCtrl` in the driver config.
- [ ] Logic levels: all breakouts at 3.3 V. Note any onboard regulators or level shifters, since they add sleep current.
- [ ] SWD pins (PA13/PA14) left free.

## Result

_Summary of changes from the proposed allocation, and the date verified._
