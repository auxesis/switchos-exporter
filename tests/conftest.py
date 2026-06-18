"""Shared test helpers: serve captured device fixtures to SwitchOSClient.

Each fixture directory under tests/fixtures/ holds the raw HTTP response bodies
for one device's `.b` endpoints (with a leading `!` written as `bang_`). The
helpers here patch SwitchOSClient._make_request so collect_metrics() runs the
full parse pipeline against those fixtures with no network access.
"""
import logging
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from switchos_client import SwitchOSClient  # noqa: E402

# Keep the parser's INFO chatter out of test output.
logging.getLogger("switchos_client").setLevel(logging.WARNING)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

# One entry per captured device. `os` records which firmware family it runs.
DEVICES = {
    "swos_css106": {
        "os": "swos",
        "device": {"name": "switch1", "ip": "10.0.0.1",
                   "device_model": "CSS106-1G-4P-1S", "manufacturer": "MikroTik",
                   "user": "admin", "password": "x"},
    },
    "swos_crs309": {
        "os": "swos",
        "device": {"name": "core0", "ip": "10.0.0.2",
                   "device_model": "CRS309-1G-8S+IN", "manufacturer": "MikroTik",
                   "user": "admin", "password": "x"},
    },
    "swoslite_css610": {
        "os": "swos-lite",
        "device": {"name": "poe0", "ip": "10.0.0.3",
                   "device_model": "CSS610-8P-2S+IN", "manufacturer": "MikroTik",
                   "user": "admin", "password": "x"},
    },
}


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200

    def raise_for_status(self):
        pass


def make_client(fixture_name):
    """A SwitchOSClient whose HTTP layer is backed by a fixture directory."""
    client = SwitchOSClient()
    directory = FIXTURES / fixture_name

    def fake_request(method, url, **kwargs):
        endpoint = url.rsplit("/", 1)[-1]
        path = directory / endpoint.replace("!", "bang_")
        return _FakeResponse(path.read_text()) if path.exists() else None

    client._make_request = fake_request
    return client


def collect(fixture_name):
    """Run collect_metrics() for a device against its fixtures."""
    info = DEVICES[fixture_name]
    return make_client(fixture_name).collect_metrics(info["device"]["ip"], info["device"])


@pytest.fixture(params=list(DEVICES), ids=list(DEVICES))
def device_case(request):
    """Parametrized over every captured device: (name, info, collected metrics)."""
    info = DEVICES[request.param]
    return request.param, info, collect(request.param)
