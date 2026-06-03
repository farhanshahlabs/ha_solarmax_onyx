"""DataUpdateCoordinator for CloudInverter."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CloudInverterAPI, CloudInverterAuthError, CloudInverterApiError, _fetch_live_keys
from .const import DOMAIN, SCAN_INTERVAL_MINUTES

_LOGGER = logging.getLogger(__name__)


class CloudInverterCoordinator(DataUpdateCoordinator):
    """Polls all three CloudInverter endpoints and merges the results."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: CloudInverterAPI,
        goods_id: str,
        group_id: str = "",
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=SCAN_INTERVAL_MINUTES),
        )
        self._api = api
        self._goods_id = goods_id
        self._group_id = group_id
        self._session: aiohttp.ClientSession | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

        try:
            # Re-login if token is missing (first run or expiry)
            if not self._api._token:
                await self._api.async_login(self._session)

            raw = await self._api.async_fetch_all(self._session, self._goods_id, self._group_id)
        except CloudInverterAuthError:
            # Token expired or keys rotated — refresh keys, re-authenticate, retry
            _LOGGER.info("Auth error during poll — refreshing keys and re-authenticating")
            self._api._token = ""
            await _fetch_live_keys(self._session)
            await self._api.async_login(self._session)
            try:
                raw = await self._api.async_fetch_all(self._session, self._goods_id, self._group_id)
            except CloudInverterApiError as err:
                raise UpdateFailed(str(err)) from err
        except CloudInverterApiError as err:
            raise UpdateFailed(str(err)) from err

        return _parse(raw)


def _flt(val, default: float = 0.0) -> float:
    """Safe float conversion with a default."""
    try:
        return float(val) if val not in (None, "", "null") else default
    except (TypeError, ValueError):
        return default


def _arr(data: dict, key: str) -> list:
    """Return an array field from the info 'data' sub-dict, defaulting to []."""
    return data.get(key) or []


def _parse(raw: dict) -> dict[str, Any]:
    """Flatten API responses into a single dict of sensor values.

    Sources:
      m  = MemberMonitor      — account-wide (used ONLY for AllLight status)
      ps = GroupDetailList    — per-plant energy/power (fixes aggregate bug)
      f  = getHybridFlowgraph — per-device real-time flow
      i  = InverterDetailInfoNewone — full Information-tab data
    """
    m  = raw.get("monitor", {})
    ps = raw.get("plant_stats", {})   # per-plant inverter entry from GroupDetailList
    f  = raw.get("flow", {})
    i  = raw.get("info", {})

    lights   = m.get("AllLight", {})
    data     = i.get("data", {}) or {}
    esp32    = i.get("ESP32Version") or {}

    pbat_raw = _flt(f.get("Pbat"))   # negative = charging, positive = discharging

    # PV string arrays from info
    vdc = _arr(data, "Vdc")
    idc = _arr(data, "Idc")
    pdc = _arr(data, "Pdc")          # in kW — multiply ×1000 for W

    # Grid AC arrays (L1/L2/L3)
    vac = _arr(data, "Vac")          # grid voltages (V)
    iac = _arr(data, "Iac")          # grid currents (A)
    pac = _arr(data, "Pac")          # grid power per phase (kW)

    # Normal (home) load arrays
    vload = _arr(data, "Vload")
    iload = _arr(data, "Iload")
    pload = _arr(data, "Pload")      # kW

    # Backup / EPS load arrays
    veps = _arr(data, "Veps")
    ieps = _arr(data, "Ieps")
    peps = _arr(data, "Peps")        # kW

    # Operating status
    op_mode   = str(i.get("Operatingmode", ""))
    op_status = {"0": "Off_Grid", "1": "On_Grid", "2": "Backup"}.get(op_mode, op_mode)

    # Per-plant solar power & energy — from GroupDetailList (ps), NOT MemberMonitor
    # ps fields mirror MemberMonitor naming: CurrPac (W), EToday (Wh), ETotal (Wh), Htotal
    # Fall back to flow TotalDCpower if ps is unavailable.
    solar_power_w      = _flt(ps.get("CurrPac") or f.get("TotalDCpower"))
    solar_today_wh     = _flt(ps.get("EToday"))
    solar_total_wh     = _flt(ps.get("ETotal"))
    solar_hours        = _flt(ps.get("Htotal"))

    return {
        # ── Solar (per-plant, not account aggregate) ──────────────────────
        "solar_power":              solar_power_w,
        "solar_energy_today":       round(solar_today_wh / 1000, 2),
        "solar_energy_total":       round(solar_total_wh / 1000, 1),
        "solar_hours_total":        solar_hours,
        "solar_peak_power":         _flt(i.get("Peackpower")),

        # ── Grid & home load (real-time, from flow) ───────────────────────
        "grid_power":               _flt(f.get("gridCurrpac")),
        "home_load_power":          _flt(f.get("loadCurrpac")),

        # ── Grid measurements (from info) ─────────────────────────────────
        "grid_l1_voltage":          round(_flt(vac[0]) if vac else 0, 1),
        "grid_l1_current":          round(_flt(iac[0]) if iac else 0, 2),
        "grid_l1_power":            round(_flt(pac[0]) * 1000 if pac else 0, 0),
        "grid_frequency":           _flt(data.get("Fac") or i.get("Fac")),
        "grid_feedin_today":        _flt(i.get("EFeedin_today") or i.get("Efeedin_today")),
        "grid_feedin_total":        _flt(i.get("EFeedin_total") or i.get("Efeedin_total")),
        "grid_purchased_today":     _flt(i.get("Epurchased_today") or i.get("EPurchased_today")),
        "grid_purchased_total":     _flt(i.get("Epurchased_total") or i.get("EPurchased_total")),

        # ── Home / normal load ────────────────────────────────────────────
        "load_l1_voltage":          round(_flt(vload[0]) if vload else 0, 1),
        "load_l1_current":          round(_flt(iload[0]) if iload else 0, 2),
        "load_l1_power":            round(_flt(pload[0]) * 1000 if pload else 0, 0),
        "load_frequency":           _flt(data.get("Fload") or i.get("Fload")),
        "load_consumption_today":   _flt(i.get("ELoad_today")),
        "load_consumption_total":   _flt(i.get("ELoad_total")),

        # ── Backup / EPS load ─────────────────────────────────────────────
        "eps_l1_voltage":           round(_flt(veps[0]) if veps else 0, 1),
        "eps_l1_current":           round(_flt(ieps[0]) if ieps else 0, 2),
        "eps_l1_power":             round(_flt(peps[0]) * 1000 if peps else 0, 0),
        "eps_frequency":            _flt(data.get("Feps") or i.get("Feps")),
        "eps_consumption_today":    _flt(i.get("EEPS_today")),
        "eps_consumption_total":    _flt(i.get("EEPS_total")),

        # ── Battery (real-time) ───────────────────────────────────────────
        "battery_power":            abs(pbat_raw),
        "battery_charging":         pbat_raw < 0,
        "battery_soc":              _flt(f.get("SOC")),
        "battery_soh":              _flt(i.get("SOH")),
        "battery_voltage":          _flt(i.get("volt")),
        "battery_current":          _flt(i.get("cur")),
        "battery_temperature":      _flt(i.get("BMS_temp")),
        "battery_charging_power":   _flt(i.get("ChargingPower")),
        "battery_discharging_power":_flt(i.get("DischargingPower")),
        "battery_health_status":    i.get("BatteryHealthStatus", ""),
        "battery_brand":            i.get("brand", ""),
        "battery_capacity_ah":      _flt(i.get("capacity") or i.get("BatCapacity")),

        # ── Battery energy accumulation ───────────────────────────────────
        "battery_daily_charged":    _flt(i.get("Eday_batChrg")),
        "battery_daily_discharged": _flt(i.get("Eday_batDischrg")),
        "battery_total_charged":    _flt(i.get("Etotal_batChrg")),
        "battery_total_discharged": _flt(i.get("Etotal_batDischrg")),

        # ── BMS ───────────────────────────────────────────────────────────
        "bms_charge_limit_v":       _flt(i.get("BMS_chargeVolt") or i.get("BMS_chargelimitvolt")),
        "bms_charge_limit_a":       _flt(i.get("BMS_chargeCurr") or i.get("BMS_chargelimitcurr")),
        "bms_discharge_limit_v":    _flt(i.get("BMS_dischargeVolt") or i.get("BMS_dischargelimitvolt")),
        "bms_discharge_limit_a":    _flt(i.get("BMS_dischargeCurr") or i.get("BMS_dischargelimitcurr")),
        "bms_firmware":             i.get("BMS_FirmwareVersion") or i.get("BMSFirmware") or i.get("BMS_Firmware", ""),
        "bms_battery_count":        int(_flt(i.get("BMS_Num") or i.get("BMSNum"))),
        "bms_alarm":                int(_flt(i.get("BMS_Alarm") or i.get("BMSAlarm"))),
        "bms_protect":              int(_flt(i.get("BMS_Protect") or i.get("BMSProtect"))),

        # ── Inverter health ───────────────────────────────────────────────
        "inverter_temperature":     _flt(i.get("Tntc")),
        "inverter_status":          ("Normal"  if lights.get("Green", 0)  > 0 else
                                     "Warning" if lights.get("yellow", 0) > 0 else
                                     "Alarm"   if lights.get("red", 0)    > 0 else "Offline"),
        "inverter_operating_status": op_status,
        "inverter_firmware":        i.get("FirmwareVersion", ""),
        "self_consumption_rate":    _flt(i.get("Dailyself_userate")),
        "self_sufficiency_rate":    _flt(i.get("Dailyself_sufficiencyrate")),
        "comms_status":             esp32.get("Status", ""),
        "signal_strength":          _flt(i.get("Signal") or esp32.get("Signal")),

        # ── PV strings ────────────────────────────────────────────────────
        "pv1_voltage": round(_flt(vdc[0]) if len(vdc) > 0 else 0, 1),
        "pv1_current": round(_flt(idc[0]) if len(idc) > 0 else 0, 2),
        "pv1_power":   round(_flt(pdc[0]) * 1000 if len(pdc) > 0 else 0, 0),
        "pv2_voltage": round(_flt(vdc[1]) if len(vdc) > 1 else 0, 1),
        "pv2_current": round(_flt(idc[1]) if len(idc) > 1 else 0, 2),
        "pv2_power":   round(_flt(pdc[1]) * 1000 if len(pdc) > 1 else 0, 0),
        "pv3_voltage": round(_flt(vdc[2]) if len(vdc) > 2 else 0, 1),
        "pv3_current": round(_flt(idc[2]) if len(idc) > 2 else 0, 2),
        "pv3_power":   round(_flt(pdc[2]) * 1000 if len(pdc) > 2 else 0, 0),
    }
