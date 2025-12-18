#!/usr/bin/env python3
"""SOLIDserver DNS client for BMC record automation.

Simplified wrapper around solidserver_connection.py specifically for
BMC A record creation in site.com zone (internal scope only).
"""

import logging
import os
from typing import Tuple, Optional
from SOLIDserverRest import *
from SOLIDserverRest import adv as sdsadv
from SOLIDserverRest.Exception import SDSEmptyError, SDSError
import solidserver_connection


class BMCDNSClient:
    """SOLIDserver client for BMC DNS records (internal, site.com only)."""
    
    def __init__(self, env_file: str = ".env"):
        """Initialize BMC DNS client from environment variables."""
        # Load config from .env
        self.env_file = env_file
        self.dns_server_name = self._load_env("SOLIDSERVER_DNS_SERVER", "dns-internal-smart.site.com")
        self.zone = self._load_env("DNS_ZONE", "site.com")
        self.sds: Optional[sdsadv.SDS] = None
        
    def _load_env(self, var_name: str, default: str = None) -> str:
        """Load environment variable from .env file."""
        return solidserver_connection.load_env_variable(var_name, self.env_file) or default
        
    def connect(self) -> bool:
        """Connect to SOLIDserver using solidserver_connection module."""
        try:
            self.sds = solidserver_connection.get_connection(self.env_file)
            return True
        except (RuntimeError, ConnectionError) as e:
            logging.error(f"Failed to connect to SOLIDserver: {e}")
            return False
    
    def create_dns_record(self, hostname: str, ip_address: str) -> Tuple[bool, str]:
        """Create BMC A record: hostname.site.com -> ip_address (internal).
        
        Args:
            hostname: Short hostname (e.g., "us3-cab10-ru17-idrac")
            ip_address: IPv4 address (e.g., "172.30.19.42")
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self.sds:
            if not self.connect():
                return False, "Not connected to SOLIDserver"
        
        fqdn = f"{hostname}.{self.zone}"
        
        try:
            # Check if record already exists
            if self.record_exists(hostname):
                logging.info(f"DNS record {fqdn} already exists, skipping")
                return True, f"Record {fqdn} already exists"
            
            # Get zone ID
            zone_id = self._get_zone_id()
            if not zone_id:
                return False, f"Zone {self.zone} not found"
            
            # Create DNS objects (pattern from dns-add.py)
            ss_dns = sdsadv.DNS(name=self.dns_server_name, sds=self.sds)
            dns_zone = sdsadv.DNS_zone(sds=self.sds, name=self.zone)
            dns_zone.set_dns(ss_dns)
            dns_zone.myid = zone_id
            
            # Refresh objects (REQUIRED by API)
            ss_dns.refresh()
            dns_zone.refresh()
            
            # Create A record
            dns_rr = sdsadv.DNS_rr(
                name=hostname,
                rr_type="A",
                value1=ip_address,
                sds=self.sds
            )
            dns_rr.set_dnszone(dns_zone)
            dns_rr.create()
            
            logging.info(f"[DNS] Created A record: {fqdn} -> {ip_address}")
            return True, f"Created {fqdn}"
            
        except SDSError as e:
            logging.error(f"[DNS] SOLIDserver API error: {e}")
            return False, f"API error: {e}"
        except Exception as e:
            logging.error(f"[DNS] Unexpected error: {e}")
            return False, f"Error: {e}"
    
    def record_exists(self, hostname: str) -> bool:
        """Check if DNS record already exists."""
        if not self.sds:
            return False
        
        fqdn = f"{hostname}.{self.zone}"
        parameters = {
            "WHERE": f"rr_full_name = '{fqdn}' AND dns_name = '{self.dns_server_name}' AND dnszone_name = '{self.zone}'"
        }
        
        try:
            results = self.sds.query("dns_rr_list", parameters, timeout=60)
            return len(results) > 0
        except SDSEmptyError:
            return False
        except Exception as e:
            logging.warning(f"[DNS] Error checking record: {e}")
            return False
    
    def _get_zone_id(self) -> Optional[str]:
        """Get DNS zone ID (required by SOLIDserver API)."""
        if not self.sds:
            return None
        
        parameters = {
            "WHERE": f"dns_name = '{self.dns_server_name}' AND dnszone_name = '{self.zone}'"
        }
        
        try:
            results = self.sds.query("dns_zone_list", parameters, timeout=60)
            if len(results) == 1:
                return results[0]['dnszone_id']
            else:
                logging.error(f"Expected 1 zone, got {len(results)}")
                return None
        except SDSEmptyError:
            logging.error(f"Zone {self.zone} not found")
            return None
        except Exception as e:
            logging.error(f"Error querying zone: {e}")
            return None