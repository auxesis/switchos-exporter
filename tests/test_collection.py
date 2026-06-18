"""Per-device collection tests: every metric family, for each captured device.

Values come from the committed fixtures, so they are deterministic. Device
identifiers (MAC/serial/IP) are redacted to fixed placeholders (see redact.py).
"""
import re

import pytest

from conftest import collect

MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")

# Expected, derived from the committed fixtures.
EXPECTED = {
    "swos_css106": {
        "ports": 6, "linked": 3,
        "names": ["router", "Port2", "Port3", "ceiling", "kitchen", "SFP"],
        "mac_entries": 57, "sfp": 0, "poe": 4, "poe_voltage": False,
        "version": "2.18", "board": "CSS106-1G-4P-1S", "temp": 41,
    },
    "swos_crs309": {
        "ports": 9, "linked": 4,
        "names": ["router", "switch0", "lindsaydesk", "SFP4", "SFP5", "SFP6",
                  "SFP7", "poe0", "MGMT"],
        "mac_entries": 61, "sfp": 4, "poe": 0, "poe_voltage": False,
        "version": "2.18", "board": "CRS309-1G-8S+", "temp": 33,
    },
    "swoslite_css610": {
        "ports": 10, "linked": 6,
        "names": ["Port1", "Port2", "Port3", "Port4", "Port5", "Port6", "Port7",
                  "Port8", "uplink", "SFP+2"],
        "mac_entries": 58, "sfp": 1, "poe": 8, "poe_voltage": True,
        "version": "2.21", "board": "CSS610-8P-2S+", "temp": 44,
    },
}


def test_device_reachable(device_case):
    name, info, m = device_case
    assert m["up"] == 1


def test_ports(device_case):
    name, info, m = device_case
    exp = EXPECTED[name]
    assert m["ports"]["total"] == exp["ports"]
    assert m["ports"]["linked"] == exp["linked"]
    assert [p["name"] for p in m["port_details"]] == exp["names"]


def test_port_stats(device_case):
    name, info, m = device_case
    exp = EXPECTED[name]
    stats = m["port_stats"]
    assert len(stats) == exp["ports"]
    for s in stats:
        # Every port reports 64-bit byte and packet counters (0 when idle).
        assert "rx_bytes_total" in s and "tx_bytes_total" in s
        assert isinstance(s["rx_bytes_total"], int) and s["rx_bytes_total"] >= 0
        assert s["rx_total_packets"] >= 0 and s["tx_total_packets"] >= 0
    # At least one port has carried real traffic.
    assert any(s["rx_bytes_total"] > 1_000_000 for s in stats)


def test_system_info(device_case):
    name, info, m = device_case
    exp = EXPECTED[name]
    si = m["system_info"]
    assert si["version"] == exp["version"]
    assert si["board_model"] == exp["board"]
    assert si["serial_id"]            # populated (redacted placeholder in fixtures)
    assert si["serial_id"] != "Unknown"
    assert MAC_RE.match(si["mac_address"])
    assert si["temperature_c"] == exp["temp"]
    assert si["uptime_seconds"] > 0
    assert isinstance(si["build_timestamp"], int) and si["build_timestamp"] > 0


def test_mac_table(device_case):
    name, info, m = device_case
    assert m["mac_stats"]["total_entries"] == EXPECTED[name]["mac_entries"]


def test_sfp_modules(device_case):
    name, info, m = device_case
    assert len(m.get("sfp_modules", [])) == EXPECTED[name]["sfp"]


def test_poe(device_case):
    name, info, m = device_case
    exp = EXPECTED[name]
    poe = m.get("poe_ports", [])
    assert len(poe) == exp["poe"]
    for p in poe:
        assert p["current_ma"] >= 0 and p["power_w"] >= 0
        assert ("voltage_v" in p) == exp["poe_voltage"]
