#!/usr/bin/env python3
"""
Kea DHCP Lease Monitor for Bare-Metal Discovery

Monitors Kea DHCP lease events and triggers automated discovery workflow.
Supports both file-based polling and database event-driven modes.
"""

import os
import sys
import time
import logging
import argparse
import csv
from pathlib import Path
from datetime import datetime, timezone
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

try:
    import yaml
except ImportError:
    print("[ERROR] PyYAML is required. Install with: pip3 install pyyaml", file=sys.stderr)
    sys.exit(1)

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # Optional dependency for database reservations

try:
    import vault_credentials
    import solidserver_connection
    from SOLIDserverRest import adv as sdsadv
    from SOLIDserverRest.Exception import SDSError, SDSDNSError
except ImportError:
    vault_credentials = None
    solidserver_connection = None
    print("[WARNING] Vault/SOLIDserver modules not available - DNS creation disabled", file=sys.stderr)


@dataclass
class DHCPLease:
    """Represents a DHCP lease from Kea."""
    ip_address: str
    mac_address: str
    hostname: Optional[str]
    subnet_id: Optional[str]
    lease_timestamp: int
    
    def __hash__(self):
        """Hash based on IP address for set operations."""
        return hash(self.ip_address)
    
    def __eq__(self, other):
        """Equality based on IP address."""
        if not isinstance(other, DHCPLease):
            return False
        return self.ip_address == other.ip_address


class LeaseSource(ABC):
    """
    Abstract interface for Kea DHCP lease sources.
    Implementations: FileLeaseSource (CSV), DatabaseLeaseSource (PostgreSQL/MySQL).
    """
    
    @abstractmethod
    def get_new_leases(self) -> List[DHCPLease]:
        """
        Retrieve new leases since last check.
        
        Returns:
            List of DHCPLease objects representing new/updated leases
        """
        pass
    
    @abstractmethod
    def mark_processed(self, lease: DHCPLease) -> None:
        """
        Mark a lease as processed to avoid reprocessing.
        
        Args:
            lease: DHCPLease object to mark as processed
        """
        pass


class FileLeaseSource(LeaseSource):
    """File-based lease source monitoring Kea CSV lease file."""
    
    def __init__(self, lease_file: Path, logger: logging.Logger, subnet_filter: Optional[str] = None):
        """
        Initialize file-based lease source.
        
        Args:
            lease_file: Path to Kea lease CSV file
            logger: Logger instance
            subnet_filter: Comma-separated subnet IDs to monitor (None = all)
        """
        self.lease_file = lease_file
        self.logger = logger
        self.subnet_filter = set(subnet_filter.split(',')) if subnet_filter else None
        self.processed_leases: Set[str] = set()  # Track processed IPs
        self.last_mtime: Optional[float] = None
    
    def _parse_lease_line(self, line: List[str]) -> Optional[DHCPLease]:
        """
        Parse CSV lease line into DHCPLease object.
        
        Args:
            line: CSV row as list of strings
            
        Returns:
            DHCPLease object or None if invalid/filtered
        """
        try:
            if len(line) < 9:
                return None
            
            ip_address = line[0]
            mac_address = line[1]
            subnet_id = line[5]
            hostname = line[8] if len(line) > 8 and line[8] else None
            expire_timestamp = int(line[4]) if line[4] else 0
            
            # Apply subnet filter
            if self.subnet_filter and subnet_id not in self.subnet_filter:
                return None
            
            return DHCPLease(
                ip_address=ip_address,
                mac_address=mac_address,
                hostname=hostname,
                subnet_id=subnet_id,
                lease_timestamp=expire_timestamp
            )
        
        except (ValueError, IndexError) as e:
            self.logger.debug(f"Failed to parse lease line: {e}")
            return None
    
    def get_new_leases(self) -> List[DHCPLease]:
        """
        Read lease file and return new leases since last check.
        
        Returns:
            List of new DHCPLease objects
        """
        if not self.lease_file.exists():
            self.logger.warning(f"Lease file not found: {self.lease_file}")
            return []
        
        # Check if file has been modified
        current_mtime = self.lease_file.stat().st_mtime
        if self.last_mtime and current_mtime == self.last_mtime:
            return []  # No changes
        
        self.last_mtime = current_mtime
        
        new_leases = []
        
        try:
            with open(self.lease_file, 'r') as f:
                reader = csv.reader(f)
                for line in reader:
                    lease = self._parse_lease_line(line)
                    if lease and lease.ip_address not in self.processed_leases:
                        new_leases.append(lease)
                        self.logger.debug(f"New lease detected: {lease.ip_address} ({lease.hostname})")
        
        except Exception as e:
            self.logger.error(f"Failed to read lease file: {e}")
            return []
        
        return new_leases
    
    def mark_processed(self, lease: DHCPLease) -> None:
        """Mark lease IP as processed."""
        self.processed_leases.add(lease.ip_address)
    
    def get_all_leases(self) -> List[DHCPLease]:
        """
        Read all leases from lease file (for initial sync).
        
        Returns:
            List of all DHCPLease objects in the file
        """
        if not self.lease_file.exists():
            self.logger.warning(f"Lease file not found: {self.lease_file}")
            return []
        
        all_leases = []
        
        try:
            with open(self.lease_file, 'r') as f:
                reader = csv.reader(f)
                for line in reader:
                    lease = self._parse_lease_line(line)
                    if lease:
                        all_leases.append(lease)
                        self.logger.debug(f"Found existing lease: {lease.ip_address} ({lease.hostname})")
        
        except Exception as e:
            self.logger.error(f"Failed to read lease file: {e}")
            return []
        
        return all_leases


class DatabaseLeaseSource(LeaseSource):
    """
    Database-based lease source for Kea with PostgreSQL NOTIFY/LISTEN.
    
    Event-driven implementation using PostgreSQL's LISTEN/NOTIFY mechanism.
    Requires database trigger to send notifications on lease changes.
    """
    
    def __init__(self, db_host: str, db_port: int, db_name: str, 
                 db_user: str, db_password: str, subnet_id: Optional[int],
                 logger: logging.Logger, timeout: int = 5):
        """
        Initialize database-based lease source with NOTIFY/LISTEN.
        
        Args:
            db_host: PostgreSQL host
            db_port: PostgreSQL port
            db_name: PostgreSQL database name
            db_user: PostgreSQL username
            db_password: PostgreSQL password
            subnet_id: Optional subnet ID filter
            logger: Logger instance
            timeout: Polling timeout in seconds for LISTEN (default: 5)
        """
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name
        self.db_user = db_user
        self.db_password = db_password
        self.subnet_id = subnet_id
        self.logger = logger
        self.timeout = timeout
        self.processed_lease_ids: Set[str] = set()
        
        if psycopg2 is None:
            raise ImportError("psycopg2 is required for DatabaseLeaseSource")
        
        # Create persistent connection for LISTEN
        self.conn = psycopg2.connect(
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            user=self.db_user,
            password=self.db_password
        )
        self.conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        self.cursor = self.conn.cursor()
        
        # Start listening for lease notifications
        self.cursor.execute("LISTEN kea_lease_events;")
        self.logger.info("Listening for database lease events on channel 'kea_lease_events'")
    
    def get_new_leases(self) -> List[DHCPLease]:
        """
        Retrieve new leases from database using NOTIFY/LISTEN.
        
        Returns:
            List of new DHCPLease objects from database notifications
        """
        import select
        
        new_leases = []
        
        try:
            # Wait for notifications with timeout
            if select.select([self.conn], [], [], self.timeout) == ([], [], []):
                # Timeout - no notifications
                return []
            
            # Process all pending notifications
            self.conn.poll()
            while self.conn.notifies:
                notify = self.conn.notifies.pop(0)
                self.logger.info(f"Received database notification: {notify.payload}")
                
                # Parse notification payload (JSON format from trigger)
                try:
                    import json
                    import ipaddress
                    
                    payload = json.loads(notify.payload)
                    hostname = payload.get('hostname')
                    ipv4_address = payload.get('ipv4_address')
                    dhcp_identifier = payload.get('dhcp_identifier')
                    
                    if not hostname or not ipv4_address:
                        self.logger.warning(f"Incomplete notification data: {payload}")
                        continue
                    
                    # Convert bigint to IP address string
                    if isinstance(ipv4_address, int):
                        ip_address = str(ipaddress.IPv4Address(ipv4_address))
                    else:
                        ip_address = str(ipv4_address)
                    
                    # Convert hex string MAC to colon format
                    if dhcp_identifier:
                        mac_address = ':'.join(dhcp_identifier[i:i+2] for i in range(0, len(dhcp_identifier), 2))
                    else:
                        mac_address = None
                    
                    # Skip if already processed (using IP as identifier)
                    if ip_address in self.processed_lease_ids:
                        self.logger.debug(f"Already processed: {ip_address}")
                        continue
                    
                    lease = DHCPLease(
                        ip_address=ip_address,
                        mac_address=mac_address,
                        hostname=hostname,
                        subnet_id=str(self.subnet_id) if self.subnet_id else None,
                        lease_timestamp=int(time.time())
                    )
                    new_leases.append(lease)
                    self.processed_lease_ids.add(ip_address)
                    self.logger.info(f"New reservation from database: {ip_address} -> {hostname} ({mac_address})")
                
                except (ValueError, json.JSONDecodeError, KeyError) as e:
                    self.logger.warning(f"Failed to parse notification payload: {notify.payload} - {e}")
                    continue
        
        except Exception as e:
            self.logger.error(f"Error receiving database notifications: {e}")
            return []
        
        return new_leases
    
    def mark_processed(self, lease: DHCPLease) -> None:
        """Mark lease as processed."""
        pass
    
    def close(self):
        """Close database connection."""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        self.logger.info("Database lease source closed")


class LeaseProcessor:
    """Processes DHCP leases and generates Ansible inventory files."""
    
    def __init__(self, output_dir: Path, logger: logging.Logger, 
                 db_host: Optional[str] = None, db_port: int = 5432,
                 db_name: Optional[str] = None, db_user: Optional[str] = None,
                 db_password: Optional[str] = None, subnet_id: int = 1,
                 sync_existing: bool = False, enable_dns: bool = False,
                 dns_zone: Optional[str] = None, dns_scope: str = "internal",
                 use_vault: bool = False):
        """
        Initialize lease processor.
        
        Args:
            output_dir: Directory for generated inventory files
            logger: Logger instance
            db_host: PostgreSQL host for static reservations (optional)
            db_port: PostgreSQL port (default: 5432)
            db_name: PostgreSQL database name (default: kea)
            db_user: PostgreSQL username
            db_password: PostgreSQL password (if not using Vault)
            subnet_id: DHCP subnet ID for reservations (default: 1)
            sync_existing: Sync existing leases from memfile to database on startup
            enable_dns: Enable DNS record creation (default: False)
            dns_zone: DNS zone for record creation (e.g., 'site.com')
            dns_scope: DNS scope - 'internal' or 'external' (default: internal)
            use_vault: Retrieve credentials from Vault (default: False)
        """
        self.output_dir = output_dir
        self.logger = logger
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.sync_existing = sync_existing
        self.use_vault = use_vault
        
        # Initialize Vault client if enabled
        self.vault_client = None
        self.sds_connection = None
        if use_vault and vault_credentials:
            try:
                self.vault_client = vault_credentials.get_vault_client()
                self.logger.info("Successfully initialized Vault client")
            except Exception as e:
                self.logger.error(f"Failed to initialize Vault client: {e}")
                self.use_vault = False
        
        # Database configuration for static reservations
        self.db_host = db_host
        self.db_port = db_port
        self.db_name = db_name or "kea"
        self.db_user = db_user
        self.db_password = db_password
        self.subnet_id = subnet_id
        
        # Fetch database credentials from Vault if enabled
        if self.use_vault and self.vault_client:
            try:
                db_creds = vault_credentials.get_kea_database_credentials(self.vault_client)
                self.db_password = db_creds['db_password']
                self.logger.info("Retrieved database credentials from Vault")
            except Exception as e:
                self.logger.warning(f"Failed to retrieve database credentials from Vault: {e}")
        
        self.db_enabled = all([db_host, db_user, self.db_password])
        
        # DNS configuration
        self.enable_dns = enable_dns
        self.dns_zone = dns_zone
        self.dns_scope = dns_scope
        
        if self.db_enabled:
            if psycopg2 is None:
                self.logger.warning("psycopg2 not installed - static reservations disabled")
                self.db_enabled = False
            else:
                self.logger.info(f"Static reservations enabled: {db_host}:{db_port}/{self.db_name}")
                if self.enable_dns:
                    if dns_zone:
                        self.logger.info(f"DNS record creation enabled: zone={dns_zone}")
                    else:
                        self.logger.warning("DNS enabled but no zone specified - DNS creation disabled")
                        self.enable_dns = False
    
    def sync_existing_leases(self, leases: List[DHCPLease]) -> int:
        """
        Sync existing leases from memfile to database.
        Only creates reservations for leases with valid hostnames matching naming convention.
        
        Args:
            leases: List of all existing DHCPLease objects
            
        Returns:
            Number of reservations created
        """
        if not self.db_enabled:
            self.logger.info("Database mode disabled - skipping existing lease sync")
            return 0
        
        self.logger.info(f"Syncing {len(leases)} existing leases to database...")
        
        created_count = 0
        skipped_no_hostname = 0
        skipped_no_match = 0
        
        for lease in leases:
            if not lease.hostname:
                skipped_no_hostname += 1
                self.logger.debug(f"Skipped {lease.ip_address}: no hostname")
                continue
            
            # Only sync leases matching site-cabinet naming convention
            result = self._extract_site_and_cabinet(lease)
            if not result:
                skipped_no_match += 1
                self.logger.debug(
                    f"Skipped {lease.ip_address} ({lease.hostname}): "
                    f"doesn't match site-cabinet convention"
                )
                continue
            
            if self.create_static_reservation(lease):
                created_count += 1
        
        self.logger.info(
            f"Sync complete: {created_count} reservations created, "
            f"{skipped_no_hostname} skipped (no hostname), "
            f"{skipped_no_match} skipped (no convention match)"
        )
        
        return created_count
    
    def create_static_reservation(self, lease: DHCPLease) -> bool:
        """Create or update static DHCP reservation using UPSERT."""
        if not self.db_enabled:
            return False
        
        if not lease.hostname:
            self.logger.debug(f"Skipping reservation for {lease.ip_address}: no hostname")
            return False
        
        try:
            # Convert MAC address to format expected by decode()
            # Remove colons: aa:bb:cc:dd:ee:ff -> AABBCCDDEEFF
            mac_hex = lease.mac_address.replace(':', '').upper()
            
            # UPSERT: Single query using INSERT ... ON CONFLICT
            # Updates IP and hostname if MAC already exists for this subnet
            upsert_sql = """
                INSERT INTO hosts (
                    dhcp_identifier,
                    dhcp_identifier_type,
                    dhcp4_subnet_id,
                    ipv4_address,
                    hostname
                ) VALUES (
                    decode(%s, 'hex'),
                    0,
                    %s,
                    (%s::inet - '0.0.0.0'::inet)::bigint,
                    %s
                )
                ON CONFLICT (dhcp_identifier, dhcp_identifier_type, dhcp4_subnet_id)
                DO UPDATE SET
                    ipv4_address = EXCLUDED.ipv4_address,
                    hostname = EXCLUDED.hostname
                RETURNING host_id, 
                    (xmax = 0) AS inserted
            """
            
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            
            try:
                with conn.cursor() as cur:
                    cur.execute(upsert_sql, (mac_hex, self.subnet_id, lease.ip_address, lease.hostname))
                    result = cur.fetchone()
                    
                    if result:
                        host_id, inserted = result
                        action = "created" if inserted else "updated"
                        
                        # Create DNS record as part of transaction
                        if self.enable_dns:
                            dns_success = self.create_dns_record(lease.hostname, lease.ip_address)
                            if not dns_success:
                                conn.rollback()
                                self.logger.error(
                                    f"Transaction rolled back: DNS creation failed for {lease.hostname}"
                                )
                                return False
                        
                        # Commit transaction (both DB reservation and DNS record)
                        conn.commit()
                        
                        self.logger.info(
                            f"Static reservation {action}: {lease.hostname} "
                            f"({lease.ip_address} / {lease.mac_address})"
                        )
                        
                        if self.enable_dns:
                            self.logger.debug(
                                f"Transaction complete: reservation host_id={host_id}, DNS record created"
                            )
                        
                        return True
            finally:
                conn.close()
        
        except Exception as e:
            self.logger.error(f"Failed to create reservation for {lease.ip_address}: {e}")
            return False
        
        return False
    
    def dns_record_exists(self, hostname: str) -> bool:
        """Check if DNS A record exists in SOLIDserver."""
        if not self.enable_dns or not self.dns_zone:
            return False
        
        if not solidserver_connection or not vault_credentials:
            return False
        
        fqdn = f"{hostname}.{self.dns_zone}"
        
        try:
            # Get SOLIDserver connection
            if self.use_vault and self.vault_client:
                sds_creds = vault_credentials.get_solidserver_credentials(self.vault_client)
                sds = sdsadv.SDS(
                    ip_address=sds_creds.get('sds_host', os.getenv('SDS_HOST', '172.30.16.141')),
                    user=sds_creds['sds_login'],
                    pwd=sds_creds['sds_password']
                )
                sds.connect(method="native")
            else:
                sds = solidserver_connection.get_connection()
            
            # Query for existing record
            dns_server_name = 'dns-internal-smart.site.com' if self.dns_scope == 'internal' else 'dns-primary.site.com'
            ss_dns = sdsadv.DNS(name=dns_server_name, sds=sds)
            
            # Search for the record
            records = sds.query("dns_rr_list", {
                "WHERE": f"dns_name = '{dns_server_name}' AND rr_full_name = '{fqdn}'"
            })
            
            return len(records) > 0
        
        except Exception as e:
            self.logger.debug(f"Error checking DNS record for {fqdn}: {e}")
            return False
    
    def sync_dns_records(self) -> int:
        """Sync DNS records for all existing static reservations in database."""
        if not self.db_enabled or not self.enable_dns:
            return 0
        
        self.logger.info("Starting DNS consistency check for existing reservations...")
        created_count = 0
        
        try:
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                dbname=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            
            with conn.cursor() as cursor:
                # Query all static reservations
                cursor.execute("""
                    SELECT DISTINCT hostname, ipv4_address, dhcp_identifier
                    FROM hosts
                    WHERE hostname IS NOT NULL 
                      AND hostname != ''
                      AND ipv4_address IS NOT NULL
                    ORDER BY hostname
                """)
                
                reservations = cursor.fetchall()
                self.logger.info(f"Found {len(reservations)} static reservations to check")
                
                for hostname, ip_bytes, mac_bytes in reservations:
                    # Convert IP from PostgreSQL inet type (handles both string and integer)
                    import ipaddress
                    if isinstance(ip_bytes, int):
                        ip_address = str(ipaddress.IPv4Address(ip_bytes))
                    else:
                        ip_address = str(ip_bytes)
                    
                    # Check if DNS record exists
                    if not self.dns_record_exists(hostname):
                        self.logger.info(f"Creating missing DNS record for {hostname} -> {ip_address}")
                        if self.create_dns_record(hostname, ip_address):
                            created_count += 1
                    else:
                        self.logger.debug(f"DNS record already exists for {hostname}")
            
            conn.close()
            self.logger.info(f"DNS consistency check complete: {created_count} records created")
            return created_count
        
        except Exception as e:
            self.logger.error(f"Failed to sync DNS records: {e}")
            return created_count
    
    def create_dns_record(self, hostname: str, ip_address: str) -> bool:
        """Create DNS A record in SOLIDserver using Vault credentials."""
        if not self.enable_dns:
            return True
        
        if not self.dns_zone:
            self.logger.debug(f"DNS zone not configured - skipping DNS for {hostname}")
            return True
        
        if not solidserver_connection or not vault_credentials:
            self.logger.warning("SOLIDserver/Vault modules not available - skipping DNS")
            return True
        
        fqdn = f"{hostname}.{self.dns_zone}"
        
        try:
            # Get SOLIDserver connection
            if self.use_vault and self.vault_client:
                # Get credentials from Vault
                sds_creds = vault_credentials.get_solidserver_credentials(self.vault_client)
                # Create SDS connection
                sds = sdsadv.SDS(
                    ip_address=sds_creds.get('sds_host', os.getenv('SDS_HOST', '172.30.16.141')),
                    user=sds_creds['sds_login'],
                    pwd=sds_creds['sds_password']
                )
                sds.connect(method="native")
            else:
                # Fallback to environment-based connection
                sds = solidserver_connection.get_connection()
            
            # DNS server mapping
            zone_to_server_mapping = {
                'internal': 'dns-internal-smart.site.com',
                'external': 'dns-primary.site.com'
            }
            dns_server_name = zone_to_server_mapping.get(self.dns_scope, 'dns-internal-smart.site.com')
            
            # Get zone ID (required by SOLIDserver API)
            zparameters = {
                "WHERE": f"dns_name = '{dns_server_name}' AND dnszone_name = '{self.dns_zone}'"
            }
            my_zs = sds.query("dns_zone_list", zparameters, timeout=60)
            if len(my_zs) != 1:
                raise SDSError(f"Expected 1 zone, found {len(my_zs)}")
            zone_id = my_zs[0]['dnszone_id']
            
            # Create DNS server and zone objects
            ss_dns = sdsadv.DNS(name=dns_server_name, sds=sds)
            dns_zone = sdsadv.DNS_zone(sds=sds, name=self.dns_zone)
            dns_zone.set_dns(ss_dns)
            dns_zone.myid = zone_id
            ss_dns.refresh()
            dns_zone.refresh()
            
            # Create DNS A record
            dns_rr = sdsadv.DNS_record(sds, fqdn)
            dns_rr.zone = dns_zone
            dns_rr.set_dns(ss_dns)
            dns_rr.set_ttl(600)
            dns_rr.set_type('A', ip=ip_address)
            dns_rr.create()
            
            self.logger.info(f"[DNS] Created A record: {fqdn} -> {ip_address} (scope: {self.dns_scope})")
            return True
        
        except (SDSError, SDSDNSError) as e:
            self.logger.error(f"SOLIDserver error creating DNS record for {fqdn}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Failed to create DNS record for {fqdn}: {e}")
            return False
    
    def generate_inventory(self, lease: DHCPLease) -> Path:
        """
        Generate individual Ansible inventory file for single lease.
        
        Args:
            lease: DHCPLease to process
            
        Returns:
            Path to generated inventory file
        """
        inventory = {
            'bmc_targets': [
                {'ip': lease.ip_address}
            ],
            'metadata': {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'source': 'kea_lease_monitor',
                'lease_info': {
                    'ip': lease.ip_address,
                    'mac': lease.mac_address,
                }
            }
        }
        
        if lease.hostname:
            inventory['metadata']['lease_info']['hostname'] = lease.hostname
        if lease.subnet_id:
            inventory['metadata']['lease_info']['subnet'] = lease.subnet_id
        
        # Generate filename
        safe_ip = lease.ip_address.replace('.', '-')
        output_file = self.output_dir / f"{safe_ip}-bmc.yml"
        
        try:
            with open(output_file, 'w') as f:
                yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
            
            self.logger.info(f"Generated inventory: {output_file}")
            return output_file
        
        except Exception as e:
            self.logger.error(f"Failed to write inventory {output_file}: {e}")
            raise
    
    def _extract_rack_unit(self, hostname: str) -> int:
        """
        Extract rack unit number from hostname for sorting.
        
        Handles multi-RU devices: us3-cab01-ru17-18-idrac -> 18 (highest RU)
        
        Args:
            hostname: BMC hostname (e.g., us3-cab10-ru17-idrac)
            
        Returns:
            Rack unit number (highest if range), or 0 if not found
        """
        import re
        
        if not hostname:
            return 0
        
        hostname_lower = hostname.lower()
        
        # Match ru## or ru##-## pattern
        ru_match = re.search(r'ru(\d+)(?:-(\d+))?', hostname_lower)
        
        if ru_match:
            ru_start = int(ru_match.group(1))
            ru_end = int(ru_match.group(2)) if ru_match.group(2) else ru_start
            # Return highest RU for multi-RU devices
            return max(ru_start, ru_end)
        
        return 0
    
    def _format_rack_unit(self, hostname: str) -> str:
        """
        Format rack unit display string from hostname.
        
        Displays range as "RU high-low" for multi-RU devices (descending order).
        
        Args:
            hostname: BMC hostname (e.g., us3-cab10-ru7-9-idrac)
            
        Returns:
            Formatted rack unit string (e.g., "RU 9-7") or empty string
        """
        import re
        
        if not hostname:
            return ''
        
        hostname_lower = hostname.lower()
        
        # Match ru## or ru##-## pattern
        ru_match = re.search(r'ru(\d+)(?:-(\d+))?', hostname_lower)
        
        if ru_match:
            ru_start = int(ru_match.group(1))
            ru_end = int(ru_match.group(2)) if ru_match.group(2) else None
            
            if ru_end:
                # Multi-RU device: show as "RU high-low"
                return f"RU {max(ru_start, ru_end)}-{min(ru_start, ru_end)}"
            else:
                # Single RU device
                return f"RU {ru_start}"
        
        return ''
    
    def _get_rack_unit_range(self, hostname: str) -> set:
        """
        Get set of all rack units occupied by a device.
        
        Args:
            hostname: BMC hostname (e.g., us3-cab10-ru7-9-idrac)
            
        Returns:
            Set of rack unit numbers (e.g., {7, 8, 9})
        """
        import re
        
        if not hostname:
            return set()
        
        hostname_lower = hostname.lower()
        ru_match = re.search(r'ru(\d+)(?:-(\d+))?', hostname_lower)
        
        if ru_match:
            ru_start = int(ru_match.group(1))
            ru_end = int(ru_match.group(2)) if ru_match.group(2) else ru_start
            return set(range(min(ru_start, ru_end), max(ru_start, ru_end) + 1))
        
        return set()
    
    def _validate_bmc_conflicts(self, bmc_targets: list, site: str, cabinet: str) -> None:
        """
        Validate BMC targets for conflicts and log warnings.
        
        Checks for:
        - Duplicate MAC addresses (different IPs)
        - Duplicate hostnames (different IPs)
        - Overlapping rack unit ranges
        
        Args:
            bmc_targets: List of BMC target dicts
            site: Site prefix
            cabinet: Cabinet ID
        """
        mac_to_ips = {}
        hostname_to_ips = {}
        ru_usage = {}  # {rack_unit: [(ip, hostname), ...]}
        
        # Collect data
        for target in bmc_targets:
            ip = target['ip']
            mac = target.get('mac', '')
            hostname = target.get('hostname', '')
            
            # Track MAC addresses
            if mac:
                if mac not in mac_to_ips:
                    mac_to_ips[mac] = []
                mac_to_ips[mac].append(ip)
            
            # Track hostnames
            if hostname:
                if hostname not in hostname_to_ips:
                    hostname_to_ips[hostname] = []
                hostname_to_ips[hostname].append(ip)
                
                # Track rack unit occupancy
                rack_units = self._get_rack_unit_range(hostname)
                for ru in rack_units:
                    if ru not in ru_usage:
                        ru_usage[ru] = []
                    ru_usage[ru].append((ip, hostname))
        
        # Check for conflicts
        conflict_found = False
        
        # Duplicate MAC addresses
        for mac, ips in mac_to_ips.items():
            if len(ips) > 1:
                self.logger.warning(
                    f"[{site.upper()}-{cabinet.upper()}] CONFLICT: MAC {mac} assigned to multiple IPs: {', '.join(sorted(ips))}"
                )
                conflict_found = True
        
        # Duplicate hostnames
        for hostname, ips in hostname_to_ips.items():
            if len(ips) > 1:
                self.logger.warning(
                    f"[{site.upper()}-{cabinet.upper()}] CONFLICT: Hostname '{hostname}' assigned to multiple IPs: {', '.join(sorted(ips))}"
                )
                conflict_found = True
        
        # Overlapping rack units
        for ru, devices in ru_usage.items():
            if len(devices) > 1:
                device_list = ', '.join([f"{hostname}({ip})" for ip, hostname in sorted(devices)])
                self.logger.warning(
                    f"[{site.upper()}-{cabinet.upper()}] CONFLICT: Rack unit {ru} claimed by multiple devices: {device_list}"
                )
                conflict_found = True
        
        if conflict_found:
            self.logger.error(
                f"[{site.upper()}-{cabinet.upper()}] Cabinet has configuration conflicts - review DHCP leases and device assignments"
            )
    
    def _extract_site_and_cabinet(self, lease: DHCPLease) -> Optional[tuple[str, str]]:
        """
        Extract site prefix and cabinet ID from lease hostname.
        
        Expects hostname format: {site}-cab{num}-... (e.g., us3-cab10-ru17-idrac)
        Only returns result if hostname matches the convention exactly.
        
        Args:
            lease: DHCPLease object with hostname
            
        Returns:
            Tuple of (site_prefix, cabinet_id) or None if hostname doesn't match convention
        """
        import re
        
        if not lease.hostname:
            self.logger.debug(f"Skipping lease {lease.ip_address}: no hostname")
            return None
        
        hostname_lower = lease.hostname.lower()
        
        # Match pattern: {site}-cab{num}-... where site is us1/us2/us3/us4/dv
        pattern = r'^(us[1-4]|dv)-cab(\d+)-'
        match = re.match(pattern, hostname_lower)
        
        if not match:
            self.logger.debug(
                f"Skipping lease {lease.ip_address}: hostname '{lease.hostname}' "
                f"doesn't match site-cabinet convention"
            )
            return None
        
        site = match.group(1)
        cabinet = f"cab{match.group(2)}"
        
        return site, cabinet
    
    def _query_lease_details(self, ip_address: str, lease_details_cache: dict) -> dict:
        """
        Query database for lease MAC/hostname or use cached metadata.
        
        Args:
            ip_address: IP address to query
            lease_details_cache: Cached lease details keyed by MAC address
            
        Returns:
            Dict with mac, hostname, manufacturer
        """
        if not self.db_enabled:
            return {'mac': '', 'hostname': '', 'manufacturer': ''}
        
        try:
            import psycopg2
            
            # Convert IP to bigint for database query
            ip_parts = ip_address.split('.')
            ip_bigint = (int(ip_parts[0]) * 256**3 + 
                        int(ip_parts[1]) * 256**2 + 
                        int(ip_parts[2]) * 256 + 
                        int(ip_parts[3]))
            
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
                user=self.db_user,
                password=self.db_password
            )
            
            try:
                with conn.cursor() as cur:
                    # Query lease4 table for MAC and hostname
                    cur.execute(
                        "SELECT encode(hwaddr, 'hex'), hostname FROM lease4 WHERE address = %s",
                        (ip_bigint,)
                    )
                    result = cur.fetchone()
                    
                    if result:
                        mac_hex, hostname = result
                        # Format MAC with colons
                        mac = ':'.join([mac_hex[i:i+2] for i in range(0, len(mac_hex), 2)]).lower()
                        hostname = hostname or ''
                        manufacturer = self._detect_manufacturer(hostname) if hostname else ''
                        
                        return {
                            'mac': mac,
                            'hostname': hostname,
                            'manufacturer': manufacturer
                        }
            finally:
                conn.close()
                
        except Exception as e:
            self.logger.debug(f"Could not query lease details for {ip_address}: {e}")
        
        return {'mac': '', 'hostname': '', 'manufacturer': ''}
    
    def _detect_manufacturer(self, hostname: str) -> str:
        """
        Detect BMC manufacturer from hostname suffix.
        
        Args:
            hostname: BMC hostname (e.g., us3-cab10-ru17-idrac)
            
        Returns:
            Manufacturer name: 'Dell', 'HP', 'Supermicro', or 'Unknown'
        """
        if not hostname:
            return 'Unknown'
        
        hostname_lower = hostname.lower()
        
        if hostname_lower.endswith('-idrac') or 'idrac' in hostname_lower:
            return 'Dell'
        elif hostname_lower.endswith('-ilo') or 'ilo' in hostname_lower:
            return 'HP'
        elif hostname_lower.endswith('-bmc') or hostname_lower.endswith('bmc'):
            return 'Supermicro'
        else:
            return 'Unknown'
    
    def generate_batch_inventory(self, leases: List[DHCPLease]) -> Optional[Path]:
        """
        Generate or update consolidated Ansible inventory file for leases.
        
        Groups leases by site and cabinet, appends new IPs to existing files.
        Only processes leases that match site-cabinet naming convention.
        
        Args:
            leases: List of DHCPLease objects to consolidate
            
        Returns:
            Path to generated/updated inventory file, or None if no valid leases
        """
        if not leases:
            self.logger.debug("No leases to process")
            return None
        
        # Group leases by site-cabinet
        grouped_leases: Dict[tuple[str, str], List[DHCPLease]] = {}
        
        for lease in leases:
            result = self._extract_site_and_cabinet(lease)
            if result:
                site, cabinet = result
                key = (site, cabinet)
                if key not in grouped_leases:
                    grouped_leases[key] = []
                grouped_leases[key].append(lease)
        
        if not grouped_leases:
            self.logger.warning(
                f"No leases matched site-cabinet convention. "
                f"Skipped {len(leases)} lease(s) with invalid/missing hostnames."
            )
            return None
        
        # Process each site-cabinet group
        updated_files = []
        for (site, cabinet), group_leases in grouped_leases.items():
            output_file = self._update_cabinet_inventory(site, cabinet, group_leases)
            if output_file:
                updated_files.append(output_file)
        
        # Return the last updated file (for backward compatibility)
        return updated_files[-1] if updated_files else None
    
    def _update_cabinet_inventory(self, site: str, cabinet: str, leases: List[DHCPLease]) -> Optional[Path]:
        """
        Update inventory file for a specific site-cabinet combination.
        
        Args:
            site: Site prefix (e.g., 'us3')
            cabinet: Cabinet ID (e.g., 'cab10')
            leases: List of DHCPLease objects for this cabinet
            
        Returns:
            Path to updated inventory file
        """
        # Generate filename: {site}-{cabinet}-discovery.yml
        output_file = self.output_dir / f"{site}-{cabinet}-discovery.yml"
        
        # Track if this is a new cabinet file
        is_new_cabinet = not output_file.exists()
        
        # Load existing inventory if file exists
        # Build map: IP -> {mac, hostname, manufacturer}
        existing_bmc_map = {}
        if output_file.exists():
            try:
                with open(output_file, 'r') as f:
                    existing_inventory = yaml.safe_load(f)
                    if existing_inventory and 'bmc_targets' in existing_inventory:
                        # Check format: new format has mac/hostname in bmc_targets
                        # Old format has them in metadata['leases']
                        if existing_inventory['bmc_targets'] and 'mac' in existing_inventory['bmc_targets'][0]:
                            # New format: load directly
                            for target in existing_inventory['bmc_targets']:
                                existing_bmc_map[target['ip']] = {
                                    'mac': target.get('mac', ''),
                                    'hostname': target.get('hostname', ''),
                                    'manufacturer': target.get('manufacturer', '')
                                }
                        else:
                            # Old format: IPs in bmc_targets, details in metadata['leases']
                            # Build IP list first
                            ip_list = [target['ip'] for target in existing_inventory['bmc_targets']]
                            
                            # Get lease details from metadata if available
                            lease_details = {}
                            if 'metadata' in existing_inventory and 'leases' in existing_inventory['metadata']:
                                for lease_info in existing_inventory['metadata']['leases']:
                                    mac = lease_info.get('mac', '')
                                    lease_details[mac] = {
                                        'hostname': lease_info.get('hostname', ''),
                                        'manufacturer': lease_info.get('manufacturer', '')
                                    }
                            
                            # Query database for each IP to get MAC/hostname
                            for ip in ip_list:
                                existing_bmc_map[ip] = self._query_lease_details(ip, lease_details)
                                
                self.logger.debug(f"Loaded existing inventory: {len(existing_bmc_map)} IPs")
            except Exception as e:
                self.logger.warning(f"Failed to load existing inventory {output_file}: {e}")
        
        # Add new leases and track them for output
        new_lease_count = 0
        new_hostnames = []
        
        for lease in leases:
            if lease.ip_address not in existing_bmc_map:
                # New BMC discovered
                existing_bmc_map[lease.ip_address] = {
                    'mac': lease.mac_address,
                    'hostname': lease.hostname or '',
                    'manufacturer': self._detect_manufacturer(lease.hostname) if lease.hostname else ''
                }
                new_lease_count += 1
                
                # Track hostname for display
                if lease.hostname:
                    new_hostnames.append(lease.hostname)
                    
                    # Create static reservation in database
                    self.create_static_reservation(lease)
        
        # Build bmc_targets list with all details
        bmc_targets = []
        for ip in existing_bmc_map.keys():
            details = existing_bmc_map[ip]
            target = {'ip': ip}
            
            # Add optional fields only if they exist
            if details['mac']:
                target['mac'] = details['mac']
            if details['hostname']:
                target['hostname'] = details['hostname']
                # Add formatted rack unit display
                rack_unit_display = self._format_rack_unit(details['hostname'])
                if rack_unit_display:
                    target['rack_unit'] = rack_unit_display
            if details['manufacturer']:
                target['manufacturer'] = details['manufacturer']
            
            bmc_targets.append(target)
        
        # Validate for conflicts before sorting
        self._validate_bmc_conflicts(bmc_targets, site, cabinet)
        
        # Sort by rack unit (descending: highest to lowest)
        # Targets without hostnames go to the end, sorted by IP
        bmc_targets.sort(
            key=lambda x: (
                self._extract_rack_unit(x.get('hostname', '')) if x.get('hostname') else -1,
                x['ip']
            ),
            reverse=True
        )
        
        inventory = {
            'bmc_targets': bmc_targets,
            'metadata': {
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'source': 'kea_lease_monitor',
                'site': site,
                'cabinet': cabinet,
                'total_count': len(bmc_targets)
            }
        }
        
        try:
            with open(output_file, 'w') as f:
                yaml.dump(inventory, f, default_flow_style=False, sort_keys=False)
            
            if new_lease_count > 0:
                if is_new_cabinet:
                    # New cabinet discovered
                    self.logger.info(f"Discovered New Devices In: {site.upper()}-{cabinet.upper()}")
                    # Sort devices by rack unit (highest to lowest)
                    sorted_hostnames = sorted(
                        new_hostnames,
                        key=lambda h: self._extract_rack_unit(h),
                        reverse=True
                    )
                    self.logger.info(f"Devices: {sorted_hostnames}")
                    self.logger.info(f"Devices added to: {output_file.name}")
                else:
                    # Existing cabinet, new devices added
                    self.logger.info(f"Discovered New Devices In: {site.upper()}-{cabinet.upper()}")
                    self.logger.info(f"Devices: {new_hostnames}")
                    self.logger.info(f"Devices added to: {output_file.name}")
            else:
                self.logger.debug(f"No new leases for {site.upper()}-{cabinet.upper()}")
            
            return output_file
        
        except Exception as e:
            self.logger.error(f"Failed to write inventory {output_file}: {e}")
            raise


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging for lease monitor."""
    logger = logging.getLogger("kea_lease_monitor")
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
    """Main entry point for Kea lease monitor."""
    parser = argparse.ArgumentParser(
        description="Monitor Kea DHCP leases and trigger bare-metal discovery",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Monitor default lease file
  python3 kea_lease_monitor.py
  
  # With static reservations (database mode)
  export KEA_DB_PASSWORD="your_password"
  python3 kea_lease_monitor.py --db-host localhost --db-user kea
  
  # Sync existing leases to database on startup
  export KEA_DB_PASSWORD="your_password"
  python3 kea_lease_monitor.py --db-host localhost --db-user kea --sync-existing
  
  # Custom lease file and output directory
  python3 kea_lease_monitor.py --lease-file /var/lib/kea/kea-leases4.csv --output-dir /tmp/discovery
  
  # Filter specific subnets with debug logging
  python3 kea_lease_monitor.py --subnet-filter 10,20,30 --log-level DEBUG
  
  # One-time scan (no continuous monitoring)
  python3 kea_lease_monitor.py --once
        """
    )
    
    parser.add_argument(
        '--lease-file',
        type=Path,
        default=Path('/var/lib/kea/kea-leases4.csv'),
        help='Path to Kea lease CSV file (default: /var/lib/kea/kea-leases4.csv)'
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path('/var/lib/kea/discovery'),
        help='Output directory for inventory files (default: /var/lib/kea/discovery)'
    )
    parser.add_argument(
        '--subnet-filter',
        help='Comma-separated subnet IDs to monitor (default: all subnets)'
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
        help='Process leases once and exit (no continuous monitoring)'
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )
    parser.add_argument(
        '--use-database-events',
        action='store_true',
        help='Use PostgreSQL NOTIFY/LISTEN for event-driven processing (requires --db-host)'
    )
    
    # Database configuration for static reservations
    db_group = parser.add_argument_group('Database Options (Static Reservations)')
    db_group.add_argument(
        '--db-host',
        help='PostgreSQL host for static reservations (enables database mode)'
    )
    db_group.add_argument(
        '--db-port',
        type=int,
        default=5432,
        help='PostgreSQL port (default: 5432)'
    )
    db_group.add_argument(
        '--db-name',
        default='kea',
        help='PostgreSQL database name (default: kea)'
    )
    db_group.add_argument(
        '--db-user',
        help='PostgreSQL username'
    )
    db_group.add_argument(
        '--db-password',
        help='PostgreSQL password (can also use KEA_DB_PASSWORD env var)'
    )
    db_group.add_argument(
        '--subnet-id',
        type=int,
        default=1,
        help='DHCP subnet ID for reservations (default: 1)'
    )
    db_group.add_argument(
        '--sync-existing',
        action='store_true',
        help='Sync existing leases from memfile to database on startup (database mode only)'
    )
    
    # DNS configuration for event-driven DNS record creation
    dns_group = parser.add_argument_group('DNS Options (Event-Driven Record Creation)')
    dns_group.add_argument(
        '--enable-dns',
        action='store_true',
        help='Enable DNS record creation (transactional with database reservations)'
    )
    dns_group.add_argument(
        '--dns-zone',
        help='DNS zone for record creation (e.g., site.com)'
    )
    dns_group.add_argument(
        '--dns-scope',
        default='internal',
        choices=['internal', 'external'],
        help='DNS scope - internal or external (default: internal)'
    )
    
    # Vault configuration for credential management
    vault_group = parser.add_argument_group('Vault Options (Credential Management)')
    vault_group.add_argument(
        '--use-vault',
        action='store_true',
        help='Retrieve credentials from Vault (requires VAULT_ADDR and VAULT_TOKEN env vars)'
    )
    
    args = parser.parse_args()
    
    # Get database password from env var or Vault
    if args.db_host and not args.db_password:
        if args.use_vault:
            # Retrieve from Vault if enabled
            try:
                import vault_credentials
                vault_client = vault_credentials.get_vault_client()
                db_creds = vault_credentials.get_kea_database_credentials(vault_client)
                args.db_password = db_creds['db_password']
            except Exception as e:
                print(f"Failed to retrieve database password from Vault: {e}", file=sys.stderr)
                return 1
        else:
            args.db_password = os.environ.get('KEA_DB_PASSWORD')
    
    # Setup logging
    logger = setup_logging(args.log_level)
    
    logger.debug("Starting Kea DHCP lease monitor")
    logger.debug(f"Lease file: {args.lease_file}")
    logger.debug(f"Output directory: {args.output_dir}")
    
    if args.subnet_filter:
        logger.debug(f"Subnet filter: {args.subnet_filter}")
    
    try:
        # Initialize lease source based on mode
        if args.use_database_events:
            if not args.db_host:
                logger.error("--use-database-events requires --db-host to be specified")
                return 1
            
            logger.info("Using event-driven database NOTIFY/LISTEN mode")
            lease_source = DatabaseLeaseSource(
                db_host=args.db_host,
                db_port=args.db_port,
                db_name=args.db_name,
                db_user=args.db_user,
                db_password=args.db_password,
                subnet_id=int(args.subnet_filter) if args.subnet_filter and args.subnet_filter.isdigit() else None,
                logger=logger,
                timeout=args.poll_interval
            )
        else:
            logger.info("Using file-based polling mode")
            lease_source = FileLeaseSource(args.lease_file, logger, args.subnet_filter)
        
        processor = LeaseProcessor(
            args.output_dir, 
            logger,
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=args.db_password,
            subnet_id=args.subnet_id,
            sync_existing=args.sync_existing,
            enable_dns=args.enable_dns,
            dns_zone=args.dns_zone,
            dns_scope=args.dns_scope,
            use_vault=args.use_vault
        )
        
        # Sync existing leases to database if requested (file mode only)
        if args.sync_existing and processor.db_enabled and not args.use_database_events:
            logger.info("Performing initial sync of existing leases...")
            all_leases = lease_source.get_all_leases()
            processor.sync_existing_leases(all_leases)
            
            # Mark all as processed to avoid re-processing during monitoring
            for lease in all_leases:
                lease_source.mark_processed(lease)
        
        # DNS consistency check - sync existing database reservations with DNS
        if processor.enable_dns and processor.use_vault and processor.db_enabled:
            processor.sync_dns_records()
        
        # Monitor loop
        iteration = 0
        while True:
            iteration += 1
            logger.debug(f"Polling iteration {iteration}")
            
            # Get new leases
            new_leases = lease_source.get_new_leases()
            
            if new_leases:
                try:
                    # Generate/update consolidated batch inventory
                    inventory_file = processor.generate_batch_inventory(new_leases)
                    
                    # Mark all leases as processed
                    for lease in new_leases:
                        lease_source.mark_processed(lease)
                    
                    if not inventory_file:
                        logger.info(f"Processed {len(new_leases)} lease(s) - no valid site-cabinet matches")
                
                except Exception as e:
                    logger.error(f"[ERROR] Failed to generate batch inventory: {e}")
            
            # Exit if one-time scan
            if args.once:
                break
            
            # Sleep before next poll
            time.sleep(args.poll_interval)
    
    except KeyboardInterrupt:
        logger.debug("Shutting down lease monitor (Ctrl+C)")
        if isinstance(lease_source, DatabaseLeaseSource):
            lease_source.close()
        return 0
    
    except Exception as e:
        logger.error(f"[ERROR] Fatal error: {e}")
        if isinstance(lease_source, DatabaseLeaseSource):
            lease_source.close()
        return 1
    
    finally:
        if args.use_database_events and isinstance(lease_source, DatabaseLeaseSource):
            lease_source.close()
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
