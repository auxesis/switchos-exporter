#!/usr/bin/env python3
"""
MikroTik SwitchOS Prometheus Exporter
Collects metrics from MikroTik switches listed in a YAML config file
"""

import time
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Any
from prometheus_client import start_http_server, Gauge, Counter, Info, Enum, REGISTRY
from device_config import DeviceConfigClient
from switchos_client import SwitchOSClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SwitchOSExporter:
    def __init__(self, port: int = 9000, health_port: int = 9001):
        self.port = port
        self.health_port = health_port
        self.device_client = DeviceConfigClient()
        self.switchos_client = SwitchOSClient()
        self.metrics = {}
        self.last_collection_time = 0
        self.last_collection_success = False
        self.collection_interval = 60
        self.setup_metrics()
        
    def sanitize_label(self, label_value: str) -> str:
        """Sanitize label values for Prometheus (preserve dots, spaces, and common punctuation)"""
        if not label_value:
            return 'Unknown'
        import re
        # Allow alphanumeric, dots, spaces, hyphens, and commas - only replace truly problematic characters
        return re.sub(r'[^a-zA-Z0-9\.\s\-,]', '_', str(label_value))
        
    def setup_metrics(self):
        """Initialize Prometheus metrics"""
        
        # Device status metrics
        self.device_up = Gauge(
            'switchos_device_up',
            'Device reachability status (1=up, 0=down)',
            ['device_name', 'device_model', 'manufacturer']
        )
        
        self.collection_duration = Gauge(
            'switchos_collection_duration_seconds',
            'Time spent collecting metrics from device',
            ['device_name']
        )
        
        # System metrics
        self.system_uptime = Gauge(
            'switchos_system_uptime_seconds',
            'System uptime in seconds',
            ['device_name', 'device_model', 'serial_id']
        )
        
        self.system_temperature = Gauge(
            'switchos_system_temperature_celsius',
            'System temperature in Celsius',
            ['device_name']
        )
        
        # Port metrics
        self.port_status = Gauge(
            'switchos_port_status',
            'Port status (1=enabled, 0=disabled)',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_link_status = Gauge(
            'switchos_port_link_status',
            'Port link status (1=linked, 0=down)',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_speed_mbps = Gauge(
            'switchos_port_speed_mbps',
            'Port speed in Mbps',
            ['device_name', 'port_name', 'port_index']
        )
        
        # Port statistics
        self.port_rx_bytes = Counter(
            'switchos_port_rx_bytes_total',
            'Total received bytes',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_tx_bytes = Counter(
            'switchos_port_tx_bytes_total',
            'Total transmitted bytes',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_rx_packets = Counter(
            'switchos_port_rx_packets_total',
            'Total received packets',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_tx_packets = Counter(
            'switchos_port_tx_packets_total',
            'Total transmitted packets',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_rx_errors = Counter(
            'switchos_port_rx_errors_total',
            'Total receive errors',
            ['device_name', 'port_name', 'port_index']
        )
        
        self.port_tx_errors = Counter(
            'switchos_port_tx_errors_total',
            'Total transmit errors',
            ['device_name', 'port_name', 'port_index']
        )
        
        # VLAN metrics
        self.vlan_count = Gauge(
            'switchos_vlan_count',
            'Number of configured VLANs',
            ['device_name']
        )
        
        self.vlan_ports = Gauge(
            'switchos_vlan_port_members',
            'Number of member ports in VLAN',
            ['device_name', 'vlan_id']
        )
        
        # MAC table metrics
        self.mac_table_entries = Gauge(
            'switchos_mac_table_entries',
            'Number of MAC address table entries',
            ['device_name']
        )
        
        self.mac_table_entries_by_vlan = Gauge(
            'switchos_mac_table_entries_by_vlan',
            'MAC address table entries per VLAN',
            ['device_name', 'vlan_id']
        )
        
        # SFP metrics
        self.sfp_temperature = Gauge(
            'switchos_sfp_temperature_celsius',
            'SFP module temperature in Celsius',
            ['device_name', 'sfp_index', 'vendor', 'part_number']
        )
        
        self.sfp_tx_power = Gauge(
            'switchos_sfp_tx_power_mw',
            'SFP module TX power in milliwatts',
            ['device_name', 'sfp_index', 'vendor', 'part_number']
        )
        
        self.sfp_rx_power = Gauge(
            'switchos_sfp_rx_power_mw',
            'SFP module RX power in milliwatts',
            ['device_name', 'sfp_index', 'vendor', 'part_number']
        )
        
        # PoE metrics (PoE-out capable switches: CSS106-xP, CSS610-xP)
        poe_labels = ['device_name', 'port_name', 'port_index']
        self.poe_status = Gauge(
            'switchos_poe_status',
            'PoE-out port status code (0=off; vendor-specific, >0=enabled/delivering)',
            poe_labels
        )
        self.poe_current = Gauge(
            'switchos_poe_current_milliamps',
            'PoE-out current draw in milliamps',
            poe_labels
        )
        self.poe_power = Gauge(
            'switchos_poe_power_watts',
            'PoE-out power delivered in watts',
            poe_labels
        )
        self.poe_voltage = Gauge(
            'switchos_poe_voltage_volts',
            'PoE-out voltage in volts (SwOS Lite only)',
            poe_labels
        )

        # Info metrics
        self.device_info = Info(
            'switchos_device_info',
            'Device information',
            ['device_name']
        )

        # Exporter health metrics
        self.last_collection_timestamp = Gauge(
            'switchos_exporter_last_collection_timestamp',
            'Unix timestamp of last successful collection cycle'
        )

        self.collection_cycle_duration = Gauge(
            'switchos_exporter_collection_cycle_duration_seconds',
            'Duration of last collection cycle in seconds'
        )

        self.devices_collected = Gauge(
            'switchos_exporter_devices_collected',
            'Number of devices collected in last cycle'
        )
        
    def collect_device_metrics(self, device: Dict[str, Any]):
        """Collect metrics from a single device"""
        device_name = self.sanitize_label(device['name'])
        device_ip = device['ip']

        logger.info(f"Collecting metrics from {device_name} ({device_ip})")

        start_time = time.time()

        try:
            # Collect all metrics from device
            metrics = self.switchos_client.collect_metrics(device_ip, device)

            # Common labels (sanitize all for Prometheus)
            labels = {
                'device_name': device_name,
                'device_model': self.sanitize_label(device.get('device_model', 'Unknown')),
                'manufacturer': self.sanitize_label(device.get('manufacturer', 'Unknown'))
            }

            # Device status
            self.device_up.labels(**labels).set(metrics['up'])

            # Collection duration
            duration = time.time() - start_time
            self.collection_duration.labels(
                device_name=device_name
            ).set(duration)

            if metrics['up']:
                self.update_device_metrics(metrics, labels)

        except Exception as e:
            logger.error(f"Error collecting metrics from {device_name}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            try:
                # Use minimal labels for error case
                minimal_labels = {
                    'device_name': self.sanitize_label(device.get('name', 'Unknown')),
                    'device_model': self.sanitize_label(device.get('device_model', 'Unknown')),
                    'manufacturer': self.sanitize_label(device.get('manufacturer', 'Unknown'))
                }
                self.device_up.labels(**minimal_labels).set(0)
            except Exception as label_error:
                logger.error(f"Error setting device down metric: {label_error}")
    
    def update_device_metrics(self, metrics: Dict[str, Any], labels: Dict[str, str]):
        """Update Prometheus metrics with collected data"""
        
        # System information
        if 'system_info' in metrics:
            sys_info = metrics['system_info']
            
            if 'uptime_seconds' in sys_info:
                try:
                    # system_uptime needs: device_name, device_model, serial_id
                    self.system_uptime.labels(
                        device_name=labels['device_name'],
                        device_model=labels['device_model'],
                        serial_id=self.sanitize_label(sys_info.get('serial_id', 'Unknown'))
                    ).set(sys_info['uptime_seconds'])
                except Exception as e:
                    logger.error(f"Error setting system uptime metric: {e}")

            if 'temperature_c' in sys_info:
                self.system_temperature.labels(
                    device_name=labels['device_name']
                ).set(sys_info['temperature_c'])
            
            # Device info
            info_data = {
                'version': sys_info.get('version', 'Unknown'),
                'board_model': sys_info.get('board_model', 'Unknown'),
                'serial_id': sys_info.get('serial_id', 'Unknown'),
                'mac_address': sys_info.get('mac_address', 'Unknown'),
                'build_date': sys_info.get('build_date', 'Unknown')
            }
            self.device_info.labels(
                device_name=labels['device_name']
            ).info(info_data)

        # Port metrics
        if 'port_details' in metrics:
            for port in metrics['port_details']:
                port_labels = {
                    'device_name': labels['device_name'],
                    'port_name': self.sanitize_label(port['name']),
                    'port_index': str(port['index'])
                }
                
                self.port_status.labels(**port_labels).set(1 if port['enabled'] else 0)
                self.port_link_status.labels(**port_labels).set(1 if port['linked'] else 0)
                self.port_speed_mbps.labels(**port_labels).set(port['speed_mbps'])
        
        # Port statistics
        if 'port_stats' in metrics:
            for port_stat in metrics['port_stats']:
                port_labels = {
                    'device_name': labels['device_name'],
                    'port_name': self.sanitize_label(port_stat['port_name']),
                    'port_index': str(port_stat['port_index'])
                }
                
                # Update counters
                if 'rx_bytes_total' in port_stat:
                    self.port_rx_bytes.labels(**port_labels)._value._value = port_stat['rx_bytes_total']
                if 'tx_bytes_total' in port_stat:
                    self.port_tx_bytes.labels(**port_labels)._value._value = port_stat['tx_bytes_total']
                if 'rx_total_packets' in port_stat:
                    self.port_rx_packets.labels(**port_labels)._value._value = port_stat['rx_total_packets']
                if 'tx_total_packets' in port_stat:
                    self.port_tx_packets.labels(**port_labels)._value._value = port_stat['tx_total_packets']
                if 'rx_errors' in port_stat:
                    self.port_rx_errors.labels(**port_labels)._value._value = port_stat['rx_errors']
                if 'tx_errors' in port_stat:
                    self.port_tx_errors.labels(**port_labels)._value._value = port_stat['tx_errors']
        
        # VLAN metrics
        if 'vlan_table' in metrics:
            vlan_count = len(metrics['vlan_table'])
            self.vlan_count.labels(
                device_name=labels['device_name']
            ).set(vlan_count)

            for vlan in metrics['vlan_table']:
                self.vlan_ports.labels(
                    device_name=labels['device_name'],
                    vlan_id=str(vlan['vlan_id'])
                ).set(vlan['member_count'])
        
        # MAC table metrics
        if 'mac_stats' in metrics:
            mac_stats = metrics['mac_stats']
            
            self.mac_table_entries.labels(
                device_name=labels['device_name']
            ).set(mac_stats['total_entries'])

            for vlan_id, count in mac_stats.get('entries_by_vlan', {}).items():
                self.mac_table_entries_by_vlan.labels(
                    device_name=labels['device_name'],
                    vlan_id=str(vlan_id)
                ).set(count)
        
        # SFP metrics
        if 'sfp_modules' in metrics:
            for sfp in metrics['sfp_modules']:
                sfp_labels = {
                    'device_name': labels['device_name'],
                    'sfp_index': str(sfp['index']),
                    'vendor': self.sanitize_label(sfp.get('vendor', 'Unknown')),
                    'part_number': self.sanitize_label(sfp.get('part_number', 'Unknown'))
                }
                
                if 'temperature_c' in sfp:
                    self.sfp_temperature.labels(**sfp_labels).set(sfp['temperature_c'])
                if 'tx_power_mw' in sfp:
                    self.sfp_tx_power.labels(**sfp_labels).set(sfp['tx_power_mw'])
                if 'rx_power_mw' in sfp:
                    self.sfp_rx_power.labels(**sfp_labels).set(sfp['rx_power_mw'])

        # PoE metrics
        if 'poe_ports' in metrics:
            for poe in metrics['poe_ports']:
                poe_labels = {
                    'device_name': labels['device_name'],
                    'port_name': self.sanitize_label(poe['port_name']),
                    'port_index': str(poe['port_index'])
                }
                self.poe_status.labels(**poe_labels).set(poe['status'])
                self.poe_current.labels(**poe_labels).set(poe['current_ma'])
                self.poe_power.labels(**poe_labels).set(poe['power_w'])
                if 'voltage_v' in poe:
                    self.poe_voltage.labels(**poe_labels).set(poe['voltage_v'])

    def collect_all_metrics(self):
        """Collect metrics from all devices"""
        cycle_start = time.time()
        devices_count = 0

        try:
            # Get devices from the config file
            devices = self.device_client.fetch_devices()
            logger.info(f"Found {len(devices)} devices to monitor")

            # Collect metrics from each device
            for device in devices:
                self.collect_device_metrics(device)
                devices_count += 1

            # Update health tracking
            self.last_collection_time = time.time()
            self.last_collection_success = True
            self.last_collection_timestamp.set(self.last_collection_time)
            self.devices_collected.set(devices_count)

        except Exception as e:
            logger.error(f"Error in metric collection cycle: {e}")
            self.last_collection_success = False

        # Always update cycle duration
        cycle_duration = time.time() - cycle_start
        self.collection_cycle_duration.set(cycle_duration)
    
    def start_collection_loop(self, interval: int = 60):
        """Start the metrics collection loop"""
        self.collection_interval = interval

        def collection_loop():
            while True:
                try:
                    logger.info("Starting metrics collection cycle")
                    self.collect_all_metrics()
                    logger.info(f"Metrics collection completed, sleeping for {interval}s")
                    time.sleep(interval)
                except Exception as e:
                    logger.error(f"Error in collection loop: {e}")
                    time.sleep(30)  # Shorter sleep on error

        # Start collection in background thread
        collection_thread = threading.Thread(target=collection_loop, daemon=True)
        collection_thread.start()
        logger.info(f"Started metrics collection loop with {interval}s interval")

    def is_healthy(self) -> bool:
        """Check if the exporter is healthy (collecting metrics recently)"""
        if self.last_collection_time == 0:
            # Allow grace period for initial startup (3x interval)
            return True

        time_since_collection = time.time() - self.last_collection_time
        max_allowed = self.collection_interval * 3  # Allow 3x interval before unhealthy

        return time_since_collection < max_allowed and self.last_collection_success

    def start_health_server(self):
        """Start a simple HTTP server for health checks"""
        exporter = self

        class HealthHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass  # Suppress access logs

            def do_GET(self):
                if self.path == '/health' or self.path == '/healthz':
                    if exporter.is_healthy():
                        self.send_response(200)
                        self.send_header('Content-Type', 'text/plain')
                        self.end_headers()
                        msg = f"OK - last collection {int(time.time() - exporter.last_collection_time)}s ago\n"
                        self.wfile.write(msg.encode())
                    else:
                        self.send_response(503)
                        self.send_header('Content-Type', 'text/plain')
                        self.end_headers()
                        msg = f"UNHEALTHY - last collection {int(time.time() - exporter.last_collection_time)}s ago\n"
                        self.wfile.write(msg.encode())
                else:
                    self.send_response(404)
                    self.end_headers()

        def run_health_server():
            server = HTTPServer(('0.0.0.0', self.health_port), HealthHandler)
            server.serve_forever()

        health_thread = threading.Thread(target=run_health_server, daemon=True)
        health_thread.start()
        logger.info(f"Health check server started on http://0.0.0.0:{self.health_port}/health")
    
    def run(self, collection_interval: int = 60):
        """Run the exporter"""
        logger.info(f"Starting SwitchOS Prometheus Exporter on port {self.port}")

        # Start health check server
        self.start_health_server()

        # Start metrics collection
        self.start_collection_loop(collection_interval)

        # Start HTTP server
        start_http_server(self.port)
        logger.info(f"Prometheus metrics server started on http://0.0.0.0:{self.port}/metrics")
        
        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down exporter")

if __name__ == "__main__":
    exporter = SwitchOSExporter(port=9000)
    exporter.run(collection_interval=60)