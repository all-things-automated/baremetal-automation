#!/usr/bin/env python3
"""
Kea DHCP Infrastructure Analyzer

Analyzes Kea DHCP lease files to identify infrastructure hardware manufacturers.
Reads kea-leases4.csv and uses MAC address (hwaddr column) OUI lookup.

Usage:
    python3 kea_infrastructure_analyzer.py /var/lib/kea/kea-leases4.csv
    python3 kea_infrastructure_analyzer.py --update-oui /var/lib/kea/kea-leases4.csv

Location: python/src/baremetal/kea_infrastructure_analyzer.py
"""

import sys
import csv
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Set, Tuple
from collections import defaultdict, Counter

# Import OUI database from test script (will be refactored to shared module later)
try:
    from bmc_dns_watcher_test import OUIDatabase
except ImportError:
    print("[ERROR] Cannot import OUIDatabase. Ensure bmc_dns_watcher_test.py is in the same directory.", file=sys.stderr)
    sys.exit(1)


class KeaLeaseAnalyzer:
    """Analyzes Kea DHCP lease file for infrastructure inventory."""
    
    def __init__(self, lease_file: Path, oui_db: OUIDatabase, logger: logging.Logger):
        """
        Initialize Kea lease analyzer.
        
        Args:
            lease_file: Path to kea-leases4.csv
            oui_db: OUI database instance for manufacturer lookup
            logger: Logger instance
        """
        self.lease_file = lease_file
        self.oui_db = oui_db
        self.logger = logger
        
        # Track unique MAC addresses and their metadata
        self.unique_macs: Dict[str, Dict[str, str]] = {}  # mac -> {ip, hostname, manufacturer}
        
        # Statistics
        self.total_leases = 0
        self.unique_mac_count = 0
        self.manufacturer_counts: Counter = Counter()
    
    def parse_lease_file(self) -> bool:
        """
        Parse Kea lease CSV file and extract unique MAC addresses.
        
        CSV Columns: address, hwaddr, client_id, valid_lifetime, expire, 
                     subnet_id, fqdn_fwd, fqdn_rev, hostname, state
        
        Returns:
            True if parsing successful, False otherwise
        """
        try:
            if not self.lease_file.exists():
                self.logger.error(f"Lease file not found: {self.lease_file}")
                return False
            
            self.logger.info(f"Parsing lease file: {self.lease_file}")
            
            with open(self.lease_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                # Validate required columns
                if 'address' not in reader.fieldnames or 'hwaddr' not in reader.fieldnames:
                    self.logger.error("CSV missing required columns: address, hwaddr")
                    return False
                
                for row in reader:
                    self.total_leases += 1
                    
                    address = row.get('address', '').strip()
                    hwaddr = row.get('hwaddr', '').strip()
                    hostname = row.get('hostname', '').strip()
                    
                    # Skip entries without MAC address
                    if not hwaddr:
                        continue
                    
                    # Skip invalid MAC addresses (too short or malformed)
                    # Valid MAC: XX:XX:XX:XX:XX:XX (17 chars with colons)
                    if len(hwaddr.replace(':', '').replace('-', '')) < 12:
                        self.logger.debug(f"Skipping invalid MAC: {hwaddr}")
                        continue
                    
                    # Store unique MAC (use first occurrence)
                    if hwaddr not in self.unique_macs:
                        # Lookup manufacturer
                        manufacturer = self.oui_db.lookup(hwaddr)
                        
                        self.unique_macs[hwaddr] = {
                            'ip': address,
                            'hostname': hostname,
                            'manufacturer': manufacturer
                        }
                        
                        # Track manufacturer statistics
                        self.manufacturer_counts[manufacturer] += 1
                        
                        self.logger.debug(f"Found MAC: {hwaddr} -> {manufacturer}")
            
            self.unique_mac_count = len(self.unique_macs)
            self.logger.info(f"Parsed {self.total_leases} lease(s), found {self.unique_mac_count} unique MAC address(es)")
            
            return True
        
        except csv.Error as e:
            self.logger.error(f"CSV parsing error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error parsing lease file: {e}")
            return False
    
    def print_summary(self):
        """Print infrastructure analysis summary."""
        print("\n" + "="*70)
        print("KEA DHCP INFRASTRUCTURE ANALYSIS")
        print("="*70)
        print(f"Lease file:           {self.lease_file}")
        print(f"Total leases:         {self.total_leases}")
        print(f"Unique MAC addresses: {self.unique_mac_count}")
        print()
        
        if not self.unique_macs:
            print("No valid MAC addresses found.")
            print("="*70)
            return
        
        # Manufacturer breakdown
        print("MANUFACTURER BREAKDOWN")
        print("-"*70)
        print(f"{'Manufacturer':<30} {'Count':<10} {'Percentage':<10}")
        print("-"*70)
        
        for manufacturer, count in self.manufacturer_counts.most_common():
            percentage = (count / self.unique_mac_count) * 100
            print(f"{manufacturer:<30} {count:<10} {percentage:>6.1f}%")
        
        print("="*70)
    
    def print_detailed_inventory(self, manufacturer_filter: str = None):
        """
        Print detailed inventory of devices.
        
        Args:
            manufacturer_filter: Optional manufacturer name to filter by
        """
        print("\n" + "="*70)
        print("DETAILED DEVICE INVENTORY")
        if manufacturer_filter:
            print(f"Filter: {manufacturer_filter}")
        print("="*70)
        print(f"{'MAC Address':<20} {'IP Address':<16} {'Manufacturer':<15} {'Hostname':<20}")
        print("-"*70)
        
        # Sort by manufacturer, then MAC
        sorted_devices = sorted(
            self.unique_macs.items(),
            key=lambda x: (x[1]['manufacturer'], x[0])
        )
        
        for mac, info in sorted_devices:
            if manufacturer_filter and info['manufacturer'] != manufacturer_filter:
                continue
            
            print(f"{mac:<20} {info['ip']:<16} {info['manufacturer']:<15} {info['hostname']:<20}")
        
        print("="*70)
    
    def export_to_csv(self, output_file: Path):
        """
        Export infrastructure inventory to CSV file.
        
        Args:
            output_file: Path to output CSV file
        """
        try:
            with open(output_file, 'w', encoding='utf-8', newline='') as f:
                writer = csv.writer(f)
                
                # Write header
                writer.writerow(['mac_address', 'ip_address', 'hostname', 'manufacturer'])
                
                # Write data (sorted by manufacturer)
                sorted_devices = sorted(
                    self.unique_macs.items(),
                    key=lambda x: (x[1]['manufacturer'], x[0])
                )
                
                for mac, info in sorted_devices:
                    writer.writerow([
                        mac,
                        info['ip'],
                        info['hostname'],
                        info['manufacturer']
                    ])
            
            self.logger.info(f"Exported inventory to: {output_file}")
            print(f"\n[OK] Exported {self.unique_mac_count} device(s) to: {output_file}")
        
        except Exception as e:
            self.logger.error(f"Failed to export to CSV: {e}")
            print(f"[ERROR] Export failed: {e}")


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging."""
    logger = logging.getLogger("kea_analyzer")
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


def main():
    """Main entry point for Kea infrastructure analyzer."""
    parser = argparse.ArgumentParser(
        description="Analyze Kea DHCP leases to identify infrastructure hardware manufacturers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze lease file
  python3 kea_infrastructure_analyzer.py /var/lib/kea/kea-leases4.csv
  
  # Export to CSV
  python3 kea_infrastructure_analyzer.py /var/lib/kea/kea-leases4.csv --export inventory.csv
  
  # Show detailed inventory for specific manufacturer
  python3 kea_infrastructure_analyzer.py /var/lib/kea/kea-leases4.csv --filter Dell
  
  # Update OUI database before analysis
  python3 kea_infrastructure_analyzer.py /var/lib/kea/kea-leases4.csv --update-oui
        """
    )
    
    parser.add_argument(
        'lease_file',
        type=Path,
        help='Path to Kea DHCP lease CSV file (kea-leases4.csv)'
    )
    parser.add_argument(
        '--update-oui',
        action='store_true',
        help='Update OUI database from IEEE before analysis'
    )
    parser.add_argument(
        '--export',
        type=Path,
        metavar='OUTPUT_FILE',
        help='Export inventory to CSV file'
    )
    parser.add_argument(
        '--filter',
        type=str,
        metavar='MANUFACTURER',
        help='Show detailed inventory for specific manufacturer'
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed inventory for all devices'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    try:
        # Validate lease file
        if not args.lease_file.exists():
            logger.error(f"Lease file not found: {args.lease_file}")
            return 1
        
        # Initialize OUI database
        logger.debug("Initializing OUI database...")
        oui_db = OUIDatabase(logger=logger)
        
        # Update OUI database if requested
        if args.update_oui:
            logger.info("Updating OUI database from IEEE...")
            success = oui_db.update_from_ieee(timeout=30)
            if success:
                logger.info("OUI database updated successfully")
            else:
                logger.warning("OUI update failed, using embedded database")
        
        # Display OUI stats
        stats = oui_db.get_stats()
        logger.info(f"OUI database loaded: {stats['total_entries']} entries")
        
        # Initialize analyzer
        analyzer = KeaLeaseAnalyzer(args.lease_file, oui_db, logger)
        
        # Parse lease file
        if not analyzer.parse_lease_file():
            logger.error("Failed to parse lease file")
            return 1
        
        # Print summary
        analyzer.print_summary()
        
        # Print detailed inventory if requested
        if args.detailed or args.filter:
            analyzer.print_detailed_inventory(manufacturer_filter=args.filter)
        
        # Export to CSV if requested
        if args.export:
            analyzer.export_to_csv(args.export)
        
        return 0
    
    except KeyboardInterrupt:
        logger.info("\nAnalysis interrupted by user")
        return 0
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return 1


if __name__ == '__main__':
    sys.exit(main())
