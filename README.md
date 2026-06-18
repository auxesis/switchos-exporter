# MikroTik SwitchOS Prometheus Exporter

[![tests](https://github.com/auxesis/switchos-exporter/actions/workflows/tests.yml/badge.svg)](https://github.com/auxesis/switchos-exporter/actions/workflows/tests.yml)

A comprehensive Prometheus exporter for MikroTik switches running SwitchOS. This exporter reads its device list from a YAML config file and collects detailed metrics including port status, SFP module information, VLAN configuration, MAC address tables, and system information.

![Grafana Dashboard](dashboard.png)

## Features

- **Simple Device Inventory**: Lists MikroTik switches in a YAML config file — no external dependencies
- **SwOS and SwOS Lite**: Works with both MikroTik switch operating systems
- **Comprehensive Metrics Collection**: 
  - Device status and system information
  - Port status, link state, and statistics
  - SFP module temperature and optical power levels
  - PoE-out current, voltage and power per port
  - VLAN configuration and membership
  - MAC address table entries
- **HTTP Digest Authentication**: Secure authentication with SwitchOS devices
- **Prometheus Compatible**: Standard Prometheus metrics format with proper label sanitization

## Architecture

The exporter consists of three main components:

1. **Device Config Client** (`device_config.py`): Loads the switch inventory from a YAML config file
2. **SwitchOS Client** (`switchos_client.py`): Communicates with switches and parses metrics
3. **Prometheus Exporter** (`switchos_exporter.py`): Exposes metrics in Prometheus format

## Metrics Collected

### Device Metrics
- `switchos_device_up`: Device reachability status (1=up, 0=down)
- `switchos_collection_duration_seconds`: Time spent collecting metrics
- `switchos_system_uptime_seconds`: System uptime
- `switchos_system_temperature_celsius`: System temperature
- `switchos_psu_voltage_volts`: Power supply input voltage (where reported)
- `switchos_power_consumption_watts`: Total switch power draw (SwOS Lite)

### Port Metrics
- `switchos_port_status`: Port enabled status (1=enabled, 0=disabled)
- `switchos_port_link_status`: Port link status (1=linked, 0=down)
- `switchos_port_speed_mbps`: Port speed in Mbps
- `switchos_port_duplex`: Port duplex (1=full, 0=half/down)
- `switchos_port_rx_bytes_total`: Total received bytes
- `switchos_port_tx_bytes_total`: Total transmitted bytes
- `switchos_port_rx_packets_total`: Total received packets
- `switchos_port_tx_packets_total`: Total transmitted packets
- `switchos_port_rx_errors_total`: Total receive errors (aggregate)
- `switchos_port_tx_errors_total`: Total transmit errors (aggregate)
- `switchos_port_error_frames_total`: Error frames by `direction` (rx/tx) and
  `type` (fcs, align, runt, fragment, jabber, oversize, too_long, collision,
  late_collision, excessive_collision)
- `switchos_port_pause_frames_total`: Pause (flow-control) frames by `direction`
- `switchos_port_frames_by_size_total`: Received frames bucketed by `size_bucket`
  (64, 65-127, 128-255, 256-511, 512-1023, 1024+)

### VLAN Metrics
- `switchos_vlan_count`: Number of configured VLANs
- `switchos_vlan_port_members`: Number of member ports in VLAN

### MAC Table Metrics
- `switchos_mac_table_entries`: Total MAC address table entries
- `switchos_mac_table_entries_by_vlan`: MAC entries per VLAN

### SFP Module Metrics
- `switchos_sfp_temperature_celsius`: SFP module temperature (optical modules)
- `switchos_sfp_voltage_volts`: SFP module supply voltage (optical modules)
- `switchos_sfp_tx_bias_milliamps`: SFP laser TX bias current (optical modules)
- `switchos_sfp_tx_power_mw`: SFP TX power in milliwatts
- `switchos_sfp_rx_power_mw`: SFP RX power in milliwatts

### PoE Metrics (PoE-out switches: CSS106-xP, CSS610-xP, …)
- `switchos_poe_status`: PoE-out port status code (see table below)
- `switchos_poe_current_milliamps`: PoE-out current draw in mA
- `switchos_poe_power_watts`: PoE-out power delivered in watts
- `switchos_poe_voltage_volts`: PoE-out voltage (SwOS Lite devices only)

`switchos_poe_status` values:

| Code | Meaning | Code | Meaning |
|------|---------|------|---------|
| 0 | off | 6 | voltage too low |
| 1 | disabled | 7 | current too low |
| 2 | waiting for load | 8 | power cycle |
| 3 | powered on | 9 | voltage too high |
| 4 | overload | 10 | controller error |
| 5 | short circuit | | |

### Device Information
- `switchos_device_info`: Device metadata (version, model, serial, etc.)

## Supported devices

The exporter works with MikroTik switches running both **SwOS** and **SwOS Lite**
(SwitchOS Lite). SwOS Lite — used by the CSS610 / CSS6xx family — serves the same
`.b` web endpoints but with obfuscated field names (`i01`, `i02`, …). The exporter
detects the format and translates it, so SwOS Lite switches get the same coverage
as SwOS: ports, link, speed, per-port counters, SFP modules, PoE and system info.

### Tested hardware

| Model | OS | Firmware | Ports |
|-------|-----|----------|-------|
| CRS309-1G-8S+IN | SwOS | 2.18 | 1× GbE + 8× SFP+ |
| CSS106-1G-4P-1S | SwOS | 2.18 | 5× GbE (4× PoE-out) + 1× SFP |
| CSS610-8P-2S+IN | SwOS Lite | 2.21 | 8× GbE PoE-out + 2× SFP+ |

### Tested firmware

The SwOS Lite field mappings (system info, link/port status, port statistics,
SFP and PoE) were extracted from the firmware web UI and cross-checked across
every SwOS Lite **2.21** image. The system, link/port, statistics and SFP field
IDs are identical across all five; the `poe.b` PoE mapping matches the two
PoE-out firmwares.

| Firmware | PoE-out support |
|----------|-----------------|
| `swos-css610out-2.21` | yes — `poe.b` (runs the tested CSS610-8P-2S+IN) |
| `swos-css610pi-2.21` | yes — `poe.b` |
| `swos-css606-2.21` | uses a different `poeoutports.b` endpoint (not yet decoded) |
| `swos-css610-2.21` | PoE-in only (nothing to meter) |
| `swos-css610g-2.21` | none |

PoE-out metrics are emitted only for ports the switch reports as PoE-capable.

## Configuration

All configuration lives in a single `devices.yaml` file. Copy
`devices.yaml.example` to `devices.yaml` and edit it. The file has two sections:

- `defaults` — applied to every device unless overridden per-device.
- `devices` — the switches to scrape. Only `name` and `ip` are required.

```yaml
defaults:
  user: admin
  password: your_switch_password

devices:
  # Minimal entry — uses the credentials from `defaults`
  - name: switch-001
    ip: 192.168.1.1

  # Entry with optional labels
  - name: switch-002
    ip: 192.168.1.2
    device_model: CRS328-24P-20S-RM
    manufacturer: MikroTik

  # Entry with per-device credential override
  - name: switch-003
    ip: 192.168.1.3
    user: monitor
    password: a-different-password
```

Top-level `port:` and `collection_interval:` set the metrics port (default
`9000`) and scrape interval in seconds (default `60`); the `--port` and
`--collection-interval` CLI flags override them.

| Field | Required | Default | Notes |
|-------|----------|---------|-------|
| `port` | no | `9000` | Top-level. Metrics port; overridden by `--port` |
| `collection_interval` | no | `60` | Top-level. Scrape interval (s); overridden by `--collection-interval` |
| `name` | yes | — | Device name (`device_name` label) |
| `ip` | yes | — | IPv4 address; CIDR suffix (e.g. `/24`) is stripped |
| `user`, `password` | yes (here or in `defaults`) | from `defaults` | SwitchOS digest-auth credentials |
| `device_model`, `manufacturer` | no | from `defaults`, else `Unknown` | Prometheus labels (on `switchos_device_up`) |

### Command line

```
python3 switchos_exporter.py [--port PORT] [--collection-interval SECONDS] [config]
```

- `config` — path to the YAML config file (default `devices.yaml`, or
  `$SWITCHOS_CONFIG`).
- `--port` — metrics port; overrides `port:` in the config file.
- `--collection-interval` — scrape interval in seconds; overrides
  `collection_interval:` in the config file.

```bash
# custom config file on a custom port
python3 switchos_exporter.py --port 9080 my_custom_devices.yaml
```

## Installation and Deployment

### Prerequisites

- Python 3.10+ or Docker
- Network access to the MikroTik switches
- MikroTik switches with SwitchOS and HTTP API enabled

### Method 1: mise (recommended for development)

This repo ships a [mise](https://mise.jdx.dev) config that pins Python and
manages a project-local virtualenv.

```bash
mise install            # install Python 3.11 + create .venv
mise run setup          # install dependencies into .venv
cp devices.yaml.example devices.yaml   # then edit it

mise run exporter       # run on the default port
mise run exporter -- --port 9080 my_custom_devices.yaml   # pass CLI args after --
mise run config         # validate the config file
mise run test           # run the test suite
```

### Method 2: Direct Python

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure**:
   ```bash
   cp devices.yaml.example devices.yaml
   # Edit devices.yaml with your credentials and switches
   ```

3. **Run the Exporter**:
   ```bash
   python3 switchos_exporter.py
   # or: python3 switchos_exporter.py --port 9080 my_custom_devices.yaml
   ```

4. **Verify Operation**:
   ```bash
   curl http://localhost:9000/metrics
   ```

### Method 3: Docker Deployment

1. **Configure**:
   ```bash
   cp devices.yaml.example devices.yaml
   # Edit devices.yaml with your credentials and switches
   ```

2. **Build and Deploy**:
   ```bash
   docker compose build
   docker compose up -d
   ```

3. **Monitor Logs**:
   ```bash
   docker compose logs -f
   ```

4. **Verify Operation**:
   ```bash
   curl http://localhost:9000/metrics
   ```

## Docker Configuration

The Docker deployment includes:

- **Resource Limits**: 2 CPU cores max, 1GB memory max
- **Health Checks**: Automatic health monitoring on metrics endpoint
- **Logging**: Structured JSON logs with rotation
- **Security**: Non-root user execution
- **Persistence**: Volume mounts for logs and configuration

## Prometheus Configuration

Add the following to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'switchos-exporter'
    static_configs:
      - targets: ['localhost:9000']
    scrape_interval: 60s
    scrape_timeout: 30s
```

## Monitoring and Alerting

### PromQL Queries

For a comprehensive collection of ready-to-use PromQL queries, see **[PROMQL_QUERIES.md](PROMQL_QUERIES.md)**.

This includes queries for:
- Port bandwidth and traffic analysis
- Port status and health monitoring
- Device health and uptime
- SFP metrics and diagnostics
- Top N analysis
- Alerting queries
- Grafana dashboard examples

### Quick Examples

**Port RX Bandwidth (Mbps)**:
```promql
rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000
```

**Port TX Bandwidth (Mbps)**:
```promql
rate(switchos_port_tx_bytes_total[5m]) * 8 / 1000000
```

**Device Status**:
```promql
switchos_device_up
```

**Top 10 Ports by Bandwidth**:
```promql
topk(10, rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000)
```

**SFP Temperature**:
```promql
switchos_sfp_temperature_celsius
```

**Per-device Filtering**:
```promql
rate(switchos_port_rx_bytes_total{device_name="switch-001"}[5m]) * 8 / 1000000
```

### Sample Alerts

```yaml
groups:
  - name: switchos
    rules:
      - alert: SwitchDown
        expr: switchos_device_up == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Switch {{ $labels.device_name }} is down"

      - alert: SFPHighTemperature
        expr: switchos_sfp_temperature_celsius > 70
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "SFP module temperature high on {{ $labels.device_name }}"
```

## Troubleshooting

### Common Issues

1. **Device shows as down**: Check network connectivity and credentials
2. **No metrics appearing**: Verify the `ip` values in `devices.yaml` are reachable
3. **Authentication errors**: Confirm SwitchOS credentials and HTTP API access
4. **Label errors**: Ensure device names don't contain invalid characters
5. **`Config file not found`**: Ensure `devices.yaml` exists in the working directory, or set `SWITCHOS_CONFIG` to its path

### Debugging

1. **Check container logs**:
   ```bash
   docker compose logs switchos-exporter
   ```

2. **Test connectivity**:
   ```bash
   curl -u admin:password http://switch-ip/link.b
   ```

3. **Verify the device inventory loads**:
   ```bash
   python3 device_config.py
   ```

### Performance Tuning

- **Collection Interval**: Modify `collection_interval=60` in `switchos_exporter.py`
- **Resource Limits**: Adjust Docker resource limits in `docker-compose.yml`
- **Concurrent Collection**: Consider threading for multiple devices

## Development

### Project Structure
```
switchos-exporter/
├── switchos_exporter.py    # Main exporter application (CLI entry point)
├── device_config.py        # YAML config loader (devices + settings)
├── switchos_client.py      # SwitchOS communication
├── requirements.txt        # Python dependencies
├── requirements-dev.txt    # Dev/test dependencies
├── mise.toml              # Python toolchain + dev tasks (mise)
├── Dockerfile             # Container definition
├── docker-compose.yml     # Docker deployment
├── devices.yaml.example  # Configuration template (port + defaults + devices)
├── tests/                 # Test suite + captured device fixtures
└── README.md            # This file
```

### Testing

The test suite runs the full parse pipeline against captured device responses
(fixtures) — no switch required — and covers every exported metric plus
SwOS/SwOS Lite parity.

```bash
pip install -r requirements-dev.txt
pytest -q                 # or: mise run test
```

See [tests/README.md](tests/README.md) for how the fixtures work and how to
**add test data captured from a new device** (including redacting identifiers
before committing).

### Contributing

1. Follow Python PEP 8 style guidelines
2. Add appropriate logging for debugging
3. Add fixtures and tests when adding support for a new device (see tests/README.md)
4. Update documentation for new features

## License

This project is licensed under the [GNU Affero General Public License v3.0 (AGPL-3.0)](LICENSE).
