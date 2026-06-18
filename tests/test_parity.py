"""SwOS vs SwOS Lite parity.

SwOS Lite (CSS610) serves the same data as SwOS but with obfuscated field
names. These tests assert the exporter produces the same metric families for
both firmware types, and pin the one known remaining gap so it is visible.
"""
import pytest

from conftest import collect, DEVICES


def families(m):
    """The set of metric families present in a collected-metrics dict."""
    fams = set()
    if m.get("up"):
        fams.add("device_up")
    if m.get("port_details"):
        fams.add("ports")
    if any("rx_bytes_total" in s for s in m.get("port_stats", [])):
        fams.add("port_byte_counters")
    if any("rx_total_packets" in s for s in m.get("port_stats", [])):
        fams.add("port_packet_counters")
    si = m.get("system_info", {})
    if si.get("version") and si.get("version") != "Unknown":
        fams.add("sys_version")
    if si.get("board_model") and si.get("board_model") != "Unknown":
        fams.add("sys_board")
    if si.get("serial_id") and si.get("serial_id") != "Unknown":
        fams.add("sys_serial")
    if si.get("mac_address"):
        fams.add("sys_mac")
    if si.get("uptime_seconds"):
        fams.add("sys_uptime")
    if "temperature_c" in si:
        fams.add("sys_temperature")
    if m.get("mac_stats", {}).get("total_entries"):
        fams.add("mac_table")
    if m.get("poe_ports"):
        fams.add("poe")
    if m.get("sfp_modules"):
        fams.add("sfp")
    return fams


# Families every supported switch must report regardless of firmware family.
CORE_FAMILIES = {
    "device_up", "ports", "port_byte_counters", "port_packet_counters",
    "sys_version", "sys_board", "sys_serial", "sys_mac", "sys_uptime",
    "sys_temperature", "mac_table",
}


@pytest.mark.parametrize("name", list(DEVICES), ids=list(DEVICES))
def test_core_families_present(name):
    """The core metric families are present for SwOS and SwOS Lite alike."""
    fams = families(collect(name))
    missing = CORE_FAMILIES - fams
    assert not missing, f"{name} is missing core families: {sorted(missing)}"


def test_swos_and_swoslite_agree_on_core():
    """A SwOS device and the SwOS Lite device expose the same core families."""
    swos = families(collect("swos_crs309"))
    lite = families(collect("swoslite_css610"))
    assert (CORE_FAMILIES & swos) == (CORE_FAMILIES & lite)


def test_poe_parity_for_poe_hardware():
    """Both a SwOS PoE switch and the SwOS Lite PoE switch report PoE."""
    assert "poe" in families(collect("swos_css106"))      # SwOS, PoE in link.b
    assert "poe" in families(collect("swoslite_css610"))  # SwOS Lite, poe.b


@pytest.mark.xfail(strict=True,
                   reason="SwOS Lite sfp.b (obfuscated) is not parsed yet; "
                          "CSS610 SFP+ modules are not reported. Remove this "
                          "marker when SwOS Lite SFP parsing lands.")
def test_swoslite_reports_sfp_modules():
    """The CSS610 has SFP+ ports and should report its modules like SwOS does."""
    assert len(collect("swoslite_css610").get("sfp_modules", [])) > 0
