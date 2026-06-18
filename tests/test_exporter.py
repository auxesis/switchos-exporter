"""Exporter-level tests: metric label structure and the HTTP endpoints.

The exporter registers metrics on the global Prometheus registry, so it is
created once per session to avoid duplicate-registration errors.
"""
import threading
from http.server import ThreadingHTTPServer

import pytest
import requests

from switchos_exporter import SwitchOSExporter

# Labels removed during this session; none should remain on any metric.
REMOVED_LABELS = {"site", "site_id", "site_description", "location", "device_role"}


@pytest.fixture(scope="session")
def exporter():
    # device_client is unused for setup_metrics() / the HTTP handler.
    return SwitchOSExporter(device_client=None, port=0)


def _metric_objects(exporter):
    return [v for v in vars(exporter).values() if hasattr(v, "_labelnames")]


def test_removed_labels_absent(exporter):
    for metric in _metric_objects(exporter):
        leaked = REMOVED_LABELS & set(metric._labelnames)
        assert not leaked, f"{metric._name} still exposes {sorted(leaked)}"


def test_core_metric_labels(exporter):
    assert set(exporter.device_up._labelnames) == {
        "device_name", "device_model", "manufacturer"}
    assert set(exporter.poe_power._labelnames) == {
        "device_name", "port_name", "port_index"}


def test_http_serves_metrics_and_health(exporter):
    server = ThreadingHTTPServer(("127.0.0.1", 0), exporter._make_handler())
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{port}"
        m = requests.get(base + "/metrics", timeout=5)
        assert m.status_code == 200
        assert "switchos_device_up" in m.text
        # before any collection runs, health is in its start-up grace period
        h = requests.get(base + "/health", timeout=5)
        assert h.status_code == 200 and "OK" in h.text
        assert requests.get(base + "/healthz", timeout=5).status_code == 200
        assert requests.get(base + "/missing", timeout=5).status_code == 404
    finally:
        server.shutdown()
