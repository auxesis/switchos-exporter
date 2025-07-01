import os
import requests
from typing import List, Dict, Optional
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class NetboxClient:
    def __init__(self):
        load_dotenv()
        self.api_url = os.getenv('netbox_api_url', '').rstrip('/')
        self.api_token = os.getenv('netbox_api_token', '')
        self.manufacturer = os.getenv('netbox_manufacturer', 'MikroTik')
        self.role = os.getenv('netbox_role', 'switch')
        self.tags = os.getenv('netbox_tags', 'Monitoring')
        
        if not self.api_url or not self.api_token:
            raise ValueError("Netbox API URL and token must be set in .env file")
        
        self.headers = {
            'Authorization': f'Token {self.api_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    
    def fetch_devices(self) -> List[Dict[str, str]]:
        """Fetch MikroTik switches from Netbox API"""
        devices = []
        
        # Build query parameters
        params = {
            'manufacturer': self.manufacturer.lower(),  # Use slug format
            'role': self.role.lower(),  # Use slug format
            'tag': self.tags.lower(),  # Tags are also slugified
            'status': 'active',  # Only fetch active devices
            'has_primary_ip': 'true'  # Only devices with primary IP
        }
        
        endpoint = f"{self.api_url}/dcim/devices/"
        
        try:
            logger.info(f"Fetching devices from Netbox: {endpoint}")
            logger.info(f"Filters: manufacturer={self.manufacturer}, role={self.role}, tags={self.tags}")
            
            # Fetch all pages of results
            while endpoint:
                response = requests.get(endpoint, headers=self.headers, params=params)
                response.raise_for_status()
                
                data = response.json()
                results = data.get('results', [])
                
                for device in results:
                    # Extract device name and primary IPv4
                    device_info = {
                        'name': device.get('name', 'Unknown'),
                        'ip': None,
                        'id': device.get('id'),
                        'site': device.get('site', {}).get('name', 'Unknown') if device.get('site') else 'Unknown',
                        'site_id': device.get('site', {}).get('slug', 'unknown') if device.get('site') else 'unknown',
                        'site_description': device.get('site', {}).get('description', '') if device.get('site') else '',
                        'location': device.get('location', {}).get('name', '') if device.get('location') else '',
                        'device_role': device.get('role', {}).get('name', 'Unknown') if device.get('role') else 'Unknown',
                        'device_model': device.get('device_type', {}).get('model', 'Unknown') if device.get('device_type') else 'Unknown',
                        'manufacturer': device.get('device_type', {}).get('manufacturer', {}).get('name', 'Unknown') if device.get('device_type', {}).get('manufacturer') else 'Unknown'
                    }
                    
                    # Get primary IPv4 address
                    primary_ip = device.get('primary_ip4')
                    if primary_ip and isinstance(primary_ip, dict):
                        ip_address = primary_ip.get('address', '')
                        # Remove CIDR notation if present
                        device_info['ip'] = ip_address.split('/')[0]
                    
                    if device_info['ip']:
                        devices.append(device_info)
                        logger.info(f"Found device: {device_info['name']} ({device_info['ip']}) at site {device_info['site']}")
                    else:
                        logger.warning(f"Device {device_info['name']} has no primary IPv4 address, skipping")
                
                # Check for next page
                endpoint = data.get('next')
                params = None  # Don't send params again for pagination
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching devices from Netbox: {e}")
            raise
        
        logger.info(f"Total devices found: {len(devices)}")
        return devices
    
    def test_connection(self) -> bool:
        """Test connection to Netbox API"""
        try:
            response = requests.get(
                f"{self.api_url}/dcim/manufacturers/",
                headers=self.headers,
                params={'limit': 1}
            )
            response.raise_for_status()
            logger.info("Successfully connected to Netbox API")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to Netbox API: {e}")
            return False


if __name__ == "__main__":
    # Test the Netbox client
    client = NetboxClient()
    
    print("Testing Netbox connection...")
    if client.test_connection():
        print("\nFetching MikroTik switches...")
        devices = client.fetch_devices()
        
        if devices:
            print(f"\nFound {len(devices)} devices:")
            for device in devices:
                print(f"  - {device['name']}: {device['ip']} (Site: {device['site']})")
        else:
            print("No devices found matching the criteria")
    else:
        print("Failed to connect to Netbox API")