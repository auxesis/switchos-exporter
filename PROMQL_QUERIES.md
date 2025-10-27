# SwitchOS Exporter - PromQL Query Examples

This document contains ready-to-use PromQL queries for monitoring MikroTik SwitchOS devices.

## Table of Contents
- [Port Bandwidth & Traffic](#port-bandwidth--traffic)
- [Port Status & Health](#port-status--health)
- [Device Health](#device-health)
- [System Metrics](#system-metrics)
- [SFP Metrics](#sfp-metrics)
- [VLAN & MAC Table](#vlan--mac-table)
- [Top N Queries](#top-n-queries)
- [Alerting Queries](#alerting-queries)

---

## Port Bandwidth & Traffic

### RX Bandwidth (bytes per second)
```promql
rate(switchos_port_rx_bytes_total[5m])
```

### TX Bandwidth (bytes per second)
```promql
rate(switchos_port_tx_bytes_total[5m])
```

### RX Bandwidth in Mbps
```promql
rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000
```

### TX Bandwidth in Mbps
```promql
rate(switchos_port_tx_bytes_total[5m]) * 8 / 1000000
```

### Total Bandwidth (RX + TX) in Mbps
```promql
(rate(switchos_port_rx_bytes_total[5m]) + rate(switchos_port_tx_bytes_total[5m])) * 8 / 1000000
```

### Bandwidth for Specific Device
```promql
rate(switchos_port_rx_bytes_total{device_name="000001.SW1"}[5m]) * 8 / 1000000
```

### Bandwidth for Specific Port
```promql
rate(switchos_port_rx_bytes_total{device_name="000001.SW1", port_name="Port1"}[5m]) * 8 / 1000000
```

### Bandwidth by Site
```promql
rate(switchos_port_rx_bytes_total{site="000007"}[5m]) * 8 / 1000000
```

### Bandwidth by Location
```promql
rate(switchos_port_rx_bytes_total{location="50 W 139th St, New York, NY 10037"}[5m]) * 8 / 1000000
```

### RX Packet Rate (packets per second)
```promql
rate(switchos_port_rx_packets_total[5m])
```

### TX Packet Rate (packets per second)
```promql
rate(switchos_port_tx_packets_total[5m])
```

### RX Error Rate (errors per second)
```promql
rate(switchos_port_rx_errors_total[5m])
```

### TX Error Rate (errors per second)
```promql
rate(switchos_port_tx_errors_total[5m])
```

---

## Port Status & Health

### All Enabled Ports
```promql
switchos_port_status == 1
```

### All Disabled Ports
```promql
switchos_port_status == 0
```

### Ports with Link Up
```promql
switchos_port_link_status == 1
```

### Ports with Link Down (but enabled)
```promql
switchos_port_link_status == 0 and switchos_port_status == 1
```

### Port Speed (Mbps)
```promql
switchos_port_speed_mbps
```

### Gigabit Ports (1000 Mbps)
```promql
switchos_port_speed_mbps == 1000
```

### Port Utilization Percentage (RX)
Requires knowing the port speed:
```promql
(rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000) / switchos_port_speed_mbps * 100
```

### Port Utilization Percentage (TX)
```promql
(rate(switchos_port_tx_bytes_total[5m]) * 8 / 1000000) / switchos_port_speed_mbps * 100
```

---

## Device Health

### All Devices Up
```promql
switchos_device_up == 1
```

### All Devices Down
```promql
switchos_device_up == 0
```

### Device Up Count
```promql
count(switchos_device_up == 1)
```

### Device Down Count
```promql
count(switchos_device_up == 0)
```

### Devices by Site (Up/Down count)
```promql
count by (site) (switchos_device_up)
```

### Collection Duration (seconds)
```promql
switchos_collection_duration_seconds
```

### Slow Collections (>10 seconds)
```promql
switchos_collection_duration_seconds > 10
```

---

## System Metrics

### System Uptime (seconds)
```promql
switchos_system_uptime_seconds
```

### System Uptime (days)
```promql
switchos_system_uptime_seconds / 86400
```

### System Temperature (Celsius)
```promql
switchos_system_temperature_celsius
```

### High Temperature Devices (>60°C)
```promql
switchos_system_temperature_celsius > 60
```

### Recently Rebooted Devices (< 1 hour uptime)
```promql
switchos_system_uptime_seconds < 3600
```

### Recently Rebooted Devices (< 24 hours uptime)
```promql
switchos_system_uptime_seconds < 86400
```

---

## SFP Metrics

### SFP Temperature (Celsius)
```promql
switchos_sfp_temperature_celsius
```

### Hot SFPs (>70°C)
```promql
switchos_sfp_temperature_celsius > 70
```

### SFP TX Power (mW)
```promql
switchos_sfp_tx_power_mw
```

### SFP RX Power (mW)
```promql
switchos_sfp_rx_power_mw
```

### SFP TX Power (dBm)
Convert milliwatts to dBm:
```promql
10 * log10(switchos_sfp_tx_power_mw)
```

### SFP RX Power (dBm)
```promql
10 * log10(switchos_sfp_rx_power_mw)
```

### Low RX Power SFPs (< 0.1 mW / -10 dBm)
```promql
switchos_sfp_rx_power_mw < 0.1
```

### SFPs by Vendor
```promql
count by (vendor) (switchos_sfp_temperature_celsius)
```

---

## VLAN & MAC Table

### Total VLANs per Device
```promql
switchos_vlan_count
```

### VLAN Port Members
```promql
switchos_vlan_port_members
```

### Total MAC Table Entries per Device
```promql
switchos_mac_table_entries
```

### MAC Entries by VLAN
```promql
switchos_mac_table_entries_by_vlan
```

### Devices with Large MAC Tables (>500 entries)
```promql
switchos_mac_table_entries > 500
```

---

## Top N Queries

### Top 10 Ports by RX Bandwidth
```promql
topk(10, rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000)
```

### Top 10 Ports by TX Bandwidth
```promql
topk(10, rate(switchos_port_tx_bytes_total[5m]) * 8 / 1000000)
```

### Top 10 Ports by Total Bandwidth
```promql
topk(10, (rate(switchos_port_rx_bytes_total[5m]) + rate(switchos_port_tx_bytes_total[5m])) * 8 / 1000000)
```

### Top 10 Ports by Error Rate
```promql
topk(10, rate(switchos_port_rx_errors_total[5m]) + rate(switchos_port_tx_errors_total[5m]))
```

### Top 10 Hottest SFPs
```promql
topk(10, switchos_sfp_temperature_celsius)
```

### Top 10 Devices by Port Count
```promql
topk(10, count by (device_name) (switchos_port_status))
```

### Top 5 Sites by Device Count
```promql
topk(5, count by (site) (switchos_device_up))
```

### Bottom 10 Ports by RX Bandwidth (excluding zero)
```promql
bottomk(10, rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000 > 0)
```

---

## Alerting Queries

### Device Down Alert
```promql
switchos_device_up == 0
```

### High Port Utilization (>80%)
```promql
(rate(switchos_port_rx_bytes_total[5m]) * 8 / 1000000) / switchos_port_speed_mbps * 100 > 80
```

### Port Flapping (link status changed recently)
Use `changes()` to detect frequent status changes:
```promql
changes(switchos_port_link_status[5m]) > 2
```

### High Error Rate (>100 errors/sec)
```promql
rate(switchos_port_rx_errors_total[5m]) + rate(switchos_port_tx_errors_total[5m]) > 100
```

### High Temperature Alert (>70°C)
```promql
switchos_system_temperature_celsius > 70
```

### SFP High Temperature Alert (>75°C)
```promql
switchos_sfp_temperature_celsius > 75
```

### Device Recently Rebooted
```promql
switchos_system_uptime_seconds < 300
```

### Slow Metric Collection (>30 seconds)
```promql
switchos_collection_duration_seconds > 30
```

### Low SFP RX Power (potential fiber issue)
```promql
switchos_sfp_rx_power_mw < 0.01
```

### No SFP RX Power (fiber disconnected)
```promql
switchos_sfp_rx_power_mw == 0
```

---

## Aggregation Examples

### Total Bandwidth Across All Devices (Mbps)
```promql
sum(rate(switchos_port_rx_bytes_total[5m]) + rate(switchos_port_tx_bytes_total[5m])) * 8 / 1000000
```

### Total Bandwidth by Site
```promql
sum by (site) (rate(switchos_port_rx_bytes_total[5m]) + rate(switchos_port_tx_bytes_total[5m])) * 8 / 1000000
```

### Total Bandwidth by Device
```promql
sum by (device_name) (rate(switchos_port_rx_bytes_total[5m]) + rate(switchos_port_tx_bytes_total[5m])) * 8 / 1000000
```

### Average Port Speed by Device
```promql
avg by (device_name) (switchos_port_speed_mbps)
```

### Total Active Ports (linked)
```promql
count(switchos_port_link_status == 1)
```

### Active Ports by Site
```promql
count by (site) (switchos_port_link_status == 1)
```

### Total Errors Across All Ports
```promql
sum(rate(switchos_port_rx_errors_total[5m]) + rate(switchos_port_tx_errors_total[5m]))
```

---

## Time Range Variations

You can adjust the time range in square brackets for different analysis:

- `[1m]` - 1 minute (more responsive, noisier)
- `[5m]` - 5 minutes (balanced, recommended)
- `[15m]` - 15 minutes (smoother, less responsive)
- `[1h]` - 1 hour (very smooth, good for trends)

Example:
```promql
# Quick spikes
rate(switchos_port_rx_bytes_total[1m]) * 8 / 1000000

# Smooth average
rate(switchos_port_rx_bytes_total[1h]) * 8 / 1000000
```

---

## Using Variables in Grafana

In Grafana dashboards, use variables for dynamic queries:

### Define Variables
```
$device    = label_values(switchos_port_rx_bytes_total, device_name)
$site      = label_values(switchos_port_rx_bytes_total, site)
$location  = label_values(switchos_port_rx_bytes_total, location)
$port      = label_values(switchos_port_rx_bytes_total{device_name="$device"}, port_name)
```

### Use in Queries
```promql
rate(switchos_port_rx_bytes_total{device_name="$device", site="$site", port_name="$port"}[5m]) * 8 / 1000000
```

### Multi-Value Variables
Enable "Multi-value" and "Include All" for variables:
```promql
rate(switchos_port_rx_bytes_total{device_name=~"$device"}[5m]) * 8 / 1000000
```

---

## Tips

1. **Always use `rate()` or `irate()` with counters** (`_total` metrics)
2. **Use `[5m]` as default time range** for rate calculations
3. **Multiply by 8 / 1000000** to convert bytes/sec to Mbps
4. **Use `topk()` and `bottomk()`** for "Top N" queries
5. **Use `by (label)`** with aggregations to group results
6. **Use `=~` for regex matching** multiple values
7. **Use `!=` or `!~`** for negative matching

---

## Need Help?

- Prometheus PromQL documentation: https://prometheus.io/docs/prometheus/latest/querying/basics/
- Grafana variables: https://grafana.com/docs/grafana/latest/dashboards/variables/
