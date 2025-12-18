#!/usr/bin/env python3
"""
Kea DHCP Hook Script for Bare-Metal Discovery

Triggered by Kea DHCP lease4_commit hook when a BMC receives a DHCP lease.
Generates an Ansible inventory file with the leased IP address for discovery automation.

Location: python/src/baremetal/kea_lease_hook.py
Deployment: See docs/KEA.md for Kea DHCP server configuration

Environment Variables:
    KEA_HOOK_OUTPUT_DIR: Directory for generated inventory files (default: /var/lib/kea/discovery)
    KEA_HOOK_SUBNET_FILTER: Comma-separated list of subnets to process (optional)
    KEA_HOOK_LOG_LEVEL: Logging level (default: INFO)

Kea Hook Parameters (passed via environment):
    KEA_LEASE4_ADDRESS: IPv4 address leased
    KEA_LEASE4_HWADDR: Hardware (MAC) address
    KEA_SUBNET4: Subnet ID
    KEA_LEASE4_HOSTNAME: Client hostname (if provided)

Output:
    YAML file: {output_dir}/bmc-{ip_address}.yml
    Format: Ansible inventory with bmc_targets list
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging for the hook script."""
    logger = logging.getLogger("kea_lease_hook")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "[%(levelname)s] %(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def validate_ip_address(ip: str) -> bool:
    """Validate IPv4 address format."""
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    
    try:
        return all(0 <= int(part) <= 255 for part in parts)
    except (ValueError, TypeError):
        return False


def should_process_subnet(subnet_id: str, filter_list: Optional[str]) -> bool:
    """
    Check if subnet should be processed based on filter.
    
    Args:
        subnet_id: Kea subnet identifier
        filter_list: Comma-separated list of subnet IDs to process (None = all)
    
    Returns:
        True if subnet should be processed
    """
    if not filter_list:
        return True
    
    allowed_subnets = [s.strip() for s in filter_list.split(',')]
    return subnet_id in allowed_subnets


def generate_inventory_yaml(ip_address: str, mac_address: str, hostname: Optional[str] = None) -> Dict:
    """
    Generate Ansible inventory structure for discovery.
    
    Args:
        ip_address: BMC IPv4 address
        mac_address: BMC MAC address
        hostname: Optional BMC hostname
    
    Returns:
        Dictionary representing Ansible inventory structure
    """
    inventory = {
        'bmc_targets': [
            {'ip': ip_address}
        ],
        'metadata': {
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'source': 'kea_dhcp_hook',
            'lease_info': {
                'ip': ip_address,
                'mac': mac_address,
            }
        }
    }
    
    if hostname:
        inventory['metadata']['lease_info']['hostname'] = hostname
    
    return inventory


def write_inventory_file(output_dir: Path, ip_address: str, inventory_data: Dict, logger: logging.Logger) -> Path:
    """
    Write inventory data to YAML file.
    
    Args:
        output_dir: Directory to write file
        ip_address: BMC IP address (used in filename)
        inventory_data: Inventory dictionary to write
        logger: Logger instance
    
    Returns:
        Path to written file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Sanitize IP for filename
    safe_ip = ip_address.replace('.', '-')
    output_file = output_dir / f"{safe_ip}-bmc.yml"
    
    try:
        with open(output_file, 'w') as f:
            yaml.dump(inventory_data, f, default_flow_style=False, sort_keys=False)
        
        logger.info(f"Generated inventory file: {output_file}")
        return output_file
    
    except Exception as e:
        logger.error(f"Failed to write inventory file {output_file}: {e}")
        raise


def main():
    """Main entry point for Kea DHCP hook."""
    parser = argparse.ArgumentParser(
        description="Kea DHCP hook for bare-metal BMC discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Called by Kea with environment variables
  KEA_LEASE4_ADDRESS=172.30.19.42 KEA_LEASE4_HWADDR=00:11:22:33:44:55 ./kea_lease_hook.py
  
  # Manual invocation for testing
  ./kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55
  
  # Specify custom output directory
  ./kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55 --output-dir /tmp/kea-test
        """
    )
    
    parser.add_argument(
        '--ip',
        help='BMC IP address (overrides KEA_LEASE4_ADDRESS environment variable)'
    )
    parser.add_argument(
        '--mac',
        help='BMC MAC address (overrides KEA_LEASE4_HWADDR environment variable)'
    )
    parser.add_argument(
        '--hostname',
        help='BMC hostname (overrides KEA_LEASE4_HOSTNAME environment variable)'
    )
    parser.add_argument(
        '--subnet',
        help='Subnet ID (overrides KEA_SUBNET4 environment variable)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        help='Output directory for inventory files (overrides KEA_HOOK_OUTPUT_DIR)'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    log_level = os.getenv('KEA_HOOK_LOG_LEVEL', args.log_level)
    logger = setup_logging(log_level)
    
    # Get parameters from args or environment
    ip_address = args.ip or os.getenv('KEA_LEASE4_ADDRESS')
    mac_address = args.mac or os.getenv('KEA_LEASE4_HWADDR')
    hostname = args.hostname or os.getenv('KEA_LEASE4_HOSTNAME')
    subnet_id = args.subnet or os.getenv('KEA_SUBNET4')
    
    output_dir = args.output_dir or Path(os.getenv('KEA_HOOK_OUTPUT_DIR', '/var/lib/kea/discovery'))
    subnet_filter = os.getenv('KEA_HOOK_SUBNET_FILTER')
    
    # Validate required parameters
    if not ip_address:
        logger.error("No IP address provided (set --ip or KEA_LEASE4_ADDRESS)")
        return 1
    
    if not mac_address:
        logger.error("No MAC address provided (set --mac or KEA_LEASE4_HWADDR)")
        return 1
    
    if not validate_ip_address(ip_address):
        logger.error(f"Invalid IP address format: {ip_address}")
        return 1
    
    # Check subnet filter
    if subnet_id and not should_process_subnet(subnet_id, subnet_filter):
        logger.info(f"Subnet {subnet_id} not in filter list, skipping")
        return 0
    
    logger.info(f"Processing DHCP lease: IP={ip_address}, MAC={mac_address}, Subnet={subnet_id}")
    
    try:
        # Generate inventory structure
        inventory_data = generate_inventory_yaml(ip_address, mac_address, hostname)
        
        # Write inventory file
        output_file = write_inventory_file(output_dir, ip_address, inventory_data, logger)
        
        logger.info(f"[OK] Successfully generated inventory for {ip_address}")
        logger.debug(f"Inventory data: {json.dumps(inventory_data, indent=2)}")
        
        return 0
    
    except Exception as e:
        logger.error(f"[ERROR] Failed to process lease: {e}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
