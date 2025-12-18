#!/usr/bin/env python3
"""
BMC DNS Inventory Reporter - Test/Experimental Version

Safe testing environment for new features without affecting production code.
Copy of bmc_dns_watcher.py for experimentation.

Location: python/src/baremetal/bmc_dns_watcher_test.py
"""

import os
import sys
import time
import logging
import argparse
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime, timezone
from collections import defaultdict

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install with: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import urllib.request
    import json
except ImportError:
    pass  # Optional for online lookup


# IEEE OUI Database URL (updated regularly by IEEE)
IEEE_OUI_URL = "https://standards-oui.ieee.org/oui/oui.json"

# Local OUI cache file
OUI_CACHE_FILE = Path("/var/lib/kea/discovery/oui_cache.json")

# Embedded OUI Database for common server manufacturers (fallback)
# Source: IEEE Registration Authority https://standards-oui.ieee.org/
# Last updated: 2025-12-08
EMBEDDED_OUI_DATABASE = {
    # Dell Inc. - Multiple OUIs (iDRAC, server NICs)
    'd067e5': 'Dell Inc.',
    '1866da': 'Dell Inc.',
    'f01faf': 'Dell Inc.',
    '34e6d7': 'Dell Inc.',
    '78045e': 'Dell Inc.',
    '00a04b': 'Dell Inc.',
    '001e4f': 'Dell Inc.',
    '002564': 'Dell Inc.',
    '00b0d0': 'Dell Inc.',
    '00c04f': 'Dell Inc.',
    '00d03d': 'Dell Inc.',
    '001c23': 'Dell Inc.',
    '1c40d0': 'Dell Inc.',
    '001dd8': 'Dell Inc.',
    'f0d4e2': 'Dell Inc.',  # iDRAC - seen in production
    'd4cbed': 'Dell Inc.',
    
    # Hewlett Packard Enterprise / HP Inc. (iLO, server NICs)
    '1402ec': 'Hewlett Packard Enterprise',
    '9457a5': 'Hewlett Packard Enterprise',
    '480fcf': 'Hewlett Packard Enterprise',
    '8cdc02': 'Hewlett Packard Enterprise',
    '705a0f': 'Hewlett Packard Enterprise',
    '001438': 'Hewlett Packard',
    '001e0b': 'Hewlett Packard',
    '002655': 'Hewlett Packard',
    '0030c1': 'Hewlett Packard',
    '003048': 'Hewlett Packard',
    '00188b': 'Hewlett Packard',
    '00215a': 'Hewlett Packard',
    'e839df': 'Hewlett Packard Enterprise',
    '846902': 'Hewlett Packard Enterprise',
    '7ca62a': 'Hewlett Packard Enterprise',  # iLO - seen in production
    
    # Super Micro Computer Inc.
    '002590': 'Super Micro Computer Inc.',
    'ac1f6b': 'Super Micro Computer Inc.',
    '3cecef': 'Super Micro Computer Inc.',
    '0025907': 'Super Micro Computer Inc.',
    
    # VMware / Cisco Systems
    '005056': 'VMware Inc.',  # VMware virtual adapters
    '001bd4': 'Cisco Systems Inc.',
    '0050f2': 'Cisco Systems Inc.',
    '0009b7': 'Cisco Systems Inc.',
    
    # Lenovo (ThinkSystem servers)
    '00505b': 'Lenovo',
    '1c69a5': 'Lenovo',
    'a0369f': 'Lenovo',
    
    # IBM
    '000255': 'IBM Corp.',
    '000ae8': 'IBM Corp.',
    
    # Intel Corporation (NUC, server NICs)
    '000000': 'Intel Corporation',
}

# OUI manufacturer normalization for consistency
# Maps various naming conventions to standard manufacturer names
OUI_NORMALIZE_MAP = {
    'dell inc.': 'Dell',
    'dell': 'Dell',
    'hewlett packard enterprise': 'HP',
    'hewlett packard': 'HP',
    'hp': 'HP',
    'hpe': 'HP',
    'super micro computer inc.': 'Supermicro',
    'supermicro': 'Supermicro',
    'vmware inc.': 'VMware',
    'vmware': 'VMware',
    'cisco systems inc.': 'Cisco',
    'cisco': 'Cisco',
    'lenovo': 'Lenovo',
    'ibm corp.': 'IBM',
    'ibm': 'IBM',
    'intel corporation': 'Intel',
    'intel': 'Intel',
}


class OUIDatabase:
    """
    OUI (Organizationally Unique Identifier) database for MAC address manufacturer lookup.
    
    Provides three-tier lookup strategy:
    1. In-memory cache (fast)
    2. Local file cache (medium)
    3. Online IEEE database (slow, requires internet)
    """
    
    def __init__(self, cache_file: Optional[Path] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize OUI database.
        
        Args:
            cache_file: Path to local cache file (default: /var/lib/kea/discovery/oui_cache.json)
            logger: Logger instance for diagnostics
        """
        self.cache_file = cache_file or OUI_CACHE_FILE
        self.logger = logger or logging.getLogger(__name__)
        self.oui_map: Dict[str, str] = {}
        
        # Load embedded database as baseline
        self.oui_map.update(EMBEDDED_OUI_DATABASE)
        self.logger.debug(f"Loaded {len(EMBEDDED_OUI_DATABASE)} embedded OUI entries")
        
        # Try to load from local cache
        self._load_from_cache()
    
    def _load_from_cache(self):
        """Load OUI database from local cache file."""
        if not self.cache_file.exists():
            self.logger.debug(f"OUI cache file not found: {self.cache_file}")
            return
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            if isinstance(cache_data, dict) and 'oui_map' in cache_data:
                loaded_count = len(cache_data['oui_map'])
                self.oui_map.update(cache_data['oui_map'])
                self.logger.debug(f"Loaded {loaded_count} OUI entries from cache")
                
                # Log cache metadata if available
                if 'updated' in cache_data:
                    self.logger.debug(f"Cache last updated: {cache_data['updated']}")
        
        except (json.JSONDecodeError, OSError, PermissionError) as e:
            self.logger.warning(f"Failed to load OUI cache: {e}")
    
    def _save_to_cache(self):
        """Save current OUI database to local cache file."""
        try:
            # Ensure cache directory exists
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            
            cache_data = {
                'oui_map': self.oui_map,
                'updated': datetime.now(timezone.utc).isoformat(),
                'source': 'IEEE OUI Database',
                'count': len(self.oui_map)
            }
            
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2)
            
            self.logger.info(f"Saved {len(self.oui_map)} OUI entries to cache")
        
        except (OSError, PermissionError) as e:
            self.logger.warning(f"Failed to save OUI cache: {e}")
    
    def update_from_ieee(self, timeout: int = 10) -> bool:
        """
        Update OUI database from IEEE online registry.
        
        Args:
            timeout: HTTP request timeout in seconds
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            self.logger.info(f"Updating OUI database from IEEE: {IEEE_OUI_URL}")
            
            req = urllib.request.Request(
                IEEE_OUI_URL,
                headers={'User-Agent': 'BMC-Discovery-Tool/1.0'}
            )
            
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            if not isinstance(data, list):
                self.logger.error("Invalid IEEE OUI data format")
                return False
            
            # Parse IEEE OUI data
            new_entries = 0
            for entry in data:
                if 'oui' in entry and 'organization' in entry:
                    oui = entry['oui'].replace(':', '').replace('-', '').lower()[:6]
                    org = entry['organization'].strip()
                    
                    if oui and org:
                        self.oui_map[oui] = org
                        new_entries += 1
            
            self.logger.info(f"Updated OUI database: {new_entries} total entries")
            
            # Save to cache
            self._save_to_cache()
            
            return True
        
        except Exception as e:
            self.logger.warning(f"Failed to update OUI database from IEEE: {e}")
            return False
    
    def lookup(self, mac_address: str) -> str:
        """
        Look up manufacturer from MAC address.
        
        Args:
            mac_address: MAC address in any format (XX:XX:XX:XX:XX:XX, XX-XX-XX-XX-XX-XX, etc.)
            
        Returns:
            Normalized manufacturer name or 'Unknown'
        """
        if not mac_address:
            return 'Unknown'
        
        # Normalize MAC address (remove separators, lowercase, first 6 chars)
        oui = mac_address.replace(':', '').replace('-', '').replace('.', '').lower()[:6]
        
        if not oui or len(oui) < 6:
            return 'Unknown'
        
        # Lookup in database
        manufacturer = self.oui_map.get(oui)
        
        if not manufacturer:
            return 'Unknown'
        
        # Normalize manufacturer name
        normalized = OUI_NORMALIZE_MAP.get(manufacturer.lower(), manufacturer)
        
        return normalized
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get OUI database statistics.
        
        Returns:
            Dictionary with database statistics
        """
        return {
            'total_entries': len(self.oui_map),
            'embedded_entries': len(EMBEDDED_OUI_DATABASE),
            'cache_file_exists': self.cache_file.exists()
        }


def detect_manufacturer_from_mac(mac_address: str, oui_db: Optional[OUIDatabase] = None) -> str:
    """
    Detect server manufacturer from MAC address OUI (first 3 octets).
    
    This is a convenience wrapper around OUIDatabase.lookup() for backward compatibility.
    For production use, create an OUIDatabase instance and reuse it.
    
    Args:
        mac_address: MAC address in format XX:XX:XX:XX:XX:XX or XX-XX-XX-XX-XX-XX
        oui_db: Optional OUIDatabase instance (creates temporary one if not provided)
        
    Returns:
        Manufacturer name or 'Unknown'
        
    References:
        - IEEE Registration Authority: https://standards-oui.ieee.org/
        - OUI Lookup Tool: https://www.wireshark.org/tools/oui-lookup.html
        - MAC Address Vendors: https://macaddress.io/
    """
    if oui_db is None:
        # Create temporary database with embedded entries only
        oui_db = OUIDatabase()
    
    return oui_db.lookup(mac_address)


class InventoryWatcher:
    """Watches discovery inventory files for changes and reports new hostnames."""
    
    # Hostname validation pattern: {site}-cab{num}-ru{##} or ru{##-##}-{bmc_type}
    # Supports single RU with zero-padding (ru01, ru17) or range (ru17-18)
    HOSTNAME_PATTERN = re.compile(r'^(us[1-4]|dv)-cab(\d+)-ru(\d{2}(?:-\d{2})?)-(\w+)$', re.IGNORECASE)
    
    # Valid site codes
    VALID_SITES = {'us1', 'us2', 'us3', 'us4', 'dv'}
    
    # Valid BMC types
    VALID_BMC_TYPES = {'idrac', 'ilo', 'bmc'}
    
    def __init__(self, watch_dir: Path, logger: logging.Logger, strict_validation: bool = True):
        """
        Initialize inventory file watcher.
        
        Args:
            watch_dir: Directory containing discovery YAML files
            logger: Logger instance
            strict_validation: Enable strict hostname validation (default: True)
        """
        self.watch_dir = watch_dir
        self.logger = logger
        self.strict_validation = strict_validation
        
        # Track reported hostnames to avoid duplicate reporting
        self.reported_hostnames: Set[str] = set()
        
        # Track hostname -> IP mappings to detect conflicts
        self.hostname_to_ip: Dict[str, str] = {}
        
        # Track IP -> hostname mappings to detect conflicts
        self.ip_to_hostname: Dict[str, str] = {}
        
        # Track file modification times
        self.file_mtimes: Dict[Path, float] = {}
        
        # Validation statistics
        self.validation_stats = {
            'total_processed': 0,
            'valid': 0,
            'invalid_format': 0,
            'invalid_site': 0,
            'invalid_bmc_type': 0,
            'duplicate_hostname': 0,
            'duplicate_ip': 0,
            'ip_conflict': 0
        }
    
    def scan_inventory_files(self) -> List[Path]:
        """
        Scan watch directory for discovery inventory files.
        
        Returns:
            List of YAML file paths matching *-discovery.yml pattern
        """
        try:
            if not self.watch_dir.exists():
                self.logger.warning(f"Watch directory does not exist: {self.watch_dir}")
                return []
            
            if not self.watch_dir.is_dir():
                self.logger.error(f"Watch path is not a directory: {self.watch_dir}")
                return []
            
            # Check read permissions
            if not os.access(self.watch_dir, os.R_OK):
                self.logger.error(f"No read permission for directory: {self.watch_dir}")
                return []
            
            files = list(self.watch_dir.glob("*-discovery.yml"))
            self.logger.debug(f"Found {len(files)} inventory file(s) in {self.watch_dir}")
            return files
        
        except PermissionError as e:
            self.logger.error(f"Permission denied accessing directory {self.watch_dir}: {e}")
            return []
        except OSError as e:
            self.logger.error(f"OS error scanning directory {self.watch_dir}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error scanning directory {self.watch_dir}: {e}")
            return []
    
    def get_modified_files(self, inventory_files: List[Path]) -> List[Path]:
        """
        Identify files that have been created or modified since last check.
        
        Args:
            inventory_files: List of inventory file paths
            
        Returns:
            List of modified file paths
        """
        modified = []
        
        for file_path in inventory_files:
            try:
                if not file_path.exists():
                    self.logger.warning(f"File no longer exists: {file_path}")
                    # Remove from tracking if deleted
                    self.file_mtimes.pop(file_path, None)
                    continue
                
                if not file_path.is_file():
                    self.logger.warning(f"Path is not a file: {file_path}")
                    continue
                
                if not os.access(file_path, os.R_OK):
                    self.logger.warning(f"No read permission for file: {file_path}")
                    continue
                
                current_mtime = file_path.stat().st_mtime
                
                if file_path not in self.file_mtimes or self.file_mtimes[file_path] < current_mtime:
                    modified.append(file_path)
                    self.file_mtimes[file_path] = current_mtime
            
            except PermissionError as e:
                self.logger.warning(f"Permission denied for {file_path.name}: {e}")
            except OSError as e:
                self.logger.warning(f"OS error checking {file_path.name}: {e}")
            except Exception as e:
                self.logger.warning(f"Unexpected error checking {file_path.name}: {e}")
        
        return modified
    
    def validate_hostname(self, hostname: str) -> Tuple[bool, Optional[str]]:
        """
        Validate hostname against naming convention.
        
        Args:
            hostname: Hostname to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not hostname:
            return False, "Empty hostname"
        
        # Check pattern match
        match = self.HOSTNAME_PATTERN.match(hostname.lower())
        if not match:
            self.validation_stats['invalid_format'] += 1
            return False, f"Hostname format invalid: expected {{site}}-cab{{num}}-ru{{##}} or ru{{##-##}}-{{bmc_type}} (RU must be zero-padded: ru01, ru17)"
        
        site, cabinet, rack_unit, bmc_type = match.groups()
        
        # Validate site code
        if site.lower() not in self.VALID_SITES:
            self.validation_stats['invalid_site'] += 1
            return False, f"Invalid site code: {site} (valid: {', '.join(sorted(self.VALID_SITES))})"
        
        # Validate rack unit range (if range format used)
        if '-' in rack_unit:
            try:
                start_ru, end_ru = map(int, rack_unit.split('-'))
                if start_ru >= end_ru:
                    self.validation_stats['invalid_format'] += 1
                    return False, f"Invalid rack unit range: ru{rack_unit} (start must be less than end)"
                if start_ru < 1 or end_ru > 48:
                    self.validation_stats['invalid_format'] += 1
                    return False, f"Invalid rack unit range: ru{rack_unit} (valid range: 01-48)"
            except ValueError:
                self.validation_stats['invalid_format'] += 1
                return False, f"Invalid rack unit format: ru{rack_unit}"
        else:
            # Validate single rack unit (already zero-padded by regex)
            try:
                ru_num = int(rack_unit)
                if ru_num < 1 or ru_num > 48:
                    self.validation_stats['invalid_format'] += 1
                    return False, f"Invalid rack unit: ru{rack_unit} (valid range: 01-48)"
            except ValueError:
                self.validation_stats['invalid_format'] += 1
                return False, f"Invalid rack unit format: ru{rack_unit}"
        
        # Validate BMC type
        if bmc_type.lower() not in self.VALID_BMC_TYPES:
            self.validation_stats['invalid_bmc_type'] += 1
            return False, f"Invalid BMC type: {bmc_type} (valid: {', '.join(sorted(self.VALID_BMC_TYPES))})"
        
        return True, None
    
    def validate_ip_address(self, ip_address: str) -> Tuple[bool, Optional[str]]:
        """
        Validate IP address format.
        
        Args:
            ip_address: IP address to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not ip_address:
            return False, "Empty IP address"
        
        # Basic IPv4 validation
        parts = ip_address.split('.')
        if len(parts) != 4:
            return False, f"Invalid IPv4 format: {ip_address}"
        
        try:
            for part in parts:
                num = int(part)
                if num < 0 or num > 255:
                    return False, f"Invalid IPv4 octet: {part} (must be 0-255)"
        except ValueError:
            return False, f"Invalid IPv4 format: {ip_address}"
        
        return True, None
    
    def check_uniqueness(self, hostname: str, ip_address: str) -> Tuple[bool, Optional[str]]:
        """
        Check for hostname and IP uniqueness conflicts.
        
        Args:
            hostname: Hostname to check
            ip_address: IP address to check
            
        Returns:
            Tuple of (is_unique, error_message)
        """
        # Check if hostname already reported with different IP
        if hostname in self.hostname_to_ip:
            existing_ip = self.hostname_to_ip[hostname]
            if existing_ip != ip_address:
                self.validation_stats['ip_conflict'] += 1
                return False, f"IP conflict: hostname '{hostname}' previously mapped to {existing_ip}, now {ip_address}"
            else:
                self.validation_stats['duplicate_hostname'] += 1
                return False, f"Duplicate: hostname '{hostname}' already processed"
        
        # Check if IP already reported with different hostname
        if ip_address in self.ip_to_hostname:
            existing_hostname = self.ip_to_hostname[ip_address]
            if existing_hostname != hostname:
                self.validation_stats['ip_conflict'] += 1
                return False, f"IP conflict: {ip_address} previously mapped to '{existing_hostname}', now '{hostname}'"
            else:
                self.validation_stats['duplicate_ip'] += 1
                return False, f"Duplicate: IP {ip_address} already processed"
        
        return True, None
    
    def extract_hostnames_from_inventory(self, file_path: Path) -> List[Tuple[str, str]]:
        """
        Extract hostname and IP address pairs from inventory file.
        
        Args:
            file_path: Path to inventory YAML file
            
        Returns:
            List of (hostname, ip_address) tuples for devices with hostnames
        """
        try:
            # Validate file before reading
            if not file_path.exists():
                self.logger.warning(f"File does not exist: {file_path}")
                return []
            
            if file_path.stat().st_size == 0:
                self.logger.warning(f"File is empty: {file_path.name}")
                return []
            
            if file_path.stat().st_size > 10_000_000:  # 10MB limit
                self.logger.warning(f"File too large (>10MB): {file_path.name}")
                return []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                inventory = yaml.safe_load(f)
            
            # Validate structure
            if inventory is None:
                self.logger.warning(f"Empty YAML document in {file_path.name}")
                return []
            
            if not isinstance(inventory, dict):
                self.logger.error(f"Invalid YAML structure (not a dict) in {file_path.name}")
                return []
            
            if 'metadata' not in inventory:
                self.logger.debug(f"No metadata section in {file_path.name}")
                return []
            
            if not isinstance(inventory['metadata'], dict):
                self.logger.error(f"Invalid metadata structure in {file_path.name}")
                return []
            
            if 'leases' not in inventory['metadata']:
                self.logger.debug(f"No leases in metadata for {file_path.name}")
                return []
            
            if not isinstance(inventory['metadata']['leases'], list):
                self.logger.error(f"Invalid leases structure (not a list) in {file_path.name}")
                return []
            
            # Extract hostnames
            hostnames = []
            for idx, lease in enumerate(inventory['metadata']['leases']):
                if not isinstance(lease, dict):
                    self.logger.warning(f"Invalid lease entry at index {idx} in {file_path.name}")
                    continue
                
                if 'hostname' not in lease or 'ip' not in lease:
                    self.logger.debug(f"Lease at index {idx} missing hostname or IP in {file_path.name}")
                    continue
                
                hostname = lease['hostname']
                ip_address = lease['ip']
                
                # Basic type validation
                if not isinstance(hostname, str) or not isinstance(ip_address, str):
                    self.logger.warning(f"Invalid hostname/IP types at index {idx} in {file_path.name}")
                    continue
                
                # Validate non-empty
                if not hostname.strip() or not ip_address.strip():
                    self.logger.warning(f"Empty hostname or IP at index {idx} in {file_path.name}")
                    continue
                
                hostnames.append((hostname.strip(), ip_address.strip()))
            
            return hostnames
        
        except yaml.YAMLError as e:
            self.logger.error(f"YAML parsing error in {file_path.name}: {e}")
            return []
        except UnicodeDecodeError as e:
            self.logger.error(f"File encoding error in {file_path.name}: {e}")
            return []
        except PermissionError as e:
            self.logger.error(f"Permission denied reading {file_path.name}: {e}")
            return []
        except OSError as e:
            self.logger.error(f"OS error reading {file_path.name}: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error reading {file_path.name}: {e}")
            return []
    
    def process_inventory_file(self, file_path: Path):
        """
        Process single inventory file and report new hostnames.
        
        Args:
            file_path: Path to inventory YAML file
        """
        self.logger.debug(f"Processing inventory file: {file_path.name}")
        
        hostnames = self.extract_hostnames_from_inventory(file_path)
        
        if not hostnames:
            self.logger.debug(f"No hostnames found in {file_path.name}")
            return
        
        valid_hostnames = []
        
        for hostname, ip_address in hostnames:
            self.validation_stats['total_processed'] += 1
            
            # Validate IP address format
            ip_valid, ip_error = self.validate_ip_address(ip_address)
            if not ip_valid:
                self.logger.warning(f"[VALIDATION] {ip_error} for hostname '{hostname}'")
                continue
            
            # Validate hostname format (if strict mode enabled)
            if self.strict_validation:
                hostname_valid, hostname_error = self.validate_hostname(hostname)
                if not hostname_valid:
                    self.logger.warning(f"[VALIDATION] {hostname_error}: '{hostname}'")
                    continue
            
            # Check for uniqueness conflicts
            unique, unique_error = self.check_uniqueness(hostname, ip_address)
            if not unique:
                self.logger.warning(f"[VALIDATION] {unique_error}")
                continue
            
            # All validations passed
            self.validation_stats['valid'] += 1
            
            # Track mappings
            self.hostname_to_ip[hostname] = ip_address
            self.ip_to_hostname[ip_address] = hostname
            self.reported_hostnames.add(hostname)
            
            # Report new hostname
            self.logger.info(f"New hostname detected: {hostname} -> {ip_address}")
            valid_hostnames.append((hostname, ip_address))
        
        if valid_hostnames:
            self.logger.info(f"Found {len(valid_hostnames)} new valid hostname(s) in {file_path.name}")
    
    def print_validation_summary(self):
        """Print validation statistics summary."""
        stats = self.validation_stats
        
        self.logger.info("\n" + "="*60)
        self.logger.info("VALIDATION SUMMARY [TEST MODE]")
        self.logger.info("="*60)
        self.logger.info(f"Total processed:        {stats['total_processed']}")
        self.logger.info(f"Valid entries:          {stats['valid']}")
        
        if stats['total_processed'] > 0:
            invalid_count = stats['total_processed'] - stats['valid']
            if invalid_count > 0:
                self.logger.info(f"\nValidation Failures:    {invalid_count}")
                self.logger.info(f"  - Invalid format:     {stats['invalid_format']}")
                self.logger.info(f"  - Invalid site:       {stats['invalid_site']}")
                self.logger.info(f"  - Invalid BMC type:   {stats['invalid_bmc_type']}")
                self.logger.info(f"  - Duplicate hostname: {stats['duplicate_hostname']}")
                self.logger.info(f"  - Duplicate IP:       {stats['duplicate_ip']}")
                self.logger.info(f"  - IP conflicts:       {stats['ip_conflict']}")
        
        self.logger.info("="*60)
    
    def watch(self, poll_interval: int = 5):
        """
        Continuously watch for inventory file changes.
        
        Args:
            poll_interval: Seconds between file system polls
        """
        self.logger.info(f"Watching directory: {self.watch_dir} [TEST MODE]")
        self.logger.info(f"Poll interval: {poll_interval} seconds")
        
        iteration = 0
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while True:
            iteration += 1
            self.logger.debug(f"Polling iteration {iteration}")
            
            try:
                # Scan for inventory files
                inventory_files = self.scan_inventory_files()
                
                if not inventory_files:
                    self.logger.debug("No inventory files found")
                    time.sleep(poll_interval)
                    continue
                
                # Check for modified files
                modified_files = self.get_modified_files(inventory_files)
                
                if modified_files:
                    self.logger.debug(f"Found {len(modified_files)} modified file(s)")
                    
                    for file_path in modified_files:
                        try:
                            self.process_inventory_file(file_path)
                            # Reset error counter on successful processing
                            consecutive_errors = 0
                        except Exception as e:
                            consecutive_errors += 1
                            self.logger.error(f"Error processing {file_path.name}: {e}")
                            
                            if consecutive_errors >= max_consecutive_errors:
                                self.logger.error(f"Too many consecutive errors ({consecutive_errors}). Continuing with caution.")
                                consecutive_errors = 0  # Reset to avoid spam
                
                time.sleep(poll_interval)
            
            except KeyboardInterrupt:
                raise  # Re-raise to be caught by main
            except Exception as e:
                consecutive_errors += 1
                self.logger.error(f"Error in watch loop iteration {iteration}: {e}")
                
                if consecutive_errors >= max_consecutive_errors:
                    self.logger.error(f"Too many consecutive watch loop errors ({consecutive_errors}). Exiting.")
                    raise RuntimeError(f"Watch loop failed after {consecutive_errors} consecutive errors") from e
                
                # Back off before retrying
                time.sleep(min(poll_interval * 2, 60))


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging for DNS watcher."""
    logger = logging.getLogger("bmc_dns_watcher_test")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    
    formatter = logging.Formatter(
        "[TEST] [%(levelname)s] %(asctime)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def test_mac_oui_detection():
    """Test MAC address OUI detection functionality."""
    print("\n" + "="*60)
    print("MAC OUI DETECTION TEST")
    print("="*60)
    
    # Initialize OUI database
    logger = logging.getLogger("oui_test")
    logger.setLevel(logging.INFO)
    oui_db = OUIDatabase(logger=logger)
    
    # Display database stats
    stats = oui_db.get_stats()
    print(f"\nOUI Database Statistics:")
    print(f"  Total entries:     {stats['total_entries']}")
    print(f"  Embedded entries:  {stats['embedded_entries']}")
    print(f"  Cache exists:      {stats['cache_file_exists']}")
    print()
    
    test_cases = [
        # Dell
        ("d0:67:e5:12:34:56", "Dell"),
        ("18:66:da:ab:cd:ef", "Dell"),
        ("f0:1f:af:11:22:33", "Dell"),
        
        # HP/HPE
        ("14:02:ec:11:22:33", "HP"),
        ("94:57:a5:44:55:66", "HP"),
        ("48:0f:cf:77:88:99", "HP"),
        
        # Supermicro
        ("00:25:90:77:88:99", "Supermicro"),
        ("ac:1f:6b:aa:bb:cc", "Supermicro"),
        
        # Cisco
        ("00:1b:d4:11:22:33", "Cisco"),
        
        # Lenovo
        ("00:50:5b:11:22:33", "Lenovo"),
        
        # Unknown
        ("00:11:22:33:44:55", "Unknown"),
    ]
    
    print("Test Results:")
    print("-" * 60)
    for mac, expected in test_cases:
        result = oui_db.lookup(mac)
        status = "[OK]" if result == expected else "[FAIL]"
        print(f"{status} {mac:20} -> {result:15} (expected: {expected})")
    
    print("="*60 + "\n")


def test_oui_update():
    """Test OUI database update from IEEE."""
    print("\n" + "="*60)
    print("OUI DATABASE UPDATE TEST")
    print("="*60)
    
    logger = logging.getLogger("oui_update_test")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    logger.addHandler(handler)
    
    # Use temporary cache file for testing
    test_cache = Path("./oui_cache_test.json")
    
    try:
        oui_db = OUIDatabase(cache_file=test_cache, logger=logger)
        
        print("\nAttempting to update from IEEE OUI database...")
        print("(This may take 10-30 seconds depending on connection)")
        
        success = oui_db.update_from_ieee(timeout=30)
        
        if success:
            stats = oui_db.get_stats()
            print(f"\n[OK] Update successful!")
            print(f"Total OUI entries: {stats['total_entries']}")
            
            # Test a few lookups
            print("\nSample lookups after update:")
            test_macs = [
                "d0:67:e5:00:00:00",  # Dell
                "14:02:ec:00:00:00",  # HP
                "00:25:90:00:00:00",  # Supermicro
            ]
            
            for mac in test_macs:
                result = oui_db.lookup(mac)
                print(f"  {mac} -> {result}")
        else:
            print("\n[WARNING] Update failed - using embedded database")
    
    finally:
        # Cleanup test cache
        if test_cache.exists():
            try:
                test_cache.unlink()
                print(f"\nCleaned up test cache: {test_cache}")
            except:
                pass
    
    print("="*60 + "\n")


def main():
    """Main entry point for BMC inventory reporter (TEST VERSION)."""
    parser = argparse.ArgumentParser(
        description="[TEST] Monitor discovery inventory files and report new BMC hostnames",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run MAC OUI detection tests
  python3 bmc_dns_watcher_test.py --test-oui
  
  # Process existing files once (test mode)
  python3 bmc_dns_watcher_test.py --once --watch-dir ./test_data
  
  # Monitor with debug logging
  python3 bmc_dns_watcher_test.py --watch-dir ./test_data --log-level DEBUG
        """
    )
    
    parser.add_argument(
        '--watch-dir',
        type=Path,
        default=Path('/var/lib/kea/discovery'),
        help='Directory to watch for discovery YAML files (default: /var/lib/kea/discovery)'
    )
    parser.add_argument(
        '--poll-interval',
        type=int,
        default=5,
        help='Polling interval in seconds (default: 5)'
    )
    parser.add_argument(
        '--once',
        action='store_true',
        help='Process existing files once and exit (no continuous monitoring)'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    parser.add_argument(
        '--no-strict',
        action='store_true',
        help='Disable strict hostname validation (allow any format)'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Print validation summary at end (automatically enabled with --once)'
    )
    parser.add_argument(
        '--test-oui',
        action='store_true',
        help='Run MAC OUI detection tests and exit'
    )
    parser.add_argument(
        '--update-oui',
        action='store_true',
        help='Update OUI database from IEEE and exit'
    )
    parser.add_argument(
        '--oui-stats',
        action='store_true',
        help='Display OUI database statistics and exit'
    )
    
    args = parser.parse_args()
    
    # Run OUI detection tests if requested
    if args.test_oui:
        test_mac_oui_detection()
        return 0
    
    # Update OUI database if requested
    if args.update_oui:
        test_oui_update()
        return 0
    
    # Display OUI stats if requested
    if args.oui_stats:
        logger = setup_logging('INFO')
        oui_db = OUIDatabase(logger=logger)
        stats = oui_db.get_stats()
        
        print("\n" + "="*60)
        print("OUI DATABASE STATISTICS")
        print("="*60)
        print(f"Total entries:        {stats['total_entries']}")
        print(f"Embedded entries:     {stats['embedded_entries']}")
        print(f"Cache file:           {OUI_CACHE_FILE}")
        print(f"Cache exists:         {stats['cache_file_exists']}")
        print("="*60 + "\n")
        return 0
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    logger.info("="*60)
    logger.info("BMC DNS INVENTORY REPORTER - TEST MODE")
    logger.info("="*60)
    logger.debug(f"Watch directory: {args.watch_dir}")
    
    try:
        # Validate watch directory before starting
        if not args.watch_dir.exists():
            logger.error(f"Watch directory does not exist: {args.watch_dir}")
            logger.info("Please create the directory or specify a different path with --watch-dir")
            return 1
        
        if not args.watch_dir.is_dir():
            logger.error(f"Watch path is not a directory: {args.watch_dir}")
            return 1
        
        if not os.access(args.watch_dir, os.R_OK):
            logger.error(f"No read permission for directory: {args.watch_dir}")
            return 1
        
        # Validate poll interval
        if args.poll_interval < 1:
            logger.error(f"Invalid poll interval: {args.poll_interval} (must be >= 1 second)")
            return 1
        
        # Initialize watcher
        strict_validation = not args.no_strict
        
        try:
            watcher = InventoryWatcher(args.watch_dir, logger, strict_validation)
        except Exception as e:
            logger.error(f"Failed to initialize watcher: {e}")
            return 1
        
        if args.once:
            # One-time scan
            logger.info("Processing existing inventory files (one-time scan)")
            if strict_validation:
                logger.info("Strict validation: ENABLED")
            else:
                logger.info("Strict validation: DISABLED")
            
            inventory_files = watcher.scan_inventory_files()
            
            if not inventory_files:
                logger.info("No inventory files found to process")
                watcher.print_validation_summary()
                return 0
            
            processed_count = 0
            error_count = 0
            
            for file_path in inventory_files:
                try:
                    watcher.process_inventory_file(file_path)
                    processed_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"Failed to process {file_path.name}: {e}")
            
            logger.info(f"One-time scan complete: {processed_count} processed, {error_count} errors")
            
            # Always show summary for one-time scans
            watcher.print_validation_summary()
            
            # Return error if all files failed
            if error_count > 0 and processed_count == 0:
                return 1
        else:
            # Continuous monitoring
            if strict_validation:
                logger.info("Strict validation: ENABLED")
            else:
                logger.info("Strict validation: DISABLED")
            
            try:
                watcher.watch(args.poll_interval)
            except RuntimeError as e:
                logger.error(f"Watch loop failed: {e}")
                return 1
    
    except KeyboardInterrupt:
        logger.info("\nShutting down inventory reporter (Ctrl+C)")
        
        # Show summary if requested
        if args.summary and 'watcher' in locals():
            try:
                watcher.print_validation_summary()
            except Exception as e:
                logger.warning(f"Could not print summary: {e}")
        
        return 0
    
    except PermissionError as e:
        logger.error(f"[ERROR] Permission denied: {e}")
        return 1
    
    except OSError as e:
        logger.error(f"[ERROR] Operating system error: {e}")
        return 1
    
    except Exception as e:
        logger.error(f"[ERROR] Fatal error: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
