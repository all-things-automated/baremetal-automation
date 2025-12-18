# Bare-Metal Infrastructure Standards

**Document Version**: 1.0  
**Last Updated**: December 18, 2025  
**Maintained By**: Core Infrastructure Team

## Purpose

This document defines the infrastructure conventions and requirements that the bare-metal automation system expects. These standards ensure consistent, automated discovery and management of bare-metal servers across all sites.

**CRITICAL**: The automation relies on these standards. Non-compliant infrastructure will not be discovered or managed correctly.

---

## Table of Contents

1. [Hostname Naming Convention](#hostname-naming-convention)
2. [Network Requirements](#network-requirements)
3. [BMC Requirements](#bmc-requirements)
4. [DHCP Requirements](#dhcp-requirements)
5. [DNS Requirements](#dns-requirements)
6. [Credential Management](#credential-management)
7. [Validation and Compliance](#validation-and-compliance)

---

## Hostname Naming Convention

### Format Specification

**Required Format**: `{site}-cab{cabinet}-ru{rack_unit}-{bmc_type}`

**Pattern**: `^(us[1-4]|dv)-cab(\d+)-ru(\d+)-(ilo|idrac|bmc)$`

### Components

| Component | Description | Valid Values | Example |
|-----------|-------------|--------------|---------|
| **site** | Site/datacenter code | `us1`, `us2`, `us3`, `us4`, `dv` | `us3` |
| **cabinet** | Cabinet/rack number | `cab` + digits (1-999) | `cab10` |
| **rack_unit** | Rack unit position | `ru` + digits (1-42) | `ru17` |
| **bmc_type** | BMC management type | `ilo`, `idrac`, `bmc` | `idrac` |

### Valid Examples

```
us3-cab10-ru17-idrac       # Dell iDRAC in US3, Cabinet 10, RU 17
us3-cab10-ru15-ilo         # HP iLO in US3, Cabinet 10, RU 15
us2-cab05-ru01-bmc         # Generic BMC in US2, Cabinet 5, RU 1
dv-cab01-ru22-idrac        # Dev environment, Cabinet 1, RU 22
```

### Invalid Examples

```
server-01                  # Missing site/cabinet/rack unit
us3-ru17-idrac             # Missing cabinet
us3-cab10-idrac            # Missing rack unit
us3_cab10_ru17_idrac       # Wrong delimiter (underscore instead of hyphen)
US3-CAB10-RU17-IDRAC       # Wrong case (must be lowercase)
us5-cab10-ru17-idrac       # Invalid site code (us5 doesn't exist)
us3-cab10-ru17-mgmt        # Invalid BMC type (must be ilo/idrac/bmc)
```

### Behavior

**Automation Processing**:
- [OK] **Compliant hostnames**: Processed for discovery and DNS registration
- [SKIP] **Non-compliant hostnames**: Skipped with debug log entry
- [INFO] **Reporting**: Summary shows count of skipped entries

**Grouping Logic**:
- Leases grouped by site and cabinet: `(us3, cab10)`
- Inventory files generated per cabinet: `us3-cab10-discovery.yml`
- Conflict detection performed per cabinet group

---

## Network Requirements

### BMC Management Network

**Required Configuration**:
- **Subnet**: Single /24 per site dedicated to BMC management
  - Example: `172.30.19.0/24` for US3
- **VLAN**: Isolated management VLAN
- **Access**: Routable from discovery server

### IP Address Assignment

**Methods** (choose one):
- **DHCP Dynamic Pool**: For initial discovery
- **DHCP Static Reservations**: For production (preferred)
- **Static IP**: Must be registered in Kea database

**IP Range Planning**:
```
172.30.19.0/24          # BMC Management Subnet
  .1                    # Gateway
  .2-.10                # Infrastructure (DHCP, DNS)
  .11-.100              # DHCP Dynamic Pool
  .101-.254             # Static Reservations
```

### Firewall Requirements

**Required Access** (from discovery server to BMCs):
- TCP/443 (HTTPS) - Redfish API
- TCP/5986 (WinRM-HTTPS) - Optional, Windows management
- ICMP - Network connectivity testing

**Security**:
- BMC network should be isolated from production networks
- Access restricted to management systems only
- No internet egress required for BMCs

---

## BMC Requirements

### Supported Hardware

**Vendors**:
- Dell: iDRAC 7, 8, 9 (Redfish API)
- HP/HPE: iLO 4, 5, 6 (Redfish API)
- Supermicro: BMC with Redfish support

**Firmware**:
- Redfish API enabled
- HTTPS access enabled
- DHCP client enabled (for initial discovery)

### BMC Configuration

**REQUIRED Settings**:
1. **Hostname**: Must follow naming convention (see above)
2. **DHCP Hostname Option**: Enabled (Option 12)
3. **Network**: DHCP enabled on management interface
4. **API Access**: Redfish API enabled over HTTPS
5. **Credentials**: Standard credentials stored in Vault

**OPTIONAL Settings**:
- DNS servers: Will be provided via DHCP
- NTP servers: Recommended for accurate logging
- SNMP: For additional monitoring

### BMC Credentials

**Standard Accounts** (stored in Vault):
- **Username**: `ADMIN` (Dell) or `Administrator` (HP)
- **Password**: Retrieved from Vault at runtime
- **Path**: `secrets/teams/core-infrastructure/server/bmc_credentials`

**Account Requirements**:
- Read-only access to hardware inventory
- No configuration changes made by automation
- Credentials rotated quarterly (manual process)

---

## DHCP Requirements

### Kea DHCP Server Configuration

**Required Features**:
- PostgreSQL backend enabled
- Host reservations table
- NOTIFY/LISTEN trigger installed
- Subnet configuration matching BMC network

### DHCP Options

**Required Options**:
```yaml
option-data:
  - name: domain-name
    data: "site.com"
  - name: domain-name-servers
    data: "192.168.204.52"
```

**Hostname Validation**:
- DHCP server MUST validate hostname format before lease assignment
- Non-compliant hostnames should generate alerts

### Database Schema

**Required Tables**:
- `hosts` - Static reservations
- `lease4` - Active leases
- `logs` - Audit trail

**Required Trigger**:
```sql
CREATE TRIGGER reservation_notify_trigger
  AFTER INSERT OR UPDATE OR DELETE ON hosts
  FOR EACH ROW EXECUTE FUNCTION notify_reservation_change();
```

---

## DNS Requirements

### SOLIDserver Integration

**Required Configuration**:
- **API Endpoint**: `https://10.10.3.203:443`
- **DNS Zone**: `site.com`
- **DNS Scope**: `internal`
- **Credentials**: Stored in Vault

**Record Type**:
- A records only (IPv4)
- TTL: 300 seconds (5 minutes)
- Automatic cleanup on lease expiration (future enhancement)

### DNS Record Format

**Example**:
```
us3-cab10-ru17-idrac.site.com    IN A    172.30.19.42
us3-cab10-ru15-ilo.site.com      IN A    172.30.19.43
```

**Behavior**:
- Records created automatically on reservation creation
- Updates handled idempotently (no duplicates)
- Reverse DNS (PTR) not currently implemented

---

## Credential Management

### HashiCorp Vault

**Required Paths**:
```
secrets/teams/core-infrastructure/server/kea_db
  - username: kea
  - password: <secure_password>

secrets/teams/core-infrastructure/server/baremetal_dns
  - username: <solidserver_user>
  - password: <secure_password>

secrets/teams/core-infrastructure/server/bmc_credentials
  - username: <bmc_admin_user>
  - password: <secure_password>
```

**Vault Configuration**:
- **Server**: `https://vault.site.com:8200`
- **Authentication**: Token-based
- **Mount Point**: `secrets` (KV v2)
- **Access**: Read-only for automation service account

**Environment Variables** (deployment time):
```bash
export VAULT_ADDR="https://vault.site.com:8200"
export VAULT_TOKEN="hvs.XXXXXXXXXXXXXXXXXXXX"
export VAULT_SKIP_VERIFY="true"  # For self-signed certificates
```

---

## Validation and Compliance

### Pre-Deployment Checklist

Before adding new hardware to automation:

- [ ] Hostname follows `{site}-cab{cabinet}-ru{rack_unit}-{bmc_type}` format
- [ ] Hostname is lowercase
- [ ] Site code is valid (`us1`-`us4`, `dv`)
- [ ] Cabinet number matches physical location
- [ ] Rack unit number matches physical position
- [ ] BMC type matches actual hardware (`ilo`/`idrac`/`bmc`)
- [ ] BMC has network connectivity to discovery server
- [ ] BMC Redfish API is enabled
- [ ] BMC DHCP hostname option is enabled
- [ ] BMC credentials are stored in Vault

### Validation Commands

**Check hostname format**:
```bash
echo "us3-cab10-ru17-idrac" | grep -E '^(us[1-4]|dv)-cab[0-9]+-ru[0-9]+-(ilo|idrac|bmc)$'
# Exit code 0 = valid, 1 = invalid
```

**Query existing reservations**:
```bash
psql -U kea -h localhost -d kea -c "
SELECT 
  hostname,
  inet '0.0.0.0' + ipv4_address as ip_address,
  encode(dhcp_identifier, 'hex') as mac_address
FROM hosts 
WHERE hostname ~ '^(us[1-4]|dv)-cab[0-9]+-ru[0-9]+-(ilo|idrac|bmc)$'
ORDER BY hostname;
"
```

**Verify DNS record**:
```bash
dig @172.30.16.141 us3-cab10-ru17-idrac.site.com +short
# Should return: 172.30.19.42
```

### Monitoring and Alerting

**Log Monitoring**:
```bash
# Check for skipped entries (naming convention violations)
sudo journalctl -u kea-lease-monitor | grep "doesn't match.*convention"

# Check for DNS creation failures
sudo journalctl -u kea-lease-monitor | grep -i "dns.*error"

# Check for Vault connection issues
sudo journalctl -u kea-lease-monitor | grep -i "vault.*error"
```

**Metrics to Track**:
- Reservations processed vs. skipped (naming convention)
- DNS records created successfully
- Vault credential retrieval failures
- BMC Redfish API connection failures

---

## Compliance Exceptions

### Temporary Non-Compliance

**Allowed** (with justification):
- Development/test environments may use non-standard hostnames
- Lab equipment may use simplified naming (e.g., `lab-server-01`)
- Legacy hardware during migration period

**Required Actions**:
- Document exception in infrastructure notes
- Set target date for compliance
- Exclude from automated discovery (will be skipped automatically)

### Non-Standard Environments

**Alternative Patterns** (future enhancement):
- Custom site codes (requires code update)
- Alternative BMC types (requires code update)
- Multi-chassis systems (pending design)

**To Request Exception**:
- Open ticket with Core Infrastructure Team
- Provide business justification
- Specify duration of exception
- Plan remediation timeline

---

## Change Management

### Updating Standards

**Process**:
1. Propose change via pull request to this document
2. Update automation code to support new standard
3. Test in development environment
4. Communicate changes to infrastructure teams
5. Update validation scripts and monitoring

**Versioning**:
- Major version: Breaking changes (requires infrastructure updates)
- Minor version: Additive changes (backward compatible)
- Patch version: Clarifications and corrections

### Migration Support

When standards change:
- Automation supports both old and new standards during transition
- Migration timeline communicated 90 days in advance
- Automated validation reports non-compliant systems
- Remediation tooling provided where possible

---

## References

### Related Documentation

- [KEA_DNS_INTEGRATION.md](KEA_DNS_INTEGRATION.md) - DNS integration technical details
- [TESTING.md](TESTING.md) - Validation and testing procedures
- [DESIGN.md](DESIGN.md) - System architecture and design decisions
- [Discovery-Server.md](Discovery-Server.md) - Discovery server overview

### External Standards

- [Redfish API Specification](https://www.dmtf.org/standards/redfish) - DMTF standard
- [RFC 2132](https://tools.ietf.org/html/rfc2132) - DHCP Options and BOOTP Vendor Extensions
- [SOLIDserver API Documentation](https://docs.efficientip.com/) - DNS management

### Support

**Questions or Issues**:
- Email: infrastructure@site.com
- Slack: #infrastructure-automation
- Jira Project: INF

**Emergency Contact**:
- On-call: PagerDuty rotation
- Escalation: Infrastructure Manager

---

**Document Control**:
- **Created**: December 18, 2025
- **Author**: Core Infrastructure Team
- **Review Cycle**: Quarterly
- **Next Review**: March 18, 2026
