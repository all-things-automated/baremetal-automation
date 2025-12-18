# Configuration Guide - Values to Update Before Use

This document lists all configuration values that must be updated to match your environment before using this automation framework.

## Overview

The codebase has been generalized to use `site.com` as a placeholder domain. You must replace these placeholders with your actual infrastructure values.

---

## 1. DNS Configuration

### Primary DNS Zone
**Where to update:**
- `.env.example` → `DNS_ZONE`
- `python/.env.example` → `DNS_ZONE`
- `ansible/playbooks/kea_deploy.yml` → `kea_domain_name` and `kea_dns_zone`
- All playbook variable files

**Current placeholder:** `site.com`  
**Update to:** Your actual DNS zone (e.g., `company.com`, `internal.company.com`)

### DNS Server Names
**Where to update:**
- `.env.example` → `SOLIDSERVER_DNS_SERVER`
- `python/.env.example` → `SOLIDSERVER_DNS_SERVER`
- Python source files: `dns-add.py`, `kea_lease_monitor.py`, `solidserver_dns.py`

**Current placeholders:**
- Internal DNS: `dns-internal-smart.site.com`
- External DNS: `dns-primary.site.com`

**Update to:** Your actual SOLIDserver DNS server names

### DNS Examples in Documentation
All documentation files contain example FQDNs and DNS commands that reference `site.com`.

**Files to review:**
- `docs/INFRASTRUCTURE_STANDARDS.md`
- `docs/KEA_DNS_*.md` (all KEA DNS documentation)
- `docs/KEA_WORKFLOW.md`
- `docs/dns_record.md`
- `ansible/roles/*/README.md` (all role documentation)

**Update examples to:** Use your actual DNS zone and server names

---

## 2. HashiCorp Vault Configuration

### Vault Server URL
**Where to update:**
- `.env.example` → `VAULT_ADDR` (if uncommented)
- `docs/INFRASTRUCTURE_STANDARDS.md` → Vault examples
- `docs/KEA_DNS_DEPLOYMENT.md` → Vault setup examples
- `ansible/playbooks/kea_deploy.yml` → `kea_vault_addr`

**Current placeholder:** `https://vault.site.com:8200`  
**Update to:** Your actual Vault server URL

**Note:** This is only needed if you're using HashiCorp Vault for credential management. The framework also supports environment variables and `.env` files.

---

## 3. Contact Information

### Maintainer Email
**Where to update:**
- `spacelift/runner/Dockerfile` → `LABEL maintainer`
- `spacelift/runner/README.md` → Contact section
- `docs/INFRASTRUCTURE_STANDARDS.md` → Contact section

**Current placeholder:** `infrastructure@site.com`  
**Update to:** Your team's contact email

---

## 4. Network Infrastructure

### IP Address Ranges
**Current examples:** `172.30.x.x` (RFC1918 private ranges)

These are **example values** used throughout documentation and test fixtures. Update to match your environment:

**Where to update:**
- `ansible/inventory/*.yml` → Host IP addresses
- `kea_dhcp/kea-dhcp4.conf` → Subnet and pool definitions
- `.env.example` → KEA_SUBNET_CIDR, KEA_POOL_START, KEA_POOL_END, KEA_GATEWAY
- Documentation examples in `docs/`

**Update to:** Your actual BMC management network ranges

### SOLIDserver IP
**Where to update:**
- `python/.env.example` → `SDS_HOST`
- `python/src/baremetal/dns-add.py` → Default value in argument parser
- `python/src/baremetal/kea_lease_monitor.py` → Fallback default values

**Current placeholder:** `172.30.16.141`  
**Update to:** Your SOLIDserver management IP address

---

## 5. BMC Naming Convention

### Hostname Pattern
The automation expects BMC hostnames to follow this pattern:
```
{site}-cab{cabinet}-ru{rack_unit}-{bmc_type}
```

**Examples:**
- `us3-cab10-ru17-idrac` (Dell iDRAC)
- `us3-cab10-ru15-ilo` (HP iLO)

**Where used:**
- Discovery artifact templates
- DNS record creation logic
- NetBox device naming
- Cabinet/rack unit extraction

**Update:** Modify `discovery_artifact.yml.j2` and Python parsing logic if your naming convention differs

### Supported BMC Types
- `idrac` - Dell iDRAC
- `ilo` - HP iLO
- `bmc` - Supermicro BMC (or generic)

**Where to update:** `ansible/roles/discovery/templates/discovery_artifact.yml.j2`

---

## 6. NetBox Configuration

### NetBox Instance URL
**Where to update:**
- `.env.example` → `NETBOX_URL`
- All documentation examples

**Current placeholder:** `https://netbox.example.com`  
**Update to:** Your actual NetBox instance URL

### NetBox API Token
**Where to update:**
- `.env.example` → `NETBOX_TOKEN`

**Required permissions:** `dcim.*`, `extras.*`, `ipam.*`

**Action:** Generate token from NetBox UI (User → API Tokens) and set in `.env`

---

## 7. Database Configuration (Kea DHCP)

### PostgreSQL Connection
**Where to update:**
- `.env` (not committed) → Database credentials
- `ansible/playbooks/kea_deploy.yml` → Database connection variables
- `docs/KEA_DNS_DEPLOYMENT.md` → Example commands

**Required variables:**
- `kea_db_host` - PostgreSQL server hostname/IP
- `kea_db_name` - Database name (default: `kea`)
- `kea_db_user` - Database username (default: `kea`)
- `kea_db_password` - Database password (use Vault or environment variable)

**Default values:** `localhost`, database name `kea`, user `kea`

---

## 8. Site Codes and Data Center Naming

### Site Code Pattern
The automation extracts site codes from BMC hostnames (first component before first hyphen).

**Examples:**
- `us3-cab10-ru17-idrac` → site code: `us3`
- `eu2-cab05-ru10-ilo` → site code: `eu2`

**Where used:**
- Physical identity extraction
- NetBox site mapping
- Inventory file generation

**Update:** Ensure your BMC hostnames follow the expected pattern, or modify extraction logic in:
- `ansible/roles/discovery/templates/discovery_artifact.yml.j2`
- Python scripts parsing BMC names

---

## 9. Testing and Development Values

### Test Artifacts
**Location:** `ansible/artifacts/*.yml`

**Current state:** Contains example discovery artifacts with `site.com` domain

**Action:** 
- These files are gitignored by default
- Delete example files before production use
- New artifacts will be generated with your actual configuration

### Test Fixtures
**Location:** `python/tests/fixtures/`

**Current state:** Contains sample CSV lease data with example values

**Action:** Safe to leave as-is (used for unit testing only)

---

## 10. Optional: Secondary DNS Zone

### Alternative DNS Zone
**Where defined:** `python/src/baremetal/dns-add.py` → `zones` list

**Current value:** `zones = ['site.com', 'erlog.com']`

**Action:** 
- Update `'erlog.com'` to your secondary zone if applicable
- Remove if only using single DNS zone
- This is specific to the `dns-add.py` script for manual DNS record creation

---

## Quick Start Checklist

Before first use, update these critical values:

- [ ] **DNS_ZONE** in `.env.example` and `python/.env.example`
- [ ] **SOLIDSERVER_DNS_SERVER** in `python/.env.example`
- [ ] **NETBOX_URL** in `.env.example`
- [ ] Copy `.env.example` to `.env` and fill in:
  - [ ] BMC_USERNAME
  - [ ] BMC_PASSWORD
  - [ ] NETBOX_TOKEN
  - [ ] SDS_HOST (if different from default)
  - [ ] SDS_LOGIN
  - [ ] SDS_HASH (base64 encoded password)
- [ ] Update `kea_dhcp/kea-dhcp4.conf` with your subnet configuration
- [ ] Update `ansible/inventory/*.yml` with your server IPs
- [ ] Review and update Vault URL if using HashiCorp Vault

---

## Validation Commands

After updating configuration, validate your setup:

### 1. Test BMC Connectivity
```bash
export BMC_USERNAME="admin"
export BMC_PASSWORD="your-password"
curl -k -u $BMC_USERNAME:$BMC_PASSWORD https://<your-bmc-ip>/redfish/v1/
```

### 2. Test NetBox API
```bash
export NETBOX_URL="https://netbox.yourcompany.com"
export NETBOX_TOKEN="your-token"
curl -H "Authorization: Token $NETBOX_TOKEN" $NETBOX_URL/api/
```

### 3. Test DNS Resolution
```bash
# Replace with your DNS server IP and zone
dig @<your-dns-server> <hostname>.yourzone.com
```

### 4. Test SOLIDserver Connection
```bash
# Use your actual SOLIDserver credentials
python3 python/src/baremetal/dns-add.py --help
```

---

## Support

If you encounter issues after configuration:

1. Verify all `.env` variables are set correctly
2. Check network connectivity to BMC, NetBox, DNS, and SOLIDserver
3. Validate API tokens and credentials
4. Review Ansible playbook output for connection errors
5. Enable verbose logging: `export ANSIBLE_VERBOSITY=2`

For additional help, contact: infrastructure@site.com (update this!)
