"""Tests for DeviceConfigClient: YAML loading, defaults, and settings."""
import pytest

from device_config import DeviceConfigClient

SAMPLE = """\
port: 9080
collection_interval: 30
defaults:
  user: admin
  password: secret
  manufacturer: MikroTik
devices:
  - name: a
    ip: 192.168.1.1/24
  - name: b
    ip: 192.168.1.2
    user: monitor
    device_model: CRS309
  - name: noip
"""


def write(tmp_path, text):
    p = tmp_path / "devices.yaml"
    p.write_text(text)
    return DeviceConfigClient(str(p))


def test_defaults_applied_and_overridden(tmp_path):
    devices = write(tmp_path, SAMPLE).fetch_devices()
    by_name = {d["name"]: d for d in devices}
    # default credentials applied
    assert by_name["a"]["user"] == "admin"
    assert by_name["a"]["password"] == "secret"
    assert by_name["a"]["manufacturer"] == "MikroTik"
    # per-device override wins
    assert by_name["b"]["user"] == "monitor"
    assert by_name["b"]["device_model"] == "CRS309"
    # absent optional label falls back to Unknown
    assert by_name["a"]["device_model"] == "Unknown"


def test_cidr_is_stripped(tmp_path):
    devices = write(tmp_path, SAMPLE).fetch_devices()
    assert next(d for d in devices if d["name"] == "a")["ip"] == "192.168.1.1"


def test_device_without_ip_is_skipped(tmp_path):
    devices = write(tmp_path, SAMPLE).fetch_devices()
    assert "noip" not in {d["name"] for d in devices}
    assert len(devices) == 2


def test_get_port_and_interval(tmp_path):
    client = write(tmp_path, SAMPLE)
    assert client.get_port() == 9080
    assert client.get_collection_interval() == 30


def test_settings_default_when_absent(tmp_path):
    client = write(tmp_path, "defaults: {user: u, password: p}\ndevices: [{name: a, ip: 1.1.1.1}]\n")
    assert client.get_port() == 9000
    assert client.get_collection_interval() == 60


def test_missing_file_raises():
    with pytest.raises(ValueError, match="not found"):
        DeviceConfigClient("/nonexistent/devices.yaml")


def test_non_integer_port_raises(tmp_path):
    client = write(tmp_path, "port: nine\ndevices: [{name: a, ip: 1.1.1.1}]\n")
    with pytest.raises(ValueError, match="must be an integer"):
        client.get_port()


def test_empty_devices_raises(tmp_path):
    client = write(tmp_path, "devices: []\n")
    with pytest.raises(ValueError, match="non-empty"):
        client.fetch_devices()
