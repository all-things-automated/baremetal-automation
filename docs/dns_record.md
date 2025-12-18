# DNS Record Creation Integration Plan - EfficientIP SOLIDserver

## Executive Summary

**Status**: Planning phase complete with **existing implementation patterns identified** [OK]

**Key Finding**: The organization already has production-proven Python scripts for SOLIDserver DNS management in `cloudops-pythonscripts/scripts/EIP/`. These scripts provide complete, battle-tested patterns for:
- Connection handling with retry logic (solidserver_connection.py)
- DNS record creation (dns-add.py)
- DNS validation (dns-validate.py)
- Error handling (SDSEmptyError, SDSError, connection retries)

**Implementation Approach**: Copy/adapt proven patterns from existing scripts rather than building from scratch. This significantly reduces risk and development time.

**Timeline**: 2-3 weeks (reduced from 4-6 weeks due to existing patterns)

**API Library**: `SOLIDserverRest==2.3.9` (already in production use)

**Current Host**: 172.30.16.141 (production SOLIDserver)

---

## Overview

This document outlines the integration plan for automating DNS "A" record creation in EfficientIP SOLIDserver when the Discovery Server detects new BMC hostnames from DHCP leases.

**Goal**: Extend `bmc_dns_watcher.py` to automatically create forward DNS "A" records in SOLIDserver when new BMC devices are discovered, eliminating manual DNS record creation.

**Current State**: 
- Kea DHCP assigns IP addresses to BMCs
- `kea_lease_monitor.py` generates discovery inventories with hostname/IP mappings
- `bmc_dns_watcher.py` monitors inventories and reports new hostnames
- **Gap**: DNS records must be manually created in SOLIDserver
- **Discovery**: Existing SOLIDserver scripts provide complete implementation patterns

**Target State**: 
- Automated DNS "A" record creation upon BMC discovery
- Integration with EfficientIP SOLIDserver using proven library patterns
- Error handling and retry logic for failed DNS operations (from existing scripts)
- Audit trail of all DNS record operations
- Non-blocking design (DNS failures don't stop discovery workflow)

---

## Current Workflow Analysis

### Existing Flow (As-Is)

```
┌──────────────────┐
│  New BMC         │
│  Powers On       │
└────────┬─────────┘
         │
         |
┌──────────────────┐
│  Kea DHCP        │
│  Grants Lease    │
│  (IP assigned)   │
└────────┬─────────┘
         │
         |
┌──────────────────────────────────┐
│  kea_lease_monitor.py            │
│  - Detects new lease             │
│  - Extracts site/cabinet/RU      │
│  - Generates discovery inventory │
│  - Writes YAML artifact          │
└────────┬─────────────────────────┘
         │
         |
┌──────────────────────────────────┐
│  bmc_dns_watcher.py              │
│  - Polls inventory directory     │
│  - Detects new/changed files     │
│  - Extracts hostname/IP pairs    │
│  - Validates hostname format     │
│  - Reports to logs               │
└────────┬─────────────────────────┘
         │
         |
┌──────────────────────────────────┐
│  MANUAL STEP (GAP)               │
│  - Administrator creates DNS     │
│    "A" record in SOLIDserver UI  │
│  - hostname -> IP mapping        │
└────────┬─────────────────────────┘
         │
         |
┌──────────────────────────────────┐
│  Discovery Workflow Continues    │
│  - Redfish API queries           │
│  - NetBox registration           │
└──────────────────────────────────┘
```

### Target Flow (To-Be)

```
┌──────────────────┐
│  New BMC         │
│  Powers On       │
└────────┬─────────┘
         │
         |
┌──────────────────┐
│  Kea DHCP        │
│  Grants Lease    │
└────────┬─────────┘
         │
         |
┌──────────────────────────────────┐
│  kea_lease_monitor.py            │
│  (no changes required)           │
└────────┬─────────────────────────┘
         │
         |
┌──────────────────────────────────┐
│  bmc_dns_watcher.py              │
│  - Polls inventory directory     │
│  - Detects new hostnames         │
│  - Validates hostname/IP         │
│  ┌──────────────────────────┐   │
│  │ NEW: SOLIDserver API     │   │
│  │ - Create DNS A record    │   │
│  │ - Verify creation        │   │
│  │ - Handle errors/retries  │   │
│  │ - Log all operations     │   │
│  └──────────────────────────┘   │
└────────┬─────────────────────────┘
         │
         |
┌──────────────────────────────────┐
│  Discovery Workflow Continues    │
│  (fully automated)               │
└──────────────────────────────────┘
```

---

## EfficientIP SOLIDserver API - Confirmed Implementation Details

### API Information (From Existing Scripts)

**[OK] CONFIRMED**: Based on existing `dns-add.py` and `solidserver_connection.py` scripts:

1. **API Library & Connection**
   - **Library**: `SOLIDserverRest==2.3.9` (Python package)
   - **Base URL**: `https://172.30.16.141` (current production)
   - **Authentication**: Native method with username/password
   - **Connection Method**: `sdsadv.SDS(ip_address=host, user=login, pwd=password)`
   - **Module**: Uses `SOLIDserverRest.adv` for advanced operations

2. **DNS Record Creation Pattern**
   - **Library Objects**:
     - `sdsadv.DNS()` - Represents DNS server
     - `sdsadv.DNS_zone()` - Represents DNS zone
     - `sdsadv.DNS_rr()` - Represents DNS resource record
   - **Required Steps**:
     1. Create DNS server object
     2. Create DNS zone object and link to server
     3. Get zone ID via `dns_zone_list` query
     4. Refresh both objects (required by API)
     5. Create RR object with zone linkage
     6. Call `.create()` method

3. **DNS Zone Management**
   - **Zone Lookup Query**: `sds.query("dns_zone_list", parameters)`
   - **Parameters**: `WHERE dns_name = '{server}' AND dnszone_name = '{zone}'`
   - **Zone ID Required**: Must obtain `dnszone_id` before creating records
   - **Scope Mapping**: Internal vs External DNS servers
     - Internal: `dns-internal-smart.site.com` (adapt for BMC zones)
     - External: `dns-external-smart.site.com` (adapt for BMC zones)

4. **Record Validation/Lookup**
   - **Endpoint**: `sds.query("dns_rr_list", parameters)`
   - **Check Existing**: Query before create to prevent duplicates
   - **Query Parameters**: 
     ```python
     WHERE rr_full_name = '{name}.{zone}' 
     AND dns_name = '{dns_server}' 
     AND dnszone_name = '{zone}'
     ```
   - **Exception Handling**: `SDSEmptyError` when no records found (expected for new records)

5. **Error Handling Patterns**
   - **Connection Retries**: Already implemented in `solidserver_connection.py`
     - 3 attempts with exponential backoff
     - Retry on timeout/connection errors
     - Skip retry on auth failures
   - **Common Errors**:
     - `SDSEmptyError`: No records found (expected)
     - `SDSError`: API/connection failures
     - Timeout errors: Handled with retry logic
   - **Exit Codes** (from dns-add.py):
     - 0: Success
     - 2: Connection failure
     - 5: Record already exists
     - 10: Query failed
     - 11: Zone not found
     - 13: DNS object refresh failed

6. **Authentication & Authorization**
   - **Current Account**: `ipmadmin` (production)
   - **Password Storage**: Base64 encoded in `.env` file
   - **Required Permissions**: DNS record create/update (already granted)
   - **Single Account**: Works across all zones (no per-site accounts needed)

### Quick Reference: Key Patterns to Copy

**From `solidserver_connection.py`**:
```python
# Connection with retry logic (copy lines 90-130)
for attempt in range(max_retries):
    try:
        sds = sdsadv.SDS(ip_address=host, user=login, pwd=password)
        sds.connect(method="native")
        return sds
    except SDSError as e:
        # Retry on timeout/connection errors only
        if any(keyword in str(e).lower() for keyword in ['timeout', 'connection']):
            time.sleep(retry_delay * (1.5 ** attempt))
```

**From `dns-add.py`**:
```python
# Zone ID lookup (copy lines 200-220)
parameters = {"WHERE": f"dns_name = '{server}' AND dnszone_name = '{zone}'"}
zones = sds.query("dns_zone_list", parameters, timeout=60)
zone_id = zones[0]['dnszone_id']

# Record creation 5-step pattern (copy lines 230-260)
ss_dns = sdsadv.DNS(name=dns_server_name, sds=sds)
dns_zone = sdsadv.DNS_zone(sds=sds, name=zone)
dns_zone.set_dns(ss_dns)
dns_zone.myid = zone_id
ss_dns.refresh()       # REQUIRED
dns_zone.refresh()     # REQUIRED
dns_rr = sdsadv.DNS_rr(name=hostname, rr_type="A", value1=ip_address, sds=sds)
dns_rr.set_dnszone(dns_zone)
dns_rr.create()

# Check existing record (copy lines 110-125)
parameters = {"WHERE": f"rr_full_name = '{fqdn}' AND dns_name = '{server}' AND dnszone_name = '{zone}'"}
try:
    records = sds.query("dns_rr_list", parameters, timeout=60)
    return len(records) > 0
except SDSEmptyError:
    return False  # No records found (expected for new records)
```

**From `.env` pattern**:
```bash
# Copy .env pattern (cloudops-pythonscripts/scripts/EIP/.env)
SDS_HOST="172.30.16.141"
SDS_LOGIN="ipmadmin"
SDS_HASH="base64_encoded_password"
```

**Files to reference during implementation**:
- `cloudops-pythonscripts/scripts/EIP/solidserver_connection.py` - Connection/retry logic
- `cloudops-pythonscripts/scripts/EIP/dns-add.py` - Record creation pattern
- `cloudops-pythonscripts/scripts/EIP/dns-validate.py` - Query patterns
- `cloudops-pythonscripts/scripts/EIP/.env` - Configuration pattern
- `cloudops-pythonscripts/scripts/EIP/requirements.txt` - Python dependencies

---

## Architecture Design

### Component: DNS Record Manager Class

**New Python Module**: `python/src/baremetal/solidserver_dns.py`

**Purpose**: Encapsulate all SOLIDserver API interactions for DNS record management.

**Responsibilities**:
- Authenticate with SOLIDserver API
- Create DNS "A" records
- Verify record creation
- Handle API errors and retries
- Provide idempotent operations (safe to re-run)
- Log all API interactions

**Design Principles**:
- **Separation of Concerns**: DNS logic separate from inventory watching
- **Testability**: Mock API for unit tests
- **Error Resilience**: Graceful degradation if DNS unavailable
- **Auditability**: Complete logging of all DNS operations

### Class Structure (Based on Existing Patterns)

**Reference Implementation**: See `dns-add.py` and `solidserver_connection.py` for proven patterns.

```python
from SOLIDserverRest import *
from SOLIDserverRest import adv as sdsadv
from SOLIDserverRest.Exception import SDSEmptyError, SDSError
import logging
from typing import Dict, Optional, Tuple
import time

class SOLIDserverClient:
    """Client for EfficientIP SOLIDserver DNS API operations.
    
    Wraps SOLIDserverRest library for BMC DNS record management.
    Based on proven patterns from existing dns-add.py implementation.
    """
    
    def __init__(self, host: str, username: str, password: str, 
                 dns_server_name: str, max_retries: int = 3, retry_delay: int = 2):
        """Initialize SOLIDserver API client.
        
        Args:
            host: SOLIDserver IP/hostname (e.g., "172.30.16.141")
            username: API username (e.g., "ipmadmin")
            password: API password (decoded, not base64)
            dns_server_name: DNS server name in SOLIDserver 
                            (e.g., "bmc-internal.site.com" - adapt from existing)
            max_retries: Connection retry attempts (default: 3)
            retry_delay: Base delay between retries in seconds (default: 2)
        """
        self.host = host
        self.username = username
        self.password = password
        self.dns_server_name = dns_server_name
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.sds: Optional[sdsadv.SDS] = None
    
    def connect(self) -> bool:
        """Establish connection to SOLIDserver API with retry logic.
        
        Pattern from solidserver_connection.py:
        - Retry on timeout/connection errors
        - Skip retry on auth failures
        - Exponential backoff
        
        Returns:
            bool: True if connected successfully
            
        Raises:
            ConnectionError: After all retry attempts fail
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                logging.debug(f"Connecting to SOLIDserver at {self.host} (attempt {attempt + 1}/{self.max_retries})")
                self.sds = sdsadv.SDS(ip_address=self.host, user=self.username, pwd=self.password)
                self.sds.connect(method="native")
                logging.info(f"Connected to SOLIDserver on attempt {attempt + 1}")
                return True
                
            except SDSError as e:
                last_error = e
                error_msg = str(e).lower()
                
                # Retry on connection/timeout errors only
                if any(keyword in error_msg for keyword in ['timeout', 'connection', 'unreachable', 'refused']):
                    if attempt < self.max_retries - 1:
                        sleep_time = self.retry_delay * (1.5 ** attempt)
                        logging.warning(f"Connection attempt {attempt + 1} failed: {e}")
                        logging.info(f"Retrying in {sleep_time:.1f} seconds...")
                        time.sleep(sleep_time)
                    else:
                        logging.error(f"All {self.max_retries} connection attempts failed")
                else:
                    logging.error(f"Connection failed with non-retryable error: {e}")
                    break
                    
            except Exception as e:
                last_error = e
                logging.error(f"Unexpected connection error: {e}")
                break
        
        raise ConnectionError(f"Failed to connect to SOLIDserver: {last_error}")
    
    def create_dns_record(self, hostname: str, ip_address: str, zone: str) -> Tuple[bool, str]:
        """Create DNS A record in SOLIDserver.
        
        Pattern from dns-add.py:
        1. Check if record exists (prevent duplicates)
        2. Get zone ID (API quirk - required despite unique zone name)
        3. Create DNS objects and link them
        4. Refresh objects (REQUIRED by API)
        5. Create resource record
        
        Args:
            hostname: Short hostname (e.g., "us3-cab01-u01-bmc")
            ip_address: IPv4 address (e.g., "172.30.19.42")
            zone: DNS zone name (e.g., "bmc.us3.example.com")
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self.sds:
            return False, "Not connected to SOLIDserver"
        
        fqdn = f"{hostname}.{zone}"
        
        try:
            # Step 1: Check if record already exists (idempotency)
            if self.record_exists(hostname, zone):
                return False, f"Record {fqdn} already exists"
            
            # Step 2: Get zone ID (required by SOLIDserver API)
            zone_id = self._get_zone_id(zone)
            if not zone_id:
                return False, f"Zone {zone} not found"
            
            # Step 3: Set up DNS objects (pattern from dns-add.py)
            ss_dns = sdsadv.DNS(name=self.dns_server_name, sds=self.sds)
            dns_zone = sdsadv.DNS_zone(sds=self.sds, name=zone)
            dns_zone.set_dns(ss_dns)
            dns_zone.myid = zone_id
            
            # Step 4: Refresh objects (REQUIRED - API doesn't work without this)
            ss_dns.refresh()
            dns_zone.refresh()
            
            # Step 5: Create the A record
            dns_rr = sdsadv.DNS_rr(
                name=hostname,
                rr_type="A",
                value1=ip_address,
                sds=self.sds
            )
            dns_rr.set_dnszone(dns_zone)
            dns_rr.create()
            
            logging.info(f"Created DNS A record: {fqdn} -> {ip_address}")
            return True, f"Successfully created {fqdn}"
            
        except SDSError as e:
            logging.error(f"SOLIDserver API error creating {fqdn}: {e}")
            return False, f"API error: {e}"
        except Exception as e:
            logging.error(f"Unexpected error creating {fqdn}: {e}")
            return False, f"Unexpected error: {e}"
    
    def record_exists(self, hostname: str, zone: str) -> bool:
        """Check if DNS record already exists.
        
        Pattern from dns-add.py find_record():
        Query dns_rr_list with full name, dns server, and zone.
        
        Args:
            hostname: Short hostname
            zone: DNS zone name
            
        Returns:
            bool: True if record exists
        """
        if not self.sds:
            raise RuntimeError("Not connected to SOLIDserver")
        
        fqdn = f"{hostname}.{zone}"
        parameters = {
            "WHERE": f"rr_full_name = '{fqdn}' AND dns_name = '{self.dns_server_name}' AND dnszone_name = '{zone}'"
        }
        
        try:
            results = self.sds.query("dns_rr_list", parameters, timeout=60)
            return len(results) > 0
        except SDSEmptyError:
            # No records found - this is expected for new records
            return False
        except Exception as e:
            logging.warning(f"Error checking record existence: {e}")
            return False
    
    def _get_zone_id(self, zone: str) -> Optional[str]:
        """Get DNS zone ID (internal helper).
        
        SOLIDserver API quirk: Zone ID is required for record creation
        even though zone name is unique. This helper retrieves it.
        
        Pattern from dns-add.py.
        """
        if not self.sds:
            return None
        
        parameters = {
            "WHERE": f"dns_name = '{self.dns_server_name}' AND dnszone_name = '{zone}'"
        }
        
        try:
            results = self.sds.query("dns_zone_list", parameters, timeout=60)
            if len(results) == 1:
                return results[0]['dnszone_id']
            elif len(results) == 0:
                logging.error(f"Zone {zone} not found")
                return None
            else:
                logging.error(f"Multiple zones found for {zone} (expected 1)")
                return None
        except SDSEmptyError:
            logging.error(f"Zone {zone} does not exist")
            return None
        except Exception as e:
            logging.error(f"Error querying zone ID: {e}")
            return None
    
    def get_zone_for_site(self, site: str) -> str:
        """Determine DNS zone based on site code.
        
        Args:
            site: Site code (us1, us2, us3, us4, dv)
            
        Returns:
            DNS zone name (e.g., 'bmc.us3.example.com')
            
        Note: Zone mapping will be configurable via environment variables:
        SOLIDSERVER_ZONE_MAP_US3=bmc.us3.example.com
        """
        # Default mapping - will be overridden by env vars
        zone_map = {
            'us1': 'bmc.us1.example.com',
            'us2': 'bmc.us2.example.com',
            'us3': 'bmc.us3.example.com',
            'us4': 'bmc.us4.example.com',
            'dv': 'bmc.dv.example.com',
        }
        return zone_map.get(site.lower(), f'bmc.{site.lower()}.example.com')
    
    def validate_record(self, hostname: str, ip_address: str) -> Tuple[bool, str]:
        """Validate record parameters before creation.
        
        Uses existing hostname pattern from bmc_dns_watcher.py:
        (us[1-4]|dv)-cab(\d{2,3})-u(\d{2})-bmc
        
        Args:
            hostname: Short hostname to validate
            ip_address: IP address to validate
            
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        import re
        
        # Validate hostname format (existing pattern from bmc_dns_watcher.py)
        hostname_pattern = r'^(us[1-4]|dv)-cab(\d{2,3})-u(\d{2})-bmc$'
        if not re.match(hostname_pattern, hostname, re.IGNORECASE):
            return False, f"Invalid hostname format: {hostname}"
        
        # Validate IP address format
        ip_pattern = r'^\d{1,3}(\.\d{1,3}){3}$'
        if not re.match(ip_pattern, ip_address):
            return False, f"Invalid IP address format: {ip_address}"
        
        # Validate octets are 0-255
        try:
            octets = [int(x) for x in ip_address.split('.')]
            if not all(0 <= octet <= 255 for octet in octets):
                return False, f"IP address octets out of range: {ip_address}"
        except ValueError:
            return False, f"Invalid IP address: {ip_address}"
        
        return True, ""
    
    def close(self):
        """Clean up API connection (SOLIDserverRest handles cleanup)."""
        if self.sds:
            logging.debug("Closing SOLIDserver connection")
            self.sds = None
```

**Key Implementation Notes:**

1. **Library-Based**: Uses proven `SOLIDserverRest==2.3.9` library (already in requirements.txt)
2. **Connection Retry**: Exponential backoff with 3 attempts (existing solidserver_connection.py pattern)
3. **Zone ID Quirk**: API requires zone ID despite unique zone name - must query first
4. **Refresh Required**: Must call `.refresh()` on DNS/zone objects before creating records (API requirement)
5. **Idempotency**: Always check existence before creation to prevent duplicates
6. **Error Handling**: Catches `SDSEmptyError` (expected), `SDSError` (API), general exceptions

### Integration with bmc_dns_watcher.py

**Modifications Required**:

1. **Import SOLIDserver Client**
   ```python
   from solidserver_dns import SOLIDserverClient
   ```

2. **Add Configuration Parameters**
   - SOLIDserver base URL
   - API credentials (username/password or API key)
   - SSL verification flag
   - Per-site DNS zone mappings
   - DNS record TTL

3. **Initialize Client in InventoryWatcher**
   ```python
   def __init__(self, watch_dir, logger, dns_client: Optional[SOLIDserverClient] = None):
       # ... existing init code ...
       self.dns_client = dns_client
       self.dns_enabled = dns_client is not None
   ```

4. **DNS Record Creation Logic**
   ```python
   def process_new_hostname(self, hostname: str, ip_address: str) -> bool:
       """Process new hostname: validate, create DNS, report."""
       
       # Existing validation
       is_valid, error = self.validate_hostname(hostname)
       if not is_valid:
           return False
       
       # NEW: Create DNS record
       if self.dns_enabled:
           site = self.extract_site_from_hostname(hostname)
           zone = self.dns_client.get_zone_for_site(site)
           
           success, message = self.dns_client.create_dns_record(
               hostname=hostname,
               ip_address=ip_address,
               zone=zone
           )
           
           if success:
               self.logger.info(f"[DNS] Created A record: {hostname}.{zone} -> {ip_address}")
           else:
               self.logger.error(f"[DNS] Failed to create record: {message}")
               # Continue processing (don't block discovery workflow)
       
       # Existing reporting logic
       self.report_hostname(hostname, ip_address)
       return True
   ```

5. **Error Handling Strategy**
   - DNS failures should NOT block discovery workflow
   - Log errors prominently for administrator review
   - Implement retry logic (3 attempts with exponential backoff)
   - Track DNS operation metrics (success/failure counts)

---

## Configuration Management

### Environment Variables

**New Variables** (add to `.env` - based on existing SOLIDserver pattern):

```bash
# ========================================
# EfficientIP SOLIDserver DNS (Based on existing dns-add.py pattern)
# ========================================
# SOLIDserver host (IP or hostname - no https://)
SDS_HOST="172.30.16.141"

# SOLIDserver API credentials
SDS_LOGIN="ipmadmin"

# SOLIDserver password (base64 encoded - same pattern as existing scripts)
# Encode with: echo -n 'your_password' | base64
SDS_HASH="base64_encoded_password_here"

# Connection retry configuration (optional - defaults to 3/2)
SDS_MAX_RETRIES="3"
SDS_RETRY_DELAY="2"

# DNS server name in SOLIDserver (adapt from existing dns-internal-smart.site.com)
# This should be the name of the BMC DNS server in your SOLIDserver
SOLIDSERVER_DNS_SERVER="bmc-internal-smart.site.com"

# Per-site DNS zone mappings (format: SOLIDSERVER_ZONE_MAP_<SITE>)
SOLIDSERVER_ZONE_MAP_US1="bmc.us1.example.com"
SOLIDSERVER_ZONE_MAP_US2="bmc.us2.example.com"
SOLIDSERVER_ZONE_MAP_US3="bmc.us3.example.com"
SOLIDSERVER_ZONE_MAP_US4="bmc.us4.example.com"
SOLIDSERVER_ZONE_MAP_DV="bmc.dv.example.com"

# Enable DNS record creation (set to 'false' to disable)
DNS_AUTO_CREATE="true"
```

**Note on Password Encoding**:
```bash
# The password is base64 encoded (not hashed) - same as existing scripts
echo -n 'your_password' | base64
# Output example: eW91cl9wYXNzd29yZA==

# Add to .env file:
SDS_HASH="eW91cl9wYXNzd29yZA=="
```

**Required Python Package** (already in existing requirements.txt):
```bash
# From cloudops-pythonscripts/scripts/EIP/requirements.txt
SOLIDserverRest==2.3.9
```

### Ansible Role Integration

**Update**: `ansible/roles/kea_deploy/templates/bmc-dns-watcher.service.j2`

**Add Environment Variables to Systemd Service**:

```ini
[Service]
# ... existing settings ...

# SOLIDserver DNS Configuration
Environment="SOLIDSERVER_URL={{ solidserver_url }}"
Environment="SOLIDSERVER_USERNAME={{ solidserver_username }}"
Environment="SOLIDSERVER_PASSWORD={{ solidserver_password }}"
Environment="SOLIDSERVER_VERIFY_SSL={{ solidserver_verify_ssl | default('true') }}"
Environment="DNS_AUTO_CREATE={{ dns_auto_create | default('true') }}"
Environment="DNS_RECORD_TTL={{ dns_record_ttl | default('3600') }}"
Environment="DNS_ZONE_MAP={{ dns_zone_map | to_json }}"
```

**Ansible Variables** (add to `ansible/roles/kea_deploy/defaults/main.yml`):

```yaml
# SOLIDserver DNS integration
solidserver_url: "{{ lookup('env', 'SOLIDSERVER_URL') }}"
solidserver_username: "{{ lookup('env', 'SOLIDSERVER_USERNAME') }}"
solidserver_password: "{{ lookup('env', 'SOLIDSERVER_PASSWORD') }}"
solidserver_verify_ssl: "{{ lookup('env', 'SOLIDSERVER_VERIFY_SSL') | default('true') }}"
dns_auto_create: "{{ lookup('env', 'DNS_AUTO_CREATE') | default('true') }}"
dns_record_ttl: "{{ lookup('env', 'DNS_RECORD_TTL') | default('3600') }}"

# Per-site DNS zone configuration
dns_zone_map:
  us1: "bmc.us1.example.com"
  us2: "bmc.us2.example.com"
  us3: "bmc.us3.example.com"
  us4: "bmc.us4.example.com"
  dv: "bmc.dv.example.com"
```

---

## Implementation Phases

### Phase 1: Research & Design
**Status**: **COMPLETE** [OK] (with existing script analysis)  
**Deliverables**:
- [x] [OK] Document current workflow
- [x] [OK] Identify integration gap (manual DNS record creation)
- [x] [OK] **Analyze existing SOLIDserver scripts** (dns-add.py, solidserver_connection.py, dns-validate.py)
- [x] [OK] **Identify API library**: SOLIDserverRest==2.3.9 (already proven in production)
- [x] [OK] **Document authentication pattern**: sdsadv.SDS with native method
- [x] [OK] **Document record creation pattern**: 5-step process with zone ID lookup
- [x] [OK] **Document connection retry pattern**: exponential backoff (solidserver_connection.py)
- [x] [OK] **Document error handling patterns**: SDSEmptyError, SDSError, timeout retries
- [x] [OK] Design class structure (based on proven dns-add.py patterns)
- [ ] Identify BMC DNS server name in SOLIDserver (e.g., "bmc-internal-smart.site.com")
- [ ] Confirm BMC DNS zone naming (e.g., "bmc.us3.example.com")
- [ ] Review with team

**Duration**: 1-2 days remaining (mostly configuration confirmation)  
**Dependencies**: Network team input on BMC zone names/DNS server name

**Key Finding**: Existing scripts provide complete implementation patterns - no API research needed!

### Phase 2: Core API Client Development
**Status**: Not Started  
**Deliverables**:
- [ ] Create `python/solidserver_dns.py` module (alongside bmc_dns_watcher.py)
- [ ] **Copy/adapt** `SOLIDserverClient` class from planning document
- [ ] **Copy/adapt** `connect()` method from solidserver_connection.py (proven retry logic)
- [ ] **Copy/adapt** `create_dns_record()` method from dns-add.py (5-step pattern)
- [ ] **Copy/adapt** `record_exists()` from dns-add.py find_record()
- [ ] **Copy/adapt** `_get_zone_id()` helper from dns-add.py
- [ ] Implement `get_zone_for_site()` with environment variable zone mapping
- [ ] Implement `validate_record()` (reuse bmc_dns_watcher.py hostname regex)
- [ ] Unit tests with mocked SOLIDserverRest library (pytest with unittest.mock)
- [ ] **Copy** requirements.txt from cloudops-pythonscripts/scripts/EIP/

**Duration**: 2-3 days (mostly copy/adapt proven patterns, not writing from scratch)  
**Dependencies**: Phase 1 complete, test credentials for BMC zones

**Implementation Notes**:
- **Reuse existing library**: SOLIDserverRest==2.3.9 (in production, proven stable)
- **Reuse connection module**: solidserver_connection.py patterns (retry, backoff)
- **Reuse DNS creation pattern**: dns-add.py 5-step process
- **Reuse error handling**: SDSEmptyError/SDSError catching patterns
- **New additions**: Zone mapping via env vars, integration with bmc_dns_watcher validation

### Phase 3: Integration with bmc_dns_watcher
**Status**: Not Started  
**Deliverables**:
- [ ] Modify `bmc_dns_watcher.py` to use SOLIDserver client
- [ ] Add configuration parameter handling
- [ ] Implement DNS creation in hostname processing flow
- [ ] Add error handling and retry logic
- [ ] Update logging for DNS operations
- [ ] Integration tests with test SOLIDserver instance

**Duration**: 2-3 days  
**Dependencies**: Phase 2 complete

### Phase 4: Configuration Management
**Status**: Not Started  
**Deliverables**:
- [ ] Update `.env.example` with SOLIDserver variables
- [ ] Update Ansible role systemd template
- [ ] Add Ansible role variables
- [ ] Update role README with DNS configuration
- [ ] Test deployment with new configuration

**Duration**: 1-2 days  
**Dependencies**: Phase 3 complete

### Phase 5: Testing & Validation
**Status**: Not Started  
**Deliverables**:
- [ ] Unit tests for SOLIDserver client
- [ ] Integration tests (test SOLIDserver instance)
- [ ] End-to-end testing (DHCP → DNS → Discovery)
- [ ] Error scenario testing (API down, auth failure, etc.)
- [ ] Performance testing (multiple concurrent records)
- [ ] Documentation updates

**Duration**: 3-5 days  
**Dependencies**: Phases 1-4 complete

### Phase 6: Production Deployment
**Status**: Not Started  
**Deliverables**:
- [ ] Deploy to US3 production (us3-sprmcr-l01)
- [ ] Monitor for 48 hours
- [ ] Validate DNS records created correctly
- [ ] Deploy to remaining sites (US1, US2, DV)
- [ ] Create operational runbook
- [ ] Train operations team

**Duration**: 1 week (staggered deployment)  
**Dependencies**: Phase 5 complete, production SOLIDserver credentials

---

## Technical Requirements

### Python Dependencies

**New Requirements** (add to `python/requirements.txt`):

```
requests>=2.31.0          # HTTP client for REST API
urllib3>=2.0.0            # URL handling
certifi>=2023.7.22        # SSL certificate verification
```

**Optional Dependencies**:
```
requests-mock>=1.11.0     # For unit testing API calls
pytest>=7.4.0             # Testing framework
```

### SOLIDserver API Access

**Requirements**:
- [ ] SOLIDserver API endpoint URL
- [ ] Service account credentials with DNS write permissions
- [ ] API documentation (REST API reference)
- [ ] Test instance for development/validation
- [ ] Firewall rules: Discovery Server → SOLIDserver HTTPS (443)

**Permissions Required**:
- Read DNS zones
- Create DNS records (A records)
- Update DNS records (for IP changes)
- List existing records (for validation)

### Network Requirements

**Connectivity**:
- Discovery Server → SOLIDserver: HTTPS (TCP 443)
- Must work from all sites (US1, US2, US3, DV)
- Consider multi-site SOLIDserver architecture (single instance or per-site?)

**DNS Zones**:
- Zones must exist in SOLIDserver before automation runs
- Zone names must match configuration (e.g., `bmc.us3.example.com`)
- Zones must allow dynamic record creation

---

## Error Handling & Edge Cases

### Error Scenarios

1. **SOLIDserver API Unavailable**
   - **Handling**: Log error, retry with exponential backoff (3 attempts)
   - **Impact**: DNS record not created, but discovery workflow continues
   - **Resolution**: Manual DNS creation, reprocess when SOLIDserver available

2. **Authentication Failure**
   - **Handling**: Log critical error, disable DNS creation for session
   - **Impact**: All DNS operations fail until credentials fixed
   - **Resolution**: Update credentials, restart bmc-dns-watcher service

3. **Duplicate Record Exists**
   - **Handling**: Check if existing IP matches, update if different
   - **Impact**: None if IP matches, update required if IP changed
   - **Resolution**: Idempotent operation (safe to retry)

4. **Invalid DNS Zone**
   - **Handling**: Log error, skip DNS creation for this hostname
   - **Impact**: Single hostname missing DNS record
   - **Resolution**: Fix zone configuration, manually create record

5. **API Rate Limiting**
   - **Handling**: Implement exponential backoff, respect retry-after headers
   - **Impact**: Delayed DNS record creation
   - **Resolution**: Wait for rate limit reset, retry

6. **Network Timeout**
   - **Handling**: Retry with increased timeout (up to 60 seconds)
   - **Impact**: Delayed DNS record creation
   - **Resolution**: Check network connectivity, retry

7. **Malformed Hostname**
   - **Handling**: Validation catches before API call
   - **Impact**: DNS record not created, logged as validation error
   - **Resolution**: Fix hostname in Kea configuration, rediscover

### Recovery Mechanisms

**State Tracking**:
- Maintain local cache of successfully created DNS records
- Persist cache to disk (JSON file) for restart resilience
- On startup, reconcile cache with SOLIDserver (query existing records)

**Retry Logic**:
```python
def create_dns_record_with_retry(hostname, ip, zone, max_retries=3):
    """Create DNS record with exponential backoff retry."""
    for attempt in range(1, max_retries + 1):
        try:
            success, message = solidserver.create_dns_record(hostname, ip, zone)
            if success:
                return True, message
            
            # If explicit failure (not timeout), don't retry
            if "already exists" in message.lower():
                return True, "Record already exists"
            
        except requests.exceptions.Timeout:
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff: 2, 4, 8 seconds
                logger.warning(f"Timeout on attempt {attempt}, retrying in {wait_time}s")
                time.sleep(wait_time)
            else:
                return False, f"Failed after {max_retries} attempts (timeout)"
        
        except requests.exceptions.RequestException as e:
            return False, f"API error: {str(e)}"
    
    return False, "Max retries exceeded"
```

---

## Monitoring & Observability

### Metrics to Track

**DNS Operation Metrics**:
- Total DNS records created (counter)
- DNS creation success rate (percentage)
- DNS creation failure rate (percentage)
- API response time (histogram)
- Retry attempts (counter)
- Authentication failures (counter)

**Logging Strategy**:

**INFO Level**:
- Successful DNS record creation
- Record already exists (idempotent skip)
- API authentication success

**WARNING Level**:
- Retry attempts
- API timeout (before max retries)
- Non-critical API errors

**ERROR Level**:
- DNS creation failure after retries
- Authentication failure
- Invalid configuration
- API errors that block operations

**Log Format**:
```
[DNS] [hostname] [operation] [result] [details]

Examples:
[DNS] [us3-cab10-ru17-idrac] [CREATE] [SUCCESS] Created A record in zone bmc.us3.example.com -> 172.30.19.42
[DNS] [us3-cab10-ru17-idrac] [CREATE] [SKIPPED] Record already exists with same IP
[DNS] [us3-cab10-ru17-idrac] [CREATE] [ERROR] API timeout after 3 retries
[DNS] [Authentication] [ERROR] Invalid credentials for SOLIDserver API
```

### Alerting Rules

**Critical Alerts** (page immediately):
- DNS creation failure rate > 20% over 1 hour
- Authentication failures (any occurrence)
- SOLIDserver API unavailable for > 15 minutes

**Warning Alerts** (email/Slack):
- DNS creation failure rate > 10% over 1 hour
- High retry rate (> 30% of operations require retry)
- API response time > 5 seconds (p95)

---

## Testing Strategy

### Unit Tests

**Test SOLIDserverClient Class**:
- Authentication success/failure
- DNS record creation (success, duplicate, error)
- Record existence check
- Zone determination logic
- Error handling and retry logic
- Mock all API calls with `requests-mock`

**Test Coverage Target**: > 80%

### Integration Tests

**Test with SOLIDserver Test Instance**:
- Create DNS record end-to-end
- Verify record in SOLIDserver UI
- Test duplicate record handling
- Test record update (IP change)
- Test error scenarios (invalid zone, bad credentials)

**Environment**: Dedicated test SOLIDserver or sandbox zone

### End-to-End Tests

**Complete Workflow**:
1. Power on test BMC (or simulate with test lease)
2. Verify DHCP lease granted
3. Verify discovery inventory created
4. Verify DNS watcher processes hostname
5. Verify DNS record created in SOLIDserver
6. Verify DNS resolution works (`nslookup`)
7. Verify discovery workflow continues (Redfish query)

**Test Sites**: US3 (primary), DV (secondary)

### Performance Tests

**Concurrent DNS Operations**:
- Simulate 10-20 concurrent BMC discoveries
- Measure DNS API response time
- Verify no race conditions or duplicate records
- Monitor API rate limiting

**Load Test**: 50 DNS records in 5 minutes

---

## Security Considerations

### Credential Management

**SOLIDserver Credentials**:
- Store in environment variables (never in code)
- Use dedicated service account (not personal account)
- Minimum required permissions (write DNS records only)
- Rotate credentials quarterly
- Use Ansible Vault for encrypted storage

**Access Control**:
- Restrict service account to specific DNS zones (bmc.*.example.com)
- No delete permissions (only create/update)
- Audit all API operations in SOLIDserver logs

### Network Security

**TLS/SSL**:
- Always use HTTPS for SOLIDserver API
- Validate SSL certificates in production
- Allow self-signed for development only

**Firewall Rules**:
- Restrict Discovery Server outbound to SOLIDserver IP:443
- No inbound access required
- Monitor for unusual API traffic patterns

### Audit Trail

**Logging Requirements**:
- Log all DNS operations (create, update, skip)
- Include timestamp, hostname, IP, user/service account
- Retain logs for 90 days minimum
- Forward logs to central SIEM

**SOLIDserver Audit**:
- Enable audit logging in SOLIDserver
- Correlate DNS watcher logs with SOLIDserver audit logs
- Review regularly for unauthorized changes

---

## Rollout Plan

### Development Environment

**Phase**: Development & Testing  
**Timeline**: Week 1-2

1. Set up test SOLIDserver instance or sandbox zone
2. Develop `solidserver_dns.py` module
3. Unit testing with mocked API
4. Integration testing with test instance
5. Code review and documentation

### Lab Environment

**Phase**: Lab Validation  
**Timeline**: Week 3

1. Deploy to lab Discovery Server (172.30.19.3)
2. Configure with test SOLIDserver credentials
3. End-to-end testing with lab BMCs
4. Verify DNS records created correctly
5. Performance and load testing

### US3 Production (Pilot)

**Phase**: Production Pilot  
**Timeline**: Week 4

1. Deploy to us3-sprmcr-l01 (production Discovery Server)
2. Configure with production SOLIDserver credentials
3. Monitor for 48 hours (limited BMC discoveries expected)
4. Validate DNS records for all new discoveries
5. Review logs for errors or issues
6. Document any issues and resolutions

### Multi-Site Rollout

**Phase**: Full Production  
**Timeline**: Week 5-6

1. Deploy to US1, US2, DV sites sequentially
2. 48-hour monitoring per site before next deployment
3. Validate DNS zones per site configured correctly
4. Train operations team on new functionality
5. Create operational runbook
6. Update monitoring and alerting

### Rollback Plan

**If Issues Occur**:
1. Set `DNS_AUTO_CREATE=false` in environment
2. Restart bmc-dns-watcher service
3. DNS watcher continues monitoring without creating records
4. Manual DNS creation resumes (back to original workflow)
5. Investigate and fix issues
6. Re-enable after validation

---

## Documentation Updates Required

### New Documents

1. **DNS_INTEGRATION.md**: Detailed SOLIDserver integration guide
   - API reference
   - Configuration examples
   - Troubleshooting guide
   - API endpoint documentation

2. **SOLIDSERVER_SETUP.md**: SOLIDserver prerequisites
   - Zone creation
   - Service account setup
   - Permission configuration
   - Network requirements

### Document Updates

1. **Discovery-Server.md**: Add DNS integration section
2. **DEPLOYMENT.md**: Add DNS configuration steps
3. **KEA_DEPLOY_QUICKREF.md**: Add DNS troubleshooting commands
4. **jira-stories.md**: Add DNS integration story
5. **README.md**: Update architecture diagram with DNS component

---

## Questions & Open Items

### SOLIDserver API Specifics

**[OK] RESOLVED** (from existing scripts):
1. ~~What is the exact REST API endpoint?~~ → **Uses SOLIDserverRest library, not raw REST**
2. ~~What authentication method?~~ → **Native method: `sds.connect(method="native")`**
3. ~~What is the request/response format?~~ → **Library abstracts this (Python objects)**
4. ~~How are DNS zones identified?~~ → **Must query for zone ID despite unique zone name (API quirk)**
5. ~~What happens with duplicate records?~~ → **Query first with `dns_rr_list`, skip if exists**
6. ~~Are there API rate limits?~~ → **Not documented in existing scripts (none encountered)**
7. ~~What error codes?~~ → **SDSEmptyError (no records), SDSError (API failures), timeout errors**
8. ~~Bulk/batch API?~~ → **Not used in existing scripts (one record at a time)**

**❓ STILL NEED TO CONFIRM**:
1. What is the BMC DNS server name in SOLIDserver? (e.g., "bmc-internal-smart.site.com")
2. What are the BMC DNS zone names? (e.g., "bmc.us3.example.com")
3. Do BMC zones already exist or do we need to create them?
4. Which SOLIDserver instance for BMC zones? (same 172.30.16.141 or different?)

### Configuration Decisions

**[OK] RESOLVED**:
1. ~~Synchronous or asynchronous?~~ → **Synchronous (simple, proven in dns-add.py)**
2. ~~Cache API responses?~~ → **No caching (existing scripts don't cache)**
3. ~~DNS record TTL?~~ → **Not specified in dns-add.py (uses zone default)**
4. ~~Support record updates?~~ → **Not needed initially (BMC IPs rarely change after discovery)**
5. ~~Implement record deletion?~~ → **Not needed initially (manual cleanup acceptable)**
6. ~~Per-site credentials?~~ → **Single account (ipmadmin works across all zones)**

**❓ STILL NEED TO DECIDE**:
1. Should we add DNS creation metrics to bmc-dns-watcher.service status output?
2. Should DNS failures alert immediately or just log for review?

### Operational Questions

**❓ NEED TO CLARIFY**:
1. Who manages the SOLIDserver service account (ipmadmin)?
2. What is the change approval process for DNS automation?
3. Should we create test BMC zones first or use existing zones?
4. What is the escalation path if SOLIDserver is unavailable?
5. Do we need DR/failover considerations for SOLIDserver?
6. **NEW**: Do Network team approve using same ipmadmin account for BMC automation?

---

## Next Steps

### Immediate Actions (Updated Based on Findings)

1. **~~Research SOLIDserver API~~** [OK] **COMPLETE**
   - [OK] Existing scripts provide complete patterns
   - [OK] Authentication method identified (native)
   - [OK] API library identified (SOLIDserverRest==2.3.9)
   - [OK] Implementation patterns documented

2. **Confirm BMC Zone Configuration** (Network Team)
   - ❓ Identify BMC DNS server name in SOLIDserver
   - ❓ Confirm BMC DNS zone names per site (us1, us2, us3, us4, dv)
   - ❓ Verify zones exist or request creation
   - ❓ Confirm ipmadmin account has permissions for BMC zones
   - ❓ Validate connectivity: Discovery Server → SOLIDserver (172.30.16.141)

3. **Set Up Test Environment**
   - Create test BMC zones (e.g., bmc-test.us3.example.com) or use existing
   - Test ipmadmin credentials from lab Discovery Server (172.30.19.3)
   - Test record creation manually using dns-add.py pattern
   - Validate DNS resolution after record creation

4. **Design Review**
   - Review this plan with Network Team (SOLIDserver owners)
   - Review with Security Team (credentials, permissions)
   - Get approval for using ipmadmin account for automation
   - Finalize BMC zone naming convention
   - Identify any concerns or risks

5. **Create Jira Story**
   - Document as new feature in jira-stories.md
   - Title: "Automate DNS Record Creation via SOLIDserver API"
   - Estimate: 13 story points (complex, but patterns exist)
   - Add to Sprint 4 (Integration sprint)
   - Include testing and documentation tasks

### Development Sequence (After Approvals)

1. **Copy Dependencies**
   - Copy `requirements.txt` from cloudops-pythonscripts/scripts/EIP/
   - Update baremetal project requirements.txt

2. **Create solidserver_dns.py Module**
   - Copy connection pattern from solidserver_connection.py
   - Copy record creation pattern from dns-add.py
   - Adapt for BMC use case (zone mapping, validation)
   - Add unit tests with mocked SOLIDserverRest

3. **Integrate with bmc_dns_watcher.py**
   - Add SOLIDserverClient initialization
   - Add DNS creation call in hostname processing
   - Add error handling (non-blocking)
   - Add DNS operation logging

4. **Update Configuration**
   - Add SDS_* environment variables to .env
   - Update kea_deploy role systemd template
   - Update role README with DNS config examples

5. **Test & Deploy**
   - Unit tests (mocked API)
   - Integration tests (test BMC zones)
   - Deploy to lab (172.30.19.3)
   - Deploy to US3 production (us3-sprmcr-l01)
   - Monitor and validate

---

## Summary

**Key Takeaway**: Existing production scripts eliminate API research phase and provide proven, battle-tested patterns for SOLIDserver integration. Implementation risk is significantly reduced.

**Revised Timeline**: 2-3 weeks (down from 4-6 weeks)

**Critical Path**: Network team confirmation of BMC zone configuration and permissions

**Risk Level**: **LOW** (existing patterns proven in production)

### Success Criteria

**MVP (Minimum Viable Product)**:
- [ ] DNS A records automatically created for new BMCs
- [ ] Integration works on US3 production site
- [ ] Error handling prevents workflow blocking
- [ ] Logging provides visibility into operations
- [ ] Configuration managed via environment variables
- [ ] No manual DNS creation required for successful discoveries

**Full Feature Set**:
- [ ] Multi-site deployment (all sites)
- [ ] Comprehensive error handling and retries
- [ ] Performance metrics and monitoring
- [ ] Complete documentation
- [ ] Operational runbook
- [ ] Team training completed

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| SOLIDserver API unavailable | Low | High | Retry logic, graceful degradation, alerting |
| Authentication issues | Medium | High | Test credentials, fallback to manual, clear docs |
| API rate limiting | Low | Medium | Implement backoff, batch operations if possible |
| DNS zone misconfiguration | Medium | Medium | Validate zones before deployment, clear error messages |
| Network connectivity issues | Low | Medium | Retry logic, timeout handling, monitoring |
| Duplicate record conflicts | Medium | Low | Idempotent operations, check before create |
| Performance degradation | Low | Low | Async operations, connection pooling, caching |

**Overall Risk Level**: **Medium**  
**Mitigation Status**: Acceptable with planned mitigations

---

## Conclusion

This integration will complete the automation pipeline by eliminating the manual DNS record creation step. By leveraging the EfficientIP SOLIDserver REST API, we can automatically create DNS A records as part of the BMC discovery workflow, further reducing time-to-production for new bare-metal servers.

**Key Benefits**:
- Eliminates manual DNS record creation (saves 5-10 minutes per server)
- Reduces human error in DNS management
- Enables fully automated lights-out provisioning
- Provides audit trail of all DNS operations
- Maintains consistency across multi-site deployment

**Next Milestone**: Complete SOLIDserver API research and obtain test credentials.

---

**Document Status**: Planning Phase - Ready for Team Review  
**Last Updated**: December 16, 2025  
**Owner**: Infrastructure Automation Team  
**Reviewers**: Network Team, Security Team, Operations Team
