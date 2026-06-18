import os
import yaml
from typing import List, Dict
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default config file location; override with the SWITCHOS_CONFIG env var.
DEFAULT_CONFIG_FILE = 'devices.yaml'


class DeviceConfigClient:
    """Load all exporter configuration from a single YAML file.

    The file holds an optional `defaults` mapping (applied to every device)
    and a `devices` list. fetch_devices() returns the list-of-dicts shape the
    exporter consumes, with credentials and labels resolved against defaults.
    """

    def __init__(self):
        self.config_file = os.getenv('SWITCHOS_CONFIG', DEFAULT_CONFIG_FILE)

        if not os.path.isfile(self.config_file):
            raise ValueError(
                f"Config file not found: '{self.config_file}'. "
                f"Create it (see devices.yaml.example) or set SWITCHOS_CONFIG."
            )

    def fetch_devices(self) -> List[Dict[str, str]]:
        """Load and normalise devices from the YAML config file."""
        logger.info(f"Loading configuration from: {self.config_file}")

        with open(self.config_file, 'r') as f:
            config = yaml.safe_load(f) or {}

        defaults = config.get('defaults') or {}
        if not isinstance(defaults, dict):
            raise ValueError(f"'defaults' in '{self.config_file}' must be a mapping")

        raw_devices = config.get('devices')
        if not isinstance(raw_devices, list) or not raw_devices:
            raise ValueError(
                f"Config file '{self.config_file}' must contain a non-empty "
                f"top-level 'devices:' list"
            )

        devices = []
        for entry in raw_devices:
            if not isinstance(entry, dict):
                logger.warning(f"Skipping invalid device entry (not a mapping): {entry!r}")
                continue

            name = entry.get('name', 'Unknown')

            # Strip CIDR notation if present (e.g. 192.168.1.1/24 -> 192.168.1.1)
            ip = entry.get('ip')
            if ip:
                ip = str(ip).split('/')[0]

            # Resolve each field against `defaults` (per-device value wins)
            def resolve(key, fallback='Unknown'):
                return entry.get(key, defaults.get(key, fallback))

            device_info = {
                'name': name,
                'ip': ip,
                'device_model': resolve('device_model'),
                'manufacturer': resolve('manufacturer'),
                'user': resolve('user', ''),
                'password': resolve('password', ''),
            }

            if device_info['ip']:
                devices.append(device_info)
                logger.info(
                    f"Found device: {device_info['name']} ({device_info['ip']})"
                )
            else:
                logger.warning(f"Device {name} has no 'ip', skipping")

        logger.info(f"Total devices loaded: {len(devices)}")
        return devices


if __name__ == "__main__":
    # Test the device config client
    client = DeviceConfigClient()

    print(f"Loading devices from {client.config_file}...")
    devices = client.fetch_devices()

    if devices:
        print(f"\nFound {len(devices)} devices:")
        for device in devices:
            print(f"  - {device['name']}: {device['ip']} (user: {device['user']})")
    else:
        print("No devices found in config file")
