import requests
from requests.auth import HTTPDigestAuth
from typing import Dict, Optional, Any, Union, List
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SwitchOSClient:
    def __init__(self):
        # Credentials are supplied per-device (resolved from the YAML config)
        # and set on each call to collect_metrics().
        self.active_username = ''
        self.active_password = ''
        self.timeout = 30
        self.retry_count = 3
        self.retry_delay = 2
    
    def _decode_hex_value(self, value: Union[str, List, Dict, Any]) -> Union[str, List, Dict, Any]:
        """Recursively decode hex values in data structures"""
        if isinstance(value, str):
            # Skip if empty or too short
            if not value or len(value) < 2:
                return value
                
            # Remove common hex prefixes
            test_value = value.strip()
            if test_value.startswith('0x') or test_value.startswith('0X'):
                return value  # Keep as-is, it's a number not a string
            
            # Check if it's a hex string (only contains hex chars, possibly with spaces)
            hex_chars = '0123456789abcdefABCDEF'
            clean_value = value.replace(' ', '').replace('\n', '').replace('\r', '')
            
            # Must be even length and all hex chars
            if clean_value and len(clean_value) % 2 == 0 and all(c in hex_chars for c in clean_value):
                try:
                    # Try to decode as UTF-8 first, then ASCII, then Latin-1
                    raw_bytes = bytes.fromhex(clean_value)
                    
                    for encoding in ['utf-8', 'ascii', 'latin-1']:
                        try:
                            decoded = raw_bytes.decode(encoding)
                            # Check if result is meaningful (has some printable chars)
                            printable_count = sum(1 for c in decoded if c.isprintable() or c in '\n\r\t')
                            total_chars = len(decoded)
                            
                            # More lenient: accept if >50% printable or if it's short and has any printable
                            if total_chars > 0 and (printable_count / total_chars > 0.5 or 
                                                   (total_chars <= 4 and printable_count > 0)):
                                return decoded.strip()
                        except:
                            continue
                except:
                    pass
            return value
        elif isinstance(value, list):
            return [self._decode_hex_value(item) for item in value]
        elif isinstance(value, dict):
            return {k: self._decode_hex_value(v) for k, v in value.items()}
        else:
            return value
        
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make HTTP request with retry logic and error handling"""
        auth = HTTPDigestAuth(self.active_username, self.active_password)
        kwargs.setdefault('timeout', self.timeout)
        kwargs['auth'] = auth
        
        for attempt in range(self.retry_count):
            try:
                response = requests.request(method, url, **kwargs)
                
                if response.status_code == 401:
                    logger.error(f"Authentication failed for {url}")
                    return None
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1} for {url}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Failed after {self.retry_count} attempts: {url}")
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for {url}: {e}")
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                else:
                    return None
        
        return None
    
    def test_connection(self, device_ip: str) -> bool:
        """Test connection and authentication to a device"""
        url = f"http://{device_ip}/backup.swb"
        logger.info(f"Testing connection to {device_ip}")
        
        response = self._make_request('GET', url)
        if response and response.status_code == 200:
            logger.info(f"Successfully authenticated to {device_ip}")
            return True
        else:
            logger.error(f"Failed to authenticate to {device_ip}")
            return False
    
    def get_link_status(self, device_ip: str) -> Optional[Dict]:
        """Get link/port status from device"""
        url = f"http://{device_ip}/link.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # The response is JavaScript object notation, not strict JSON
                # Need to convert it to valid JSON by adding quotes
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values (0x...) - both in objects and arrays
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Add quotes around single-quoted strings
                json_text = json_text.replace("'", '"')
                
                # Parse the fixed JSON
                return json.loads(json_text)
            except Exception as e:
                logger.error(f"Failed to parse link status response: {e}")
                logger.error(f"Response text: {response.text[:500]}")
                return {}
        return {}
    
    def get_sfp_status(self, device_ip: str) -> Optional[Dict]:
        """Get SFP module status from device"""
        url = f"http://{device_ip}/sfp.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # Parse the JavaScript object notation
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Add quotes around single-quoted strings
                json_text = json_text.replace("'", '"')
                
                # Parse the fixed JSON
                data = json.loads(json_text)
                
                # Decode all hex values automatically
                return self._decode_hex_value(data)
            except Exception as e:
                logger.error(f"Failed to parse SFP status response: {e}")
                return {}
        return {}
    
    def parse_sfp_metrics(self, sfp_data: Dict) -> Dict[str, Any]:
        """Parse SFP data to extract module metrics"""
        metrics = {
            'sfp_modules': []
        }
        
        try:
            # Get vendor names
            vendors = sfp_data.get('vnd', [])
            part_numbers = sfp_data.get('pnr', [])
            serials = sfp_data.get('ser', [])
            dates = sfp_data.get('dat', [])
            types = sfp_data.get('typ', [])
            temperatures = sfp_data.get('tmp', [])
            voltages = sfp_data.get('vcc', [])
            tx_power = sfp_data.get('tpw', [])
            rx_power = sfp_data.get('rpw', [])
            
            # Process each SFP module (usually 2 for SFP+ ports)
            num_modules = max(len(vendors), len(part_numbers))
            
            for i in range(num_modules):
                # Skip empty modules
                if i < len(vendors) and vendors[i] and vendors[i].strip():
                    module = {
                        'index': i + 1,
                        'vendor': vendors[i] if i < len(vendors) else '',
                        'part_number': part_numbers[i] if i < len(part_numbers) else '',
                        'serial': serials[i] if i < len(serials) else '',
                        'date': dates[i] if i < len(dates) else '',
                        'type': types[i] if i < len(types) else '',
                        'present': True
                    }
                    
                    # Add numeric values if available
                    if i < len(temperatures):
                        # Convert hex temperature to Celsius
                        temp_val = temperatures[i]
                        if isinstance(temp_val, str):
                            if temp_val.startswith('0x'):
                                temp_val = int(temp_val, 16)
                            else:
                                temp_val = int(temp_val.strip('"'), 16) if temp_val.strip('"').startswith('0x') else 0
                        module['temperature_c'] = temp_val / 256.0 if temp_val else 0
                    
                    if i < len(voltages):
                        volt_val = voltages[i]
                        if isinstance(volt_val, str):
                            if volt_val.startswith('0x'):
                                volt_val = int(volt_val, 16)
                            else:
                                volt_val = int(volt_val.strip('"'), 16) if volt_val.strip('"').startswith('0x') else 0
                        module['voltage_v'] = volt_val / 10000.0 if volt_val else 0
                    
                    if i < len(tx_power):
                        tx_val = tx_power[i]
                        if isinstance(tx_val, str):
                            if tx_val.startswith('0x'):
                                tx_val = int(tx_val, 16)
                            else:
                                tx_val = int(tx_val.strip('"'), 16) if tx_val.strip('"').startswith('0x') else 0
                        module['tx_power_mw'] = tx_val / 10000.0 if tx_val else 0
                    
                    if i < len(rx_power):
                        rx_val = rx_power[i]
                        if isinstance(rx_val, str):
                            if rx_val.startswith('0x'):
                                rx_val = int(rx_val, 16)
                            else:
                                rx_val = int(rx_val.strip('"'), 16) if rx_val.strip('"').startswith('0x') else 0
                        module['rx_power_mw'] = rx_val / 10000.0 if rx_val else 0
                    
                    metrics['sfp_modules'].append(module)
            
            logger.info(f"Found {len(metrics['sfp_modules'])} SFP modules")
            
        except Exception as e:
            logger.error(f"Error parsing SFP data: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def get_port_stats(self, device_ip: str) -> Optional[Dict]:
        """Get port statistics from device"""
        url = f"http://{device_ip}/stats.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            # Some switch models don't serve port stats and return an empty body
            # or the HTML web UI instead of the expected `{...}` object notation.
            # Treat anything that isn't the stats payload as "no stats available".
            body = response.text.strip()
            if not body.startswith('{'):
                logger.debug(f"No port stats available from {device_ip} "
                             f"(unexpected response, {len(body)} bytes)")
                return {}
            try:
                # Parse the JavaScript object notation
                import re
                import json

                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)

                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)

                # Parse the fixed JSON
                return json.loads(json_text)
            except Exception as e:
                logger.error(f"Failed to parse port stats response: {e}")
                return {}
        return {}
    
    def parse_port_stats(self, stats_data: Dict, port_details: List[Dict]) -> Dict[str, Any]:
        """Parse port statistics data"""
        metrics = {'port_stats': []}
        
        try:
            # Key mappings for stats
            stat_keys = {
                'rb': 'rx_bytes',          # RX bytes
                'rbh': 'rx_bytes_high',    # RX bytes high (for 64-bit)
                'rup': 'rx_unicast',       # RX unicast packets
                'rbp': 'rx_broadcast',     # RX broadcast packets
                'rmp': 'rx_multicast',     # RX multicast packets
                'rtp': 'rx_total_packets', # RX total packets
                'rrb': 'rx_runt_bytes',    # RX runt frames
                'rrp': 'rx_runt_packets',  # RX runt packets
                'rov': 'rx_oversize',      # RX oversize
                'rr': 'rx_rate',           # RX rate
                'rfcs': 'rx_fcs_errors',   # RX FCS errors
                'rae': 'rx_align_errors',  # RX alignment errors
                'rte': 'rx_too_long',      # RX too long errors
                'tb': 'tx_bytes',          # TX bytes
                'tbh': 'tx_bytes_high',    # TX bytes high
                'tup': 'tx_unicast',       # TX unicast packets
                'tbp': 'tx_broadcast',     # TX broadcast packets
                'tmp': 'tx_multicast',     # TX multicast packets
                'ttp': 'tx_total_packets', # TX total packets
                'trb': 'tx_runt_bytes',    # TX runt frames
                'trp': 'tx_runt_packets',  # TX runt packets
                'tcl': 'tx_collisions',    # TX collisions
                'tlc': 'tx_late_collision',# TX late collisions
                'tec': 'tx_excessive_coll',# TX excessive collisions
                'tmc': 'tx_multi_coll',    # TX multiple collisions
                'tpp': 'tx_pause_packets', # TX pause packets
                'rpp': 'rx_pause_packets', # RX pause packets
                'p64': 'packets_64',       # 64 byte packets
                'p65': 'packets_65_127',   # 65-127 byte packets
                'p128': 'packets_128_255', # 128-255 byte packets
                'p256': 'packets_256_511', # 256-511 byte packets
                'p512': 'packets_512_1023',# 512-1023 byte packets
                'p1k': 'packets_1024_max', # 1024+ byte packets
            }
            
            # Process each port's stats
            for i, port in enumerate(port_details):
                port_stat = {
                    'port_index': port['index'],
                    'port_name': port['name']
                }
                
                # Extract stats for this port
                for raw_key, metric_name in stat_keys.items():
                    if raw_key in stats_data:
                        values = stats_data[raw_key]
                        if i < len(values):
                            value = values[i]
                            # Convert hex string to int if needed
                            if isinstance(value, str):
                                value = int(value.strip('"'), 16) if value.strip('"').startswith('0x') else 0
                            port_stat[metric_name] = value
                
                # Calculate 64-bit values where we have high/low parts
                if 'rx_bytes' in port_stat and 'rx_bytes_high' in port_stat:
                    port_stat['rx_bytes_total'] = (port_stat.get('rx_bytes_high', 0) << 32) + port_stat.get('rx_bytes', 0)
                
                if 'tx_bytes' in port_stat and 'tx_bytes_high' in port_stat:
                    port_stat['tx_bytes_total'] = (port_stat.get('tx_bytes_high', 0) << 32) + port_stat.get('tx_bytes', 0)
                
                # Calculate error rates
                port_stat['rx_errors'] = sum([
                    port_stat.get('rx_fcs_errors', 0),
                    port_stat.get('rx_align_errors', 0),
                    port_stat.get('rx_too_long', 0),
                    port_stat.get('rx_runt_packets', 0)
                ])
                
                port_stat['tx_errors'] = sum([
                    port_stat.get('tx_collisions', 0),
                    port_stat.get('tx_late_collision', 0),
                    port_stat.get('tx_excessive_coll', 0),
                    port_stat.get('tx_runt_packets', 0)
                ])
                
                metrics['port_stats'].append(port_stat)
            
            logger.info(f"Parsed stats for {len(metrics['port_stats'])} ports")
            
        except Exception as e:
            logger.error(f"Error parsing port stats: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def get_vlan_config(self, device_ip: str) -> Optional[Dict]:
        """Get VLAN/forwarding configuration from device"""
        url = f"http://{device_ip}/fwd.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # Parse the JavaScript object notation
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Add quotes around single-quoted strings
                json_text = json_text.replace("'", '"')
                
                # Parse the fixed JSON
                data = json.loads(json_text)
                
                # Decode all hex values automatically
                return self._decode_hex_value(data)
            except Exception as e:
                logger.error(f"Failed to parse VLAN config response: {e}")
                return {}
        return {}
    
    def parse_vlan_config(self, vlan_data: Dict, port_details: List[Dict]) -> Dict[str, Any]:
        """Parse VLAN configuration data"""
        metrics = {'vlan_config': []}
        
        try:
            # VLAN mode mappings (based on SwitchOS values)
            vlan_mode_map = {
                0: 'disabled',
                1: 'optional', 
                2: 'enabled',
                3: 'strict'
            }
            
            # VLAN ingress mode mappings  
            vlan_ingress_map = {
                0: 'fallback',
                1: 'check',
                2: 'secure',
                3: 'disabled'
            }
            
            # Get VLAN configuration arrays (from actual response structure)
            vlan_modes = vlan_data.get('vlan', [])    # VLAN mode per port
            vlan_receive = vlan_data.get('vlni', [])  # VLAN ingress mode per port  
            default_vlans = vlan_data.get('dvid', []) # Default VLAN ID per port
            stp_state = vlan_data.get('srt', [])      # STP state per port
            
            # Port forwarding masks
            port_forwards = {}
            for i in range(1, 27):  # Ports 1-26
                fp_key = f'fp{i}'
                if fp_key in vlan_data:
                    port_forwards[i] = vlan_data[fp_key]
            
            # Process each port's VLAN config
            for i, port in enumerate(port_details):
                vlan_cfg = {
                    'port_index': port['index'],
                    'port_name': port['name']
                }
                
                # VLAN Mode
                if i < len(vlan_modes):
                    mode_val = vlan_modes[i]
                    if isinstance(mode_val, str) and mode_val.startswith('0x'):
                        mode_val = int(mode_val, 16)
                    elif isinstance(mode_val, str):
                        mode_val = int(mode_val.strip('"'), 16) if mode_val.strip('"').startswith('0x') else int(mode_val)
                    
                    vlan_cfg['vlan_mode'] = vlan_mode_map.get(mode_val, f'unknown_{mode_val}')
                    vlan_cfg['vlan_mode_raw'] = mode_val
                
                # VLAN Ingress Mode  
                if i < len(vlan_receive):
                    recv_val = vlan_receive[i]
                    if isinstance(recv_val, str) and recv_val.startswith('0x'):
                        recv_val = int(recv_val, 16)
                    elif isinstance(recv_val, str):
                        recv_val = int(recv_val.strip('"'), 16) if recv_val.strip('"').startswith('0x') else int(recv_val)
                    
                    vlan_cfg['vlan_ingress'] = vlan_ingress_map.get(recv_val, f'unknown_{recv_val}')
                    vlan_cfg['vlan_ingress_raw'] = recv_val
                
                # Default VLAN ID
                if i < len(default_vlans):
                    dvid_val = default_vlans[i]
                    if isinstance(dvid_val, str) and dvid_val.startswith('0x'):
                        dvid_val = int(dvid_val, 16)
                    elif isinstance(dvid_val, str):
                        dvid_val = int(dvid_val.strip('"'), 16) if dvid_val.strip('"').startswith('0x') else int(dvid_val)
                    
                    vlan_cfg['default_vlan_id'] = dvid_val
                
                # STP State
                if i < len(stp_state):
                    stp_val = stp_state[i]
                    if isinstance(stp_val, str) and stp_val.startswith('0x'):
                        stp_val = int(stp_val, 16)
                    elif isinstance(stp_val, str):
                        stp_val = int(stp_val.strip('"'), 16) if stp_val.strip('"').startswith('0x') else int(stp_val)
                    
                    vlan_cfg['stp_state'] = stp_val
                
                # Port forwarding mask (which ports this port can forward to)
                port_num = port['index']
                if port_num in port_forwards:
                    fp_val = port_forwards[port_num]
                    if isinstance(fp_val, str) and fp_val.startswith('0x'):
                        fp_val = int(fp_val, 16)
                    elif isinstance(fp_val, str):
                        fp_val = int(fp_val.strip('"'), 16) if fp_val.strip('"').startswith('0x') else int(fp_val)
                    
                    vlan_cfg['forwarding_mask'] = hex(fp_val)
                
                metrics['vlan_config'].append(vlan_cfg)
            
            # Extract unique VLAN IDs from default_vlans
            if default_vlans:
                unique_vlans = set()
                for dvid in default_vlans:
                    if isinstance(dvid, str) and dvid.startswith('0x'):
                        dvid = int(dvid, 16)
                    elif isinstance(dvid, str):
                        dvid = int(dvid.strip('"'), 16) if dvid.strip('"').startswith('0x') else int(dvid)
                    
                    if dvid > 0:  # Only include valid VLAN IDs
                        unique_vlans.add(dvid)
                
                metrics['configured_vlans'] = sorted(list(unique_vlans))
            
            logger.info(f"Parsed VLAN config for {len(metrics['vlan_config'])} ports")
            
        except Exception as e:
            logger.error(f"Error parsing VLAN config: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def get_vlan_table(self, device_ip: str) -> Optional[List]:
        """Get VLAN table configuration from device"""
        url = f"http://{device_ip}/vlan.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # Parse the JavaScript array notation
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Parse the fixed JSON
                data = json.loads(json_text)
                
                # Decode all hex values automatically
                return self._decode_hex_value(data)
            except Exception as e:
                logger.error(f"Failed to parse VLAN table response: {e}")
                return []
        return []
    
    def parse_vlan_table(self, vlan_table: List[Dict]) -> Dict[str, Any]:
        """Parse VLAN table data"""
        metrics = {'vlan_table': []}
        
        try:
            for vlan_entry in vlan_table:
                vlan_info = {}
                
                # VLAN ID
                vid = vlan_entry.get('vid', 0)
                if isinstance(vid, str) and vid.startswith('0x'):
                    vid = int(vid, 16)
                elif isinstance(vid, str):
                    vid = int(vid.strip('"'), 16) if vid.strip('"').startswith('0x') else int(vid)
                vlan_info['vlan_id'] = vid
                
                # Port Isolation
                piso = vlan_entry.get('piso', 0)
                if isinstance(piso, str) and piso.startswith('0x'):
                    piso = int(piso, 16)
                elif isinstance(piso, str):
                    piso = int(piso.strip('"'), 16) if piso.strip('"').startswith('0x') else int(piso)
                vlan_info['port_isolation'] = bool(piso)
                
                # Learning
                lrn = vlan_entry.get('lrn', 0)
                if isinstance(lrn, str) and lrn.startswith('0x'):
                    lrn = int(lrn, 16)
                elif isinstance(lrn, str):
                    lrn = int(lrn.strip('"'), 16) if lrn.strip('"').startswith('0x') else int(lrn)
                vlan_info['learning_enabled'] = bool(lrn)
                
                # Mirror
                mrr = vlan_entry.get('mrr', 0)
                if isinstance(mrr, str) and mrr.startswith('0x'):
                    mrr = int(mrr, 16)
                elif isinstance(mrr, str):
                    mrr = int(mrr.strip('"'), 16) if mrr.strip('"').startswith('0x') else int(mrr)
                vlan_info['mirror_enabled'] = bool(mrr)
                
                # IGMP Snooping
                igmp = vlan_entry.get('igmp', 0)
                if isinstance(igmp, str) and igmp.startswith('0x'):
                    igmp = int(igmp, 16)
                elif isinstance(igmp, str):
                    igmp = int(igmp.strip('"'), 16) if igmp.strip('"').startswith('0x') else int(igmp)
                vlan_info['igmp_snooping'] = bool(igmp)
                
                # Member ports (bitmask)
                mbr = vlan_entry.get('mbr', 0)
                if isinstance(mbr, str) and mbr.startswith('0x'):
                    mbr = int(mbr, 16)
                elif isinstance(mbr, str):
                    mbr = int(mbr.strip('"'), 16) if mbr.strip('"').startswith('0x') else int(mbr)
                
                # Decode member ports from bitmask
                member_ports = []
                for port_num in range(1, 27):  # Ports 1-26
                    if mbr & (1 << (port_num - 1)):
                        member_ports.append(port_num)
                
                vlan_info['member_ports'] = member_ports
                vlan_info['member_count'] = len(member_ports)
                vlan_info['member_bitmask'] = hex(mbr)
                
                metrics['vlan_table'].append(vlan_info)
            
            # Summary statistics
            metrics['total_vlans'] = len(metrics['vlan_table'])
            metrics['vlans_with_isolation'] = sum(1 for v in metrics['vlan_table'] if v['port_isolation'])
            metrics['vlans_with_learning'] = sum(1 for v in metrics['vlan_table'] if v['learning_enabled'])
            metrics['vlans_with_igmp'] = sum(1 for v in metrics['vlan_table'] if v['igmp_snooping'])
            
            logger.info(f"Parsed VLAN table with {metrics['total_vlans']} VLANs")
            
        except Exception as e:
            logger.error(f"Error parsing VLAN table: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def get_mac_table(self, device_ip: str) -> Optional[List]:
        """Get MAC address table from device"""
        url = f"http://{device_ip}/!dhost.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # Parse the JavaScript array notation
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Add quotes around single-quoted strings
                json_text = json_text.replace("'", '"')
                
                # Parse the fixed JSON
                data = json.loads(json_text)
                
                # Decode all hex values automatically (but preserve MAC addresses)
                return data  # Don't decode hex for MAC addresses
            except Exception as e:
                logger.error(f"Failed to parse MAC table response: {e}")
                return []
        return []
    
    def parse_mac_table(self, mac_table: List[Dict]) -> Dict[str, Any]:
        """Parse MAC address table data"""
        metrics = {'mac_table': [], 'mac_stats': {}}
        
        try:
            for mac_entry in mac_table:
                mac_info = {}
                
                # MAC Address (keep as hex string, format it)
                adr = mac_entry.get('adr', '')
                if adr:
                    # Format MAC address with colons
                    formatted_mac = ':'.join([adr[i:i+2] for i in range(0, len(adr), 2)])
                    mac_info['mac_address'] = formatted_mac.upper()
                    mac_info['mac_raw'] = adr
                
                # VLAN ID
                vid = mac_entry.get('vid', 0)
                if isinstance(vid, str) and vid.startswith('0x'):
                    vid = int(vid, 16)
                elif isinstance(vid, str):
                    vid = int(vid.strip('"'), 16) if vid.strip('"').startswith('0x') else int(vid)
                mac_info['vlan_id'] = vid
                
                # Port
                prt = mac_entry.get('prt', 0)
                if isinstance(prt, str) and prt.startswith('0x'):
                    prt = int(prt, 16)
                elif isinstance(prt, str):
                    prt = int(prt.strip('"'), 16) if prt.strip('"').startswith('0x') else int(prt)
                mac_info['port'] = prt
                
                # Drop flag
                drp = mac_entry.get('drp', 0)
                if isinstance(drp, str) and drp.startswith('0x'):
                    drp = int(drp, 16)
                elif isinstance(drp, str):
                    drp = int(drp.strip('"'), 16) if drp.strip('"').startswith('0x') else int(drp)
                mac_info['drop'] = bool(drp)
                
                # Mirror flag
                mir = mac_entry.get('mir', 0)
                if isinstance(mir, str) and mir.startswith('0x'):
                    mir = int(mir, 16)
                elif isinstance(mir, str):
                    mir = int(mir.strip('"'), 16) if mir.strip('"').startswith('0x') else int(mir)
                mac_info['mirror'] = bool(mir)
                
                # Identify vendor from MAC OUI
                if adr and len(adr) >= 6:
                    oui = adr[:6].upper()
                    vendor_map = {
                        'E8DA00': 'Ubiquiti',
                        '306893': 'Ubiquiti', 
                        '326893': 'Ubiquiti',
                        '48A98A': 'Ubiquiti',
                        '000456': 'Ubiquiti',
                        '0024A4': 'Ubiquiti',
                        '085531': 'Ubiquiti',
                        '08F1B3': 'Ubiquiti',
                        '149F43': 'Ubiquiti',
                        '2CC81B': 'Ubiquiti',
                        'BC2411': 'Ubiquiti',
                        'C4AD34': 'Ubiquiti',
                        'D401C3': 'Ubiquiti'
                    }
                    mac_info['vendor'] = vendor_map.get(oui, 'Unknown')
                
                metrics['mac_table'].append(mac_info)
            
            # Calculate statistics
            metrics['mac_stats'] = {
                'total_entries': len(metrics['mac_table']),
                'entries_by_vlan': {},
                'entries_by_port': {},
                'entries_by_vendor': {},
                'dropped_entries': sum(1 for m in metrics['mac_table'] if m.get('drop', False)),
                'mirrored_entries': sum(1 for m in metrics['mac_table'] if m.get('mirror', False))
            }
            
            # Group by VLAN
            for mac in metrics['mac_table']:
                vlan = mac['vlan_id']
                metrics['mac_stats']['entries_by_vlan'][vlan] = metrics['mac_stats']['entries_by_vlan'].get(vlan, 0) + 1
            
            # Group by port
            for mac in metrics['mac_table']:
                port = mac['port']
                metrics['mac_stats']['entries_by_port'][port] = metrics['mac_stats']['entries_by_port'].get(port, 0) + 1
            
            # Group by vendor
            for mac in metrics['mac_table']:
                vendor = mac.get('vendor', 'Unknown')
                metrics['mac_stats']['entries_by_vendor'][vendor] = metrics['mac_stats']['entries_by_vendor'].get(vendor, 0) + 1
            
            logger.info(f"Parsed MAC table with {metrics['mac_stats']['total_entries']} entries")
            
        except Exception as e:
            logger.error(f"Error parsing MAC table: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def get_system_info(self, device_ip: str) -> Optional[Dict]:
        """Get system information from device"""
        url = f"http://{device_ip}/sys.b"
        headers = {
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f'http://{device_ip}/index.html'
        }
        
        response = self._make_request('GET', url, headers=headers)
        if response:
            try:
                # Parse the JavaScript object notation
                import re
                import json
                
                # Add quotes around keys
                json_text = re.sub(r'([{,])([a-zA-Z_]\w*):', r'\1"\2":', response.text)
                
                # Add quotes around hex values
                json_text = re.sub(r'([:, \[])?(0x[0-9a-fA-F]+)([,\]}])', r'\1"\2"\3', json_text)
                
                # Add quotes around single-quoted strings
                json_text = json_text.replace("'", '"')
                
                # Parse the fixed JSON
                data = json.loads(json_text)
                
                # Decode all hex values automatically
                return self._decode_hex_value(data)
            except Exception as e:
                logger.error(f"Failed to parse system info response: {e}")
                return {}
        return {}
    
    def parse_system_info(self, sys_data: Dict) -> Dict[str, Any]:
        """Parse system information data"""
        metrics = {'system_info': {}}
        
        try:
            sys_info = metrics['system_info']
            
            # Uptime (seconds)
            upt = sys_data.get('upt', 0)
            if isinstance(upt, str) and upt.startswith('0x'):
                upt = int(upt, 16)
            elif isinstance(upt, str):
                upt = int(upt.strip('"'), 16) if upt.strip('"').startswith('0x') else int(upt)
            sys_info['uptime_seconds'] = upt
            sys_info['uptime_days'] = round(upt / 86400, 1)
            
            # Current IP
            cip = sys_data.get('cip', 0)
            if isinstance(cip, str) and cip.startswith('0x'):
                cip = int(cip, 16)
            elif isinstance(cip, str):
                cip = int(cip.strip('"'), 16) if cip.strip('"').startswith('0x') else int(cip)
            if cip:
                # Convert to IP address
                sys_info['current_ip'] = f"{(cip >> 24) & 0xFF}.{(cip >> 16) & 0xFF}.{(cip >> 8) & 0xFF}.{cip & 0xFF}"
            
            # Management IP
            ip = sys_data.get('ip', 0)
            if isinstance(ip, str) and ip.startswith('0x'):
                ip = int(ip, 16)
            elif isinstance(ip, str):
                ip = int(ip.strip('"'), 16) if ip.strip('"').startswith('0x') else int(ip)
            if ip:
                sys_info['management_ip'] = f"{(ip >> 24) & 0xFF}.{(ip >> 16) & 0xFF}.{(ip >> 8) & 0xFF}.{ip & 0xFF}"
            
            # MAC Address
            mac = sys_data.get('mac', '')
            if mac:
                formatted_mac = ':'.join([mac[i:i+2] for i in range(0, len(mac), 2)])
                sys_info['mac_address'] = formatted_mac.upper()
            
            # Router MAC
            rmac = sys_data.get('rmac', '')
            if rmac:
                formatted_rmac = ':'.join([rmac[i:i+2] for i in range(0, len(rmac), 2)])
                sys_info['router_mac'] = formatted_rmac.upper()
            
            # Decode hex-encoded strings
            hex_fields = {
                'brd': 'board_model',
                'sid': 'serial_id', 
                'id': 'device_id',
                'ver': 'version',
                'rev': 'revision'
            }
            
            for field, name in hex_fields.items():
                value = sys_data.get(field, '')
                if value:
                    sys_info[name] = value
            
            # Build timestamp
            bld = sys_data.get('bld', 0)
            if isinstance(bld, str) and bld.startswith('0x'):
                bld = int(bld, 16)
            elif isinstance(bld, str):
                bld = int(bld.strip('"'), 16) if bld.strip('"').startswith('0x') else int(bld)
            if bld:
                import datetime
                sys_info['build_timestamp'] = bld
                sys_info['build_date'] = datetime.datetime.fromtimestamp(bld).strftime('%Y-%m-%d %H:%M:%S')
            
            # Temperature
            temp = sys_data.get('temp', 0)
            if isinstance(temp, str) and temp.startswith('0x'):
                temp = int(temp, 16)
            elif isinstance(temp, str):
                temp = int(temp.strip('"'), 16) if temp.strip('"').startswith('0x') else int(temp)
            sys_info['temperature_c'] = temp
            
            # Boolean flags
            bool_fields = {
                'wdt': 'watchdog_enabled',
                'dsc': 'discovery_enabled', 
                'mgmt': 'management_enabled',
                'igmp': 'igmp_enabled',
                'poe': 'poe_enabled',
                'upgr': 'upgrade_mode',
                'ainf': 'auto_info_enabled'
            }
            
            for field, name in bool_fields.items():
                value = sys_data.get(field, 0)
                if isinstance(value, str) and value.startswith('0x'):
                    value = int(value, 16)
                elif isinstance(value, str):
                    value = int(value.strip('"'), 16) if value.strip('"').startswith('0x') else int(value)
                sys_info[name] = bool(value)
            
            # Numeric fields
            numeric_fields = {
                'pdsc': 'port_discovery_mask',
                'allp': 'all_ports_mask',
                'prio': 'priority',
                'rpr': 'rapid_spanning_tree',
                'cost': 'path_cost'
            }
            
            for field, name in numeric_fields.items():
                value = sys_data.get(field, 0)
                if isinstance(value, str) and value.startswith('0x'):
                    value = int(value, 16)
                elif isinstance(value, str):
                    value = int(value.strip('"'), 16) if value.strip('"').startswith('0x') else int(value)
                sys_info[name] = value
            
            # Power supply info
            power_fields = ['p1v', 'p2v', 'p1c', 'p2c', 'p1s', 'p2s']
            for field in power_fields:
                value = sys_data.get(field, 0)
                if isinstance(value, str) and value.startswith('0x'):
                    value = int(value, 16)
                elif isinstance(value, str):
                    value = int(value.strip('"'), 16) if value.strip('"').startswith('0x') else int(value)
                sys_info[field] = value
            
            # Fan info
            fan_fields = ['fan1', 'fan2', 'fan3', 'fan4']
            for field in fan_fields:
                value = sys_data.get(field, 0)
                if isinstance(value, str) and value.startswith('0x'):
                    value = int(value, 16)
                elif isinstance(value, str):
                    value = int(value.strip('"'), 16) if value.strip('"').startswith('0x') else int(value)
                sys_info[field] = value
            
            logger.info(f"Parsed system info for device {sys_info.get('device_id', 'unknown')}")
            
        except Exception as e:
            logger.error(f"Error parsing system info: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def parse_link_metrics(self, link_data: Dict) -> Dict[str, Any]:
        """Parse link status data to extract port metrics"""
        metrics = {
            'ports': {'total': 0, 'enabled': 0, 'linked': 0},
            'port_details': []
        }
        
        try:
            # Get enabled ports bitmask
            en_mask = int(link_data.get('en', '0x0'), 16)
            
            # Get link status bitmask
            lnk_mask = int(link_data.get('lnk', '0x0'), 16)
            
            # Get port names (hex encoded)
            port_names = link_data.get('nm', [])
            
            # Get port speeds
            port_speeds = link_data.get('spd', [])
            
            # Total ports from the `prt` field (CRS-style switches). CSS-style
            # switches omit `prt`, so fall back to the number of port names.
            prt = link_data.get('prt')
            if prt is not None:
                total_ports = int(prt, 16) if isinstance(prt, str) else int(prt)
            else:
                total_ports = len(port_names)
            metrics['ports']['total'] = total_ports
            
            # Process each port
            for i in range(min(total_ports, len(port_names))):
                port_enabled = bool(en_mask & (1 << i))
                port_linked = bool(lnk_mask & (1 << i))
                
                # Decode port name from hex
                port_name = port_names[i] if i < len(port_names) else f"Port{i+1}"
                try:
                    port_name = bytes.fromhex(port_name).decode('ascii', errors='ignore')
                except:
                    pass
                
                # Get port speed
                speed = port_speeds[i] if i < len(port_speeds) else 0
                # Convert hex string to int if needed
                if isinstance(speed, str) and speed.startswith('"0x'):
                    speed = int(speed.strip('"'), 16)
                elif isinstance(speed, str) and speed.startswith('0x'):
                    speed = int(speed, 16)
                    
                speed_map = {0: 0, 1: 10, 2: 100, 3: 1000, 7: 0}  # 7 = auto/unknown
                speed_mbps = speed_map.get(speed, 0)
                
                if port_enabled:
                    metrics['ports']['enabled'] += 1
                    if port_linked:
                        metrics['ports']['linked'] += 1
                
                metrics['port_details'].append({
                    'index': i + 1,
                    'name': port_name,
                    'enabled': port_enabled,
                    'linked': port_linked,
                    'speed_mbps': speed_mbps
                })
            
            logger.info(f"Parsed link metrics: {metrics['ports']}")
            
        except Exception as e:
            logger.error(f"Error parsing link data: {e}")
            import traceback
            traceback.print_exc()
        
        return metrics
    
    def collect_metrics(self, device_ip: str, device_info: Dict[str, Any]) -> Dict[str, Any]:
        """Collect all metrics from a device"""
        # Credentials are resolved per-device by the config loader
        self.active_username = device_info.get('user', '')
        self.active_password = device_info.get('password', '')

        metrics = {
            'device_name': device_info.get('name', 'Unknown'),
            'device_ip': device_ip,
            'device_model': device_info.get('device_model', 'Unknown'),
            'manufacturer': device_info.get('manufacturer', 'Unknown'),
            'up': 0,
            'collection_time': time.time()
        }
        
        # Get link status - this also tests authentication
        link_data = self.get_link_status(device_ip)
        if link_data:
            metrics['up'] = 1
            link_metrics = self.parse_link_metrics(link_data)
            metrics.update(link_metrics)
            
            # Get SFP status
            sfp_data = self.get_sfp_status(device_ip)
            if sfp_data:
                sfp_metrics = self.parse_sfp_metrics(sfp_data)
                metrics.update(sfp_metrics)
            
            # Get port statistics
            stats_data = self.get_port_stats(device_ip)
            if stats_data and 'port_details' in link_metrics:
                stats_metrics = self.parse_port_stats(stats_data, link_metrics['port_details'])
                metrics.update(stats_metrics)
            
            # Get VLAN configuration
            vlan_data = self.get_vlan_config(device_ip)
            if vlan_data and 'port_details' in link_metrics:
                vlan_metrics = self.parse_vlan_config(vlan_data, link_metrics['port_details'])
                metrics.update(vlan_metrics)
            
            # Get VLAN table
            vlan_table = self.get_vlan_table(device_ip)
            if vlan_table:
                vlan_table_metrics = self.parse_vlan_table(vlan_table)
                metrics.update(vlan_table_metrics)
            
            # Get MAC address table
            mac_table = self.get_mac_table(device_ip)
            if mac_table:
                mac_table_metrics = self.parse_mac_table(mac_table)
                metrics.update(mac_table_metrics)
            
            # Get system information
            sys_data = self.get_system_info(device_ip)
            if sys_data:
                sys_metrics = self.parse_system_info(sys_data)
                metrics.update(sys_metrics)
        else:
            logger.error(f"Cannot connect to {device_info.get('name', 'Unknown')} ({device_ip})")

        # Clear active credentials after polling this device
        self.active_username = ''
        self.active_password = ''

        return metrics


if __name__ == "__main__":
    # Test the SwitchOS client with devices from the config file
    from device_config import DeviceConfigClient

    # Get devices from the config file
    device_client = DeviceConfigClient()
    devices = device_client.fetch_devices()

    if not devices:
        print("No devices found in config file")
        exit(1)
    
    # Test SwitchOS connection
    switchos = SwitchOSClient()
    
    for device in devices:
        print(f"\nTesting device: {device['name']} ({device['ip']})")
        metrics = switchos.collect_metrics(device['ip'], device)
        
        print(f"Device up: {'Yes' if metrics['up'] else 'No'}")
        if metrics['up']:
            if 'ports' in metrics:
                ports = metrics['ports']
                print(f"Ports: {ports.get('total', 0)} total, {ports.get('enabled', 0)} enabled, {ports.get('linked', 0)} linked")
            
            if 'port_details' in metrics:
                print("\nPort Details:")
                for port in metrics['port_details'][:5]:  # Show first 5 ports
                    status = []
                    if port['enabled']:
                        status.append('enabled')
                    if port['linked']:
                        status.append(f"linked@{port['speed_mbps']}Mbps")
                    status_str = ', '.join(status) if status else 'disabled'
                    print(f"  - {port['name']}: {status_str}")
                if len(metrics['port_details']) > 5:
                    print(f"  ... and {len(metrics['port_details']) - 5} more ports")
            
            if 'sfp_modules' in metrics and metrics['sfp_modules']:
                print("\nSFP Modules:")
                for sfp in metrics['sfp_modules']:
                    print(f"  - SFP{sfp['index']}: {sfp['vendor']} {sfp['part_number']}")
                    print(f"    Serial: {sfp['serial']}")
                    print(f"    Type: {sfp['type']}")
                    if 'temperature_c' in sfp:
                        print(f"    Temp: {sfp['temperature_c']:.1f}°C, Voltage: {sfp['voltage_v']:.2f}V")
                        print(f"    TX Power: {sfp['tx_power_mw']:.2f}mW, RX Power: {sfp['rx_power_mw']:.2f}mW")
            
            if 'port_stats' in metrics and metrics['port_stats']:
                print("\nPort Statistics (showing active ports):")
                active_ports = [p for p in metrics['port_stats'] 
                              if p.get('rx_total_packets', 0) > 0 or p.get('tx_total_packets', 0) > 0]
                
                for port in active_ports[:5]:  # Show first 5 active ports
                    rx_mb = port.get('rx_bytes_total', 0) / (1024 * 1024)
                    tx_mb = port.get('tx_bytes_total', 0) / (1024 * 1024)
                    print(f"  - {port['port_name']}:")
                    print(f"    RX: {rx_mb:.2f} MB ({port.get('rx_total_packets', 0):,} packets)")
                    print(f"    TX: {tx_mb:.2f} MB ({port.get('tx_total_packets', 0):,} packets)")
                    if port.get('rx_errors', 0) > 0 or port.get('tx_errors', 0) > 0:
                        print(f"    Errors: RX={port.get('rx_errors', 0)}, TX={port.get('tx_errors', 0)}")
                
                if len(active_ports) > 5:
                    print(f"  ... and {len(active_ports) - 5} more active ports")
            
            if 'vlan_config' in metrics and metrics['vlan_config']:
                print("\nVLAN Configuration (showing first 5 ports):")
                for vlan_cfg in metrics['vlan_config'][:5]:
                    print(f"  - {vlan_cfg['port_name']}:")
                    if 'vlan_mode' in vlan_cfg:
                        print(f"    Mode: {vlan_cfg['vlan_mode']}")
                    if 'vlan_ingress' in vlan_cfg:
                        print(f"    Ingress: {vlan_cfg['vlan_ingress']}")
                    if 'default_vlan_id' in vlan_cfg:
                        print(f"    Default VLAN: {vlan_cfg['default_vlan_id']}")
                    if 'stp_state' in vlan_cfg:
                        print(f"    STP State: {vlan_cfg['stp_state']}")
                
                if len(metrics['vlan_config']) > 5:
                    print(f"  ... and {len(metrics['vlan_config']) - 5} more ports")
                
                if 'configured_vlans' in metrics and metrics['configured_vlans']:
                    print(f"\nConfigured VLANs: {sorted(metrics['configured_vlans'])}")
            
            if 'vlan_table' in metrics and metrics['vlan_table']:
                print(f"\nVLAN Table ({metrics.get('total_vlans', 0)} VLANs):")
                for vlan in metrics['vlan_table']:
                    features = []
                    if vlan['port_isolation']:
                        features.append('isolation')
                    if vlan['learning_enabled']:
                        features.append('learning')
                    if vlan['mirror_enabled']:
                        features.append('mirror')
                    if vlan['igmp_snooping']:
                        features.append('igmp')
                    
                    feature_str = f" ({', '.join(features)})" if features else ""
                    print(f"  - VLAN {vlan['vlan_id']}: {vlan['member_count']} ports{feature_str}")
                    if vlan['member_ports']:
                        port_ranges = []
                        start = vlan['member_ports'][0]
                        end = start
                        
                        for port in vlan['member_ports'][1:] + [None]:
                            if port == end + 1:
                                end = port
                            else:
                                if start == end:
                                    port_ranges.append(str(start))
                                else:
                                    port_ranges.append(f"{start}-{end}")
                                if port:
                                    start = end = port
                        
                        print(f"    Members: {', '.join(port_ranges)}")
                
                print(f"\nVLAN Summary: {metrics.get('vlans_with_learning', 0)} with learning, "
                      f"{metrics.get('vlans_with_isolation', 0)} with isolation, "
                      f"{metrics.get('vlans_with_igmp', 0)} with IGMP")
            
            if 'mac_stats' in metrics and metrics['mac_stats']:
                stats = metrics['mac_stats']
                print(f"\nMAC Address Table ({stats['total_entries']} entries):")
                
                # Show top ports by MAC count
                if stats['entries_by_port']:
                    top_ports = sorted(stats['entries_by_port'].items(), key=lambda x: x[1], reverse=True)[:5]
                    print("  Top ports by MAC count:")
                    for port, count in top_ports:
                        print(f"    Port {port}: {count} MACs")
                
                # Show VLANs
                if stats['entries_by_vlan']:
                    vlan_counts = sorted(stats['entries_by_vlan'].items())
                    print(f"  By VLAN: {', '.join([f'VLAN {v}({c})' for v, c in vlan_counts])}")
                
                # Show vendors
                if stats['entries_by_vendor']:
                    vendor_counts = sorted(stats['entries_by_vendor'].items(), key=lambda x: x[1], reverse=True)
                    print(f"  By vendor: {', '.join([f'{v}({c})' for v, c in vendor_counts])}")
                
                # Show sample MACs
                if 'mac_table' in metrics and metrics['mac_table']:
                    print("\n  Sample entries:")
                    for mac in metrics['mac_table'][:3]:
                        print(f"    {mac['mac_address']} → Port {mac['port']} (VLAN {mac['vlan_id']}, {mac.get('vendor', 'Unknown')})")
            
            if 'system_info' in metrics and metrics['system_info']:
                sys_info = metrics['system_info']
                print(f"\nSystem Information:")
                if 'device_id' in sys_info:
                    print(f"  Device: {sys_info['device_id']}")
                if 'board_model' in sys_info:
                    print(f"  Model: {sys_info['board_model']}")
                if 'version' in sys_info:
                    print(f"  Version: {sys_info['version']}")
                if 'serial_id' in sys_info:
                    print(f"  Serial: {sys_info['serial_id']}")
                if 'mac_address' in sys_info:
                    print(f"  MAC: {sys_info['mac_address']}")
                if 'management_ip' in sys_info:
                    print(f"  Management IP: {sys_info['management_ip']}")
                if 'uptime_days' in sys_info:
                    print(f"  Uptime: {sys_info['uptime_days']} days")
                if 'temperature_c' in sys_info:
                    print(f"  Temperature: {sys_info['temperature_c']}°C")
                if 'build_date' in sys_info:
                    print(f"  Build: {sys_info['build_date']}")
                
                # Show enabled features
                features = []
                if sys_info.get('watchdog_enabled'):
                    features.append('watchdog')
                if sys_info.get('discovery_enabled'):
                    features.append('discovery') 
                if sys_info.get('management_enabled'):
                    features.append('management')
                if sys_info.get('igmp_enabled'):
                    features.append('igmp')
                if sys_info.get('poe_enabled'):
                    features.append('poe')
                
                if features:
                    print(f"  Features: {', '.join(features)}")