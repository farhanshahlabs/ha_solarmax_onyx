"""CloudInverter sensor entities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, CONF_PLANT_NAME
from .coordinator import CloudInverterCoordinator


@dataclass(frozen=True)
class CloudInverterSensorDescription(SensorEntityDescription):
    key: str = ""


_W   = UnitOfPower.WATT
_KWH = UnitOfEnergy.KILO_WATT_HOUR
_V   = UnitOfElectricPotential.VOLT
_A   = UnitOfElectricCurrent.AMPERE
_C   = UnitOfTemperature.CELSIUS
_HZ  = UnitOfFrequency.HERTZ
_PCT = PERCENTAGE
_HRS = UnitOfTime.HOURS

_PWR  = SensorDeviceClass.POWER
_NRG  = SensorDeviceClass.ENERGY
_VLT  = SensorDeviceClass.VOLTAGE
_CUR  = SensorDeviceClass.CURRENT
_TMP  = SensorDeviceClass.TEMPERATURE
_BAT  = SensorDeviceClass.BATTERY
_FRQ  = SensorDeviceClass.FREQUENCY

_MEAS = SensorStateClass.MEASUREMENT
_TINC = SensorStateClass.TOTAL_INCREASING
_TOT  = SensorStateClass.TOTAL


def _s(key, name, unit=None, dc=None, sc=None, icon=None):
    """Shorthand factory for CloudInverterSensorDescription."""
    return CloudInverterSensorDescription(
        key=key, name=name,
        native_unit_of_measurement=unit,
        device_class=dc,
        state_class=sc,
        icon=icon,
    )


SENSORS: tuple[CloudInverterSensorDescription, ...] = (
    # ── Solar (per-plant — sourced from GroupDetailList, NOT aggregate MemberMonitor) ──
    _s("solar_power",           "Solar Power",            _W,   _PWR, _MEAS),
    _s("solar_energy_today",    "Solar Energy Today",     _KWH, _NRG, _TINC),
    _s("solar_energy_total",    "Solar Energy Total",     _KWH, _NRG, _TINC),
    _s("solar_hours_total",     "Solar Hours Total",      _HRS,       _TINC),
    _s("solar_peak_power",      "Solar Peak Power",       _W,   _PWR, _MEAS),

    # ── Grid real-time (from flow) ─────────────────────────────────────────────
    _s("grid_power",            "Grid Power",             _W,   _PWR, _MEAS),
    _s("home_load_power",       "Home Load Power",        _W,   _PWR, _MEAS),

    # ── Grid L1 measurements (from info) ──────────────────────────────────────
    _s("grid_l1_voltage",       "Grid L1 Voltage",        _V,   _VLT, _MEAS),
    _s("grid_l1_current",       "Grid L1 Current",        _A,   _CUR, _MEAS),
    _s("grid_l1_power",         "Grid L1 Power",          _W,   _PWR, _MEAS),
    _s("grid_frequency",        "Grid Frequency",         _HZ,  _FRQ, _MEAS),

    # ── Grid energy accumulation ───────────────────────────────────────────────
    _s("grid_feedin_today",     "Feed-in Energy Today",   _KWH, _NRG, _TINC),
    _s("grid_feedin_total",     "Total Feed-in Energy",   _KWH, _NRG, _TINC),
    _s("grid_purchased_today",  "Purchased Energy Today", _KWH, _NRG, _TINC),
    _s("grid_purchased_total",  "Total Purchased Energy", _KWH, _NRG, _TINC),

    # ── Home (normal) load ────────────────────────────────────────────────────
    _s("load_l1_voltage",         "Load L1 Voltage",          _V,   _VLT, _MEAS),
    _s("load_l1_current",         "Load L1 Current",          _A,   _CUR, _MEAS),
    _s("load_l1_power",           "Load L1 Power",            _W,   _PWR, _MEAS),
    _s("load_frequency",          "Load Frequency",           _HZ,  _FRQ, _MEAS),
    _s("load_consumption_today",  "Home Load Today",          _KWH, _NRG, _TINC),
    _s("load_consumption_total",  "Total Home Load",          _KWH, _NRG, _TOT),

    # ── Backup / EPS load ─────────────────────────────────────────────────────
    _s("eps_l1_voltage",          "Backup L1 Voltage",        _V,   _VLT, _MEAS),
    _s("eps_l1_current",          "Backup L1 Current",        _A,   _CUR, _MEAS),
    _s("eps_l1_power",            "Backup L1 Power",          _W,   _PWR, _MEAS),
    _s("eps_frequency",           "Backup Frequency",         _HZ,  _FRQ, _MEAS),
    _s("eps_consumption_today",   "Backup Load Today",        _KWH, _NRG, _TINC),
    _s("eps_consumption_total",   "Total Backup Load",        _KWH, _NRG, _TOT),

    # ── Battery real-time ─────────────────────────────────────────────────────
    _s("battery_power",             "Battery Power",              _W,   _PWR, _MEAS),
    _s("battery_soc",               "Battery State of Charge",    _PCT, _BAT, _MEAS),
    _s("battery_soh",               "Battery State of Health",    _PCT,       _MEAS),
    _s("battery_voltage",           "Battery Voltage",            _V,   _VLT, _MEAS),
    _s("battery_current",           "Battery Current",            _A,   _CUR, _MEAS),
    _s("battery_temperature",       "Battery Temperature",        _C,   _TMP, _MEAS),
    _s("battery_charging_power",    "Battery Charging Power",     _W,   _PWR, _MEAS),
    _s("battery_discharging_power", "Battery Discharging Power",  _W,   _PWR, _MEAS),
    _s("battery_health_status",     "Battery Health Status",      icon="mdi:battery-heart"),
    _s("battery_brand",             "Battery Brand",              icon="mdi:battery"),
    _s("battery_capacity_ah",       "Battery Capacity",           "Ah",       _MEAS),

    # ── Battery energy accumulation ───────────────────────────────────────────
    _s("battery_daily_charged",     "Battery Daily Charged",      _KWH, _NRG, _TINC),
    _s("battery_daily_discharged",  "Battery Daily Discharged",   _KWH, _NRG, _TINC),
    _s("battery_total_charged",     "Battery Total Charged",      _KWH, _NRG, _TINC),
    _s("battery_total_discharged",  "Battery Total Discharged",   _KWH, _NRG, _TINC),

    # ── BMS ───────────────────────────────────────────────────────────────────
    _s("bms_charge_limit_v",    "BMS Charge Limit Voltage",    _V,  _VLT, _MEAS),
    _s("bms_charge_limit_a",    "BMS Charge Limit Current",    _A,  _CUR, _MEAS),
    _s("bms_discharge_limit_v", "BMS Discharge Limit Voltage", _V,  _VLT, _MEAS),
    _s("bms_discharge_limit_a", "BMS Discharge Limit Current", _A,  _CUR, _MEAS),
    _s("bms_firmware",          "BMS Firmware Version",        icon="mdi:chip"),
    _s("bms_battery_count",     "BMS Battery Count",           icon="mdi:battery-multiple"),
    _s("bms_alarm",             "BMS Alarm Count",             icon="mdi:alarm-light"),
    _s("bms_protect",           "BMS Protect Count",           icon="mdi:shield"),

    # ── Inverter health ───────────────────────────────────────────────────────
    _s("inverter_temperature",      "Inverter Temperature",      _C, _TMP, _MEAS),
    _s("inverter_status",           "Inverter Status",           icon="mdi:power"),
    _s("inverter_operating_status", "Inverter Operating Status", icon="mdi:solar-power"),
    _s("inverter_firmware",         "Inverter Firmware",         icon="mdi:chip"),
    _s("self_consumption_rate",     "Self Consumption Rate",     _PCT,      _MEAS),
    _s("self_sufficiency_rate",     "Self Sufficiency Rate",     _PCT,      _MEAS),
    _s("comms_status",              "Communication Status",      icon="mdi:wifi"),
    _s("signal_strength",           "Signal Strength",           SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
                                                                 SensorDeviceClass.SIGNAL_STRENGTH, _MEAS),

    # ── PV strings ────────────────────────────────────────────────────────────
    _s("pv1_voltage", "PV1 Voltage", _V,  _VLT, _MEAS),
    _s("pv1_current", "PV1 Current", _A,  _CUR, _MEAS),
    _s("pv1_power",   "PV1 Power",   _W,  _PWR, _MEAS),
    _s("pv2_voltage", "PV2 Voltage", _V,  _VLT, _MEAS),
    _s("pv2_current", "PV2 Current", _A,  _CUR, _MEAS),
    _s("pv2_power",   "PV2 Power",   _W,  _PWR, _MEAS),
    _s("pv3_voltage", "PV3 Voltage", _V,  _VLT, _MEAS),
    _s("pv3_current", "PV3 Current", _A,  _CUR, _MEAS),
    _s("pv3_power",   "PV3 Power",   _W,  _PWR, _MEAS),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: CloudInverterCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        CloudInverterSensor(coordinator, entry, desc) for desc in SENSORS
    )


class CloudInverterSensor(CoordinatorEntity[CloudInverterCoordinator], SensorEntity):
    entity_description: CloudInverterSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CloudInverterCoordinator,
        entry: ConfigEntry,
        description: CloudInverterSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        plant_name = entry.data.get(CONF_PLANT_NAME, entry.title)
        # unique_id scoped to the plant so multiple plants don't clash
        self._attr_unique_id = f"{entry.data.get('group_id', entry.entry_id)}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=plant_name,          # plant name becomes the entity prefix in HA UI
            manufacturer=MANUFACTURER,
            model=entry.data.get("model", "SolarTouch"),
        )

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self.entity_description.key)
