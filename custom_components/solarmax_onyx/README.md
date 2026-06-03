# SolarTouch — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Monitor your solar inverter in Home Assistant using your [CloudInverter.net](https://www.solarmax_onyx.net) account. Supports hybrid inverters with battery storage.

## Features

- **30 sensors** — solar power, battery SOC/SOH/voltage/temp, grid power, home load, PV strings, self-consumption rate, and more
- **Animated power flow card** — live diagram showing energy flow between solar, battery, grid, and home (requires [power-flow-card-plus](https://github.com/flixlix/power-flow-card-plus))
- **Automatic updates** every 5 minutes
- **Config flow UI** — set up via Settings → Integrations, no YAML required
- **Multi-device support** — select from multiple inverters on the same account

## Supported Inverters

Any inverter visible on CloudInverter.net. Tested with:

- SM-ONYX-UL-10KW (hybrid, 10 kW)

## Installation

### Via HACS (recommended)

1. In HACS, go to **Integrations → Custom repositories**
2. Add `https://github.com/sayedamjad/ha_integrations` as an **Integration**
3. Search for **SolarTouch** and download it
4. Restart Home Assistant

### Manual

1. Copy the `custom_components/solarmax_onyx` folder into your HA `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **SolarTouch**
3. Enter your CloudInverter.net username and password
4. If you have multiple inverters, select the one to monitor
5. Done — sensors appear immediately

## Sensors

| Sensor | Unit | Description |
|--------|------|-------------|
| Solar Power | W | Current AC output |
| Solar Energy Today | kWh | Energy generated today |
| Solar Energy Total | kWh | Lifetime energy |
| Solar Peak Power | W | Highest output ever |
| Grid Power | W | Import (+) / Export (−) |
| Home Load Power | W | Current home consumption |
| Battery Power | W | Charge/discharge power |
| Battery SOC | % | State of charge |
| Battery SOH | % | State of health |
| Battery Voltage | V | Terminal voltage |
| Battery Current | A | Charge/discharge current |
| Battery Temperature | °C | BMS temperature |
| Battery Total Charged | kWh | Lifetime energy in |
| Battery Total Discharged | kWh | Lifetime energy out |
| Inverter Temperature | °C | Heat sink temperature |
| Inverter Status | — | Normal / Warning / Alarm / Offline |
| Inverter Operating Status | — | Off_Grid / On_Grid / Backup |
| Self Consumption Rate | % | Daily self-consumption |
| Self Sufficiency Rate | % | Daily self-sufficiency |
| Communication Status | — | Online / Offline |
| PV1/2/3 Voltage | V | Per-string voltage |
| PV1/2/3 Current | A | Per-string current |
| PV1/2/3 Power | W | Per-string power |

## Power Flow Card

Install [power-flow-card-plus](https://github.com/flixlix/power-flow-card-plus) via HACS Frontend, then add this card to your dashboard:

```yaml
type: custom:power-flow-card-plus
entities:
  grid:
    entity: sensor.solarmax_onyx_grid_power
  solar:
    entity: sensor.solarmax_onyx_solar_power
  battery:
    entity: sensor.solarmax_onyx_battery_power
    state_of_charge: sensor.solarmax_onyx_battery_soc
  home:
    entity: sensor.solarmax_onyx_home_load_power
```

## Technical Notes

- Authentication uses AES-CBC signed request bodies (reverse-engineered from the CloudInverter.net JavaScript bundle)
- The `cryptography` library (built into Home Assistant) is used for AES — no extra dependencies required
- API polling is cloud-based; an internet connection is required

## Contributing

Pull requests welcome. Please open an issue first to discuss any significant changes.

## License

MIT
