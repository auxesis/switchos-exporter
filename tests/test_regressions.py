"""Regression tests, one per bug fixed during this session.

Each test pins the behaviour of a specific fix so it can't silently regress.
"""
import re

import pytest

from conftest import collect, DEVICES

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


@pytest.mark.parametrize("name", list(DEVICES), ids=list(DEVICES))
def test_mac_address_not_garbled(name):
    """MAC is colon-formatted hex, not _decode_hex_value mojibake."""
    mac = collect(name)["system_info"]["mac_address"]
    assert MAC_RE.match(mac), f"{name} MAC looks garbled: {mac!r}"


def test_sfp_temperature_sentinel_and_scale():
    """CRS309: only the optical module reports a (sane, unscaled) temperature;
    copper DAC modules with the -128 sentinel report none — not 1.67e7."""
    sfp = collect("swos_crs309")["sfp_modules"]
    with_temp = [m for m in sfp if "temperature_c" in m]
    assert len(with_temp) == 1                       # only the real optical SFP+
    temp = with_temp[0]["temperature_c"]
    assert 0 < temp < 100                            # whole degrees C, not /256 or sentinel
    for m in sfp:
        assert m.get("temperature_c", 0) < 1000      # no 16,777,215 garbage


def test_swoslite_link_port_count():
    """CSS610 link.b is obfuscated and has no `prt` field; all 10 ports parse."""
    m = collect("swoslite_css610")
    assert m["ports"]["total"] == 10
    assert len(m["port_details"]) == 10


def test_swoslite_stats_decoded_64bit():
    """CSS610 !stats.b (obfuscated) decodes into real 64-bit byte counters."""
    stats = collect("swoslite_css610")["port_stats"]
    assert len(stats) == 10
    # The busiest port has carried multiple GB (proves high/low dword assembly).
    assert max(s["rx_bytes_total"] for s in stats) > 1_000_000_000


def test_swoslite_sfp_decoded():
    """CSS610 sfp.b (obfuscated) yields the module identity; the 16-bit -128
    temperature sentinel on its copper DAC is skipped, not emitted as garbage."""
    sfp = collect("swoslite_css610")["sfp_modules"]
    assert len(sfp) == 1
    mod = sfp[0]
    assert mod["vendor"] == "OEM"
    assert mod["part_number"] == "CAB-10GSFP-P1M"
    assert "temperature_c" not in mod        # copper DAC: 0xff80 sentinel skipped


def test_swoslite_device_info_populated():
    """CSS610 sys.b (obfuscated) populates device info instead of Unknown."""
    si = collect("swoslite_css610")["system_info"]
    assert si["version"] == "2.21"
    assert "CSS610" in si["board_model"]
    assert si["serial_id"] not in ("", "Unknown")
    assert si["temperature_c"] == 44


def test_port_stats_bang_stats_fallback():
    """CSS106 serves no /stats.b; stats come from /!stats.b instead."""
    stats = collect("swos_css106")["port_stats"]
    assert len(stats) == 6
    assert any(s["rx_bytes_total"] > 0 for s in stats)


def test_poe_power_matches_volts_times_amps():
    """SwOS Lite PoE: decoded power ≈ voltage × current (validates the mapping)."""
    poe = collect("swoslite_css610")["poe_ports"]
    delivering = [p for p in poe if p["power_w"] > 0]
    assert delivering, "expected at least one port delivering PoE"
    for p in delivering:
        expected = p["voltage_v"] * p["current_ma"] / 1000.0
        assert p["power_w"] == pytest.approx(expected, abs=1.5)


def test_poe_voltage_only_on_swoslite():
    """SwOS PoE (link.b) has no voltage; SwOS Lite PoE (poe.b) does."""
    swos = collect("swos_css106")["poe_ports"]
    lite = collect("swoslite_css610")["poe_ports"]
    assert all("voltage_v" not in p for p in swos)
    assert all("voltage_v" in p for p in lite)
