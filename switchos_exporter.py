#!/usr/bin/env python3
"""
MikroTik SwitchOS Prometheus Exporter
Collects metrics from MikroTik switches discovered via Netbox
"""

import time
import logging
import threading
from typing import Dict, List, Any
from prometheus_client import start_http_server, Gauge, Counter, Info, Enum, REGISTRY
from netbox_client import NetboxClient
from switchos_client import SwitchOSClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class SwitchOSExporter:
    def __init__(self, port: int = 9000):
        self.port = port
        self.netbox_client = NetboxClient()
        self.switchos_client = SwitchOSClient()
        self.metrics = {}
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
            ['device_name', 'site', 'site_id', 'location', 'device_model', 'manufacturer', 'device_role']
        )
        
        self.collection_duration = Gauge(
            'switchos_collection_duration_seconds',
            'Time spent collecting metrics from device',
            ['device_name', 'site', 'site_id', 'location']
        )
        
        # System metrics
        self.system_uptime = Gauge(
            'switchos_system_uptime_seconds',
            'System uptime in seconds',
            ['device_name', 'site', 'site_id', 'location', 'device_model', 'serial_id']
        )
        
        self.system_temperature = Gauge(
            'switchos_system_temperature_celsius',
            'System temperature in Celsius',
            ['device_name', 'site', 'site_id', 'location']
        )
        
        # Port metrics
        self.port_status = Gauge(
            'switchos_port_status',
            'Port status (1=enabled, 0=disabled)',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_link_status = Gauge(
            'switchos_port_link_status',
            'Port link status (1=linked, 0=down)',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_speed_mbps = Gauge(
            'switchos_port_speed_mbps',
            'Port speed in Mbps',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        # Port statistics
        self.port_rx_bytes = Counter(
            'switchos_port_rx_bytes_total',
            'Total received bytes',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_tx_bytes = Counter(
            'switchos_port_tx_bytes_total',
            'Total transmitted bytes',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_rx_packets = Counter(
            'switchos_port_rx_packets_total',
            'Total received packets',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_tx_packets = Counter(
            'switchos_port_tx_packets_total',
            'Total transmitted packets',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_rx_errors = Counter(
            'switchos_port_rx_errors_total',
            'Total receive errors',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        self.port_tx_errors = Counter(
            'switchos_port_tx_errors_total',
            'Total transmit errors',
            ['device_name', 'site', 'site_id', 'location', 'port_name', 'port_index']
        )
        
        # VLAN metrics
        self.vlan_count = Gauge(
            'switchos_vlan_count',
            'Number of configured VLANs',
            ['device_name', 'site', 'site_id', 'location']
        )
        
        self.vlan_ports = Gauge(
            'switchos_vlan_port_members',
            'Number of member ports in VLAN',
            ['device_name', 'site', 'site_id', 'location', 'vlan_id']
        )
        
        # MAC table metrics
        self.mac_table_entries = Gauge(
            'switchos_mac_table_entries',
            'Number of MAC address table entries',
            ['device_name', 'site', 'site_id', 'location']
        )
        
        self.mac_table_entries_by_vlan = Gauge(
            'switchos_mac_table_entries_by_vlan',
            'MAC address table entries per VLAN',
            ['device_name', 'site', 'site_id', 'location', 'vlan_id']
        )
        
        # SFP metrics
        self.sfp_temperature = Gauge(
            'switchos_sfp_temperature_celsius',
            'SFP module temperature in Celsius',
            ['device_name', 'site', 'site_id', 'location', 'sfp_index', 'vendor', 'part_number']
        )
        
        self.sfp_tx_power = Gauge(
            'switchos_sfp_tx_power_mw',
            'SFP module TX power in milliwatts',
            ['device_name', 'site', 'site_id', 'location', 'sfp_index', 'vendor', 'part_number']
        )
        
        self.sfp_rx_power = Gauge(
            'switchos_sfp_rx_power_mw',
            'SFP module RX power in milliwatts',
            ['device_name', 'site', 'site_id', 'location', 'sfp_index', 'vendor', 'part_number']
        )
        
        # Info metrics
        self.device_info = Info(
            'switchos_device_info',
            'Device information',
            ['device_name', 'site', 'site_id', 'location']
        )
        
    def collect_device_metrics(self, device: Dict[str, Any]):
        """Collect metrics from a single device"""
        device_name = self.sanitize_label(device['name'])
        device_ip = device['ip']
        site = self.sanitize_label(device['site'])
        site_id = self.sanitize_label(device['site_id'])
        location = self.sanitize_label(device['location'])
        
        logger.info(f"Collecting metrics from {device_name} ({device_ip}) at site {site_id}")
        
        start_time = time.time()
        
        try:
            # Collect all metrics from device
            metrics = self.switchos_client.collect_metrics(device_ip, device)
            
            # Common labels (sanitize all for Prometheus)
            labels = {
                'device_name': device_name,
                'site': site,
                'site_id': site_id,
                'location': location,
                'device_model': self.sanitize_label(device.get('device_model', 'Unknown')),
                'manufacturer': self.sanitize_label(device.get('manufacturer', 'Unknown')),
                'device_role': self.sanitize_label(device.get('device_role', 'Unknown'))
            }
            
            # Device status
            self.device_up.labels(**labels).set(metrics['up'])
            
            # Collection duration
            duration = time.time() - start_time
            self.collection_duration.labels(
                device_name=device_name,
                site=site,
                site_id=site_id,
                location=location
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
                    'site': self.sanitize_label(device.get('site', 'Unknown')),
                    'site_id': self.sanitize_label(device.get('site_id', 'unknown')),
                    'location': self.sanitize_label(device.get('location', 'Unknown')),
                    'device_model': self.sanitize_label(device.get('device_model', 'Unknown')),
                    'manufacturer': self.sanitize_label(device.get('manufacturer', 'Unknown')),
                    'device_role': self.sanitize_label(device.get('device_role', 'Unknown'))
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
                    # system_uptime needs: device_name, site, site_id, location, device_model, serial_id
                    self.system_uptime.labels(
                        device_name=labels['device_name'],
                        site=labels['site'],
                        site_id=labels['site_id'],
                        location=labels['location'],
                        device_model=labels['device_model'],
                        serial_id=self.sanitize_label(sys_info.get('serial_id', 'Unknown'))
                    ).set(sys_info['uptime_seconds'])
                except Exception as e:
                    logger.error(f"Error setting system uptime metric: {e}")
            
            if 'temperature_c' in sys_info:
                self.system_temperature.labels(
                    device_name=labels['device_name'],
                    site=labels['site'],
                    site_id=labels['site_id'],
                    location=labels['location']
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
                device_name=labels['device_name'],
                site=labels['site'],
                site_id=labels['site_id'],
                location=labels['location']
            ).info(info_data)
        
        # Port metrics
        if 'port_details' in metrics:
            for port in metrics['port_details']:
                port_labels = {
                    'device_name': labels['device_name'],
                    'site': labels['site'],
                    'site_id': labels['site_id'],
                    'location': labels['location'],
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
                    'site': labels['site'],
                    'site_id': labels['site_id'],
                    'location': labels['location'],
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
                device_name=labels['device_name'],
                site=labels['site'],
                site_id=labels['site_id'],
                location=labels['location']
            ).set(vlan_count)
            
            for vlan in metrics['vlan_table']:
                self.vlan_ports.labels(
                    device_name=labels['device_name'],
                    site=labels['site'],
                    site_id=labels['site_id'],
                    location=labels['location'],
                    vlan_id=str(vlan['vlan_id'])
                ).set(vlan['member_count'])
        
        # MAC table metrics
        if 'mac_stats' in metrics:
            mac_stats = metrics['mac_stats']
            
            self.mac_table_entries.labels(
                device_name=labels['device_name'],
                site=labels['site'],
                site_id=labels['site_id'],
                location=labels['location']
            ).set(mac_stats['total_entries'])
            
            for vlan_id, count in mac_stats.get('entries_by_vlan', {}).items():
                self.mac_table_entries_by_vlan.labels(
                    device_name=labels['device_name'],
                    site=labels['site'],
                    site_id=labels['site_id'],
                    location=labels['location'],
                    vlan_id=str(vlan_id)
                ).set(count)
        
        # SFP metrics
        if 'sfp_modules' in metrics:
            for sfp in metrics['sfp_modules']:
                sfp_labels = {
                    'device_name': labels['device_name'],
                    'site': labels['site'],
                    'site_id': labels['site_id'],
                    'location': labels['location'],
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
    
    def collect_all_metrics(self):
        """Collect metrics from all devices"""
        try:
            # Get devices from Netbox
            devices = self.netbox_client.fetch_devices()
            logger.info(f"Found {len(devices)} devices to monitor")
            
            # Collect metrics from each device
            for device in devices:
                self.collect_device_metrics(device)
                
        except Exception as e:
            logger.error(f"Error in metric collection cycle: {e}")
    
    def start_collection_loop(self, interval: int = 60):
        """Start the metrics collection loop"""
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
    
    def run(self, collection_interval: int = 60):
        """Run the exporter"""
        logger.info(f"Starting SwitchOS Prometheus Exporter on port {self.port}")
        
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