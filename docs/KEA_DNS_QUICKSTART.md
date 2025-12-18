# Kea DHCP DNS Integration - Quick Start

**Status**: ✅ Ready for Production  
**Version**: 1.0.0  
**Date**: December 18, 2025

## What This Does

Automatically creates DNS records in SOLIDserver when BMC devices receive DHCP reservations, with secure credential management via HashiCorp Vault and real-time event processing using PostgreSQL NOTIFY/LISTEN.

## Quick Deploy

```bash
# 1. Set Vault credentials
export VAULT_ADDR="https://vault.site.com:8200"
export VAULT_TOKEN="hvs.XXXXXXXXXXXXXXXXXXXX"

# 2. Deploy to server
cd ansible/playbooks
./deploy-kea-dns.sh us3-sprmcr-l01

# 3. Verify
ssh us3-sprmcr-l01 'sudo systemctl status kea-lease-monitor'
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -f'
```

## Architecture

```
DHCP Reservation → PostgreSQL NOTIFY → Lease Monitor → SOLIDserver DNS
                                     ↓
                              Cabinet Inventory Files
```

**Flow**:
1. BMC device requests DHCP lease
2. Reservation inserted into PostgreSQL `hosts` table
3. Trigger fires `pg_notify()` with JSON payload
4. Service detects event via `LISTEN` connection
5. Creates DNS A record in SOLIDserver (< 200ms)
6. Generates cabinet-specific inventory YAML

## Key Features

✅ **Vault Integration** - No hardcoded credentials  
✅ **DNS Sync** - Creates missing DNS records on startup  
✅ **Real-time Events** - PostgreSQL NOTIFY/LISTEN (< 200ms latency)  
✅ **Idempotent** - Safe to run multiple times  
✅ **Cabinet-aware** - Generates site-cabinet inventory files  

## Documentation

| Document | Purpose |
|----------|---------|
| [KEA_DNS_INTEGRATION.md](KEA_DNS_INTEGRATION.md) | Complete technical guide |
| [KEA_DNS_DEPLOYMENT.md](KEA_DNS_DEPLOYMENT.md) | Deployment summary and testing results |
| [KEA_DNS_DEPLOYMENT_CHECKLIST.md](KEA_DNS_DEPLOYMENT_CHECKLIST.md) | Step-by-step deployment checklist |

## Configuration

### Ansible Variables
```yaml
kea_use_vault: true                    # Enable Vault
kea_enable_dns: true                   # Enable DNS creation
kea_dns_zone: "site.com"              # DNS zone
kea_dns_scope: "internal"             # internal/external
kea_use_database_events: true         # Real-time NOTIFY/LISTEN
```

### Service Flags
```bash
--use-vault                            # Use Vault for credentials
--enable-dns                           # Enable DNS creation
--dns-zone site.com                    # DNS zone
--dns-scope internal                   # DNS scope
--use-database-events                  # Real-time events
```

## Testing

### Test DNS Sync
```bash
ssh us3-sprmcr-l01 'cd /opt/baremetal-automation && \
  python3 kea_lease_monitor.py \
  --db-host localhost --db-user kea --use-vault \
  --enable-dns --dns-zone site.com --dns-scope internal \
  --log-level INFO --once'
```

### Test Real-time Events
```bash
# Terminal 1: Watch logs
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -f'

# Terminal 2: Insert reservation
ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \
  \"INSERT INTO hosts (dhcp_identifier_type, dhcp_identifier, dhcp4_subnet_id, ipv4_address, hostname) \
   VALUES (1, decode('aabbccddee99', 'hex'), 1, ('172.30.19.199'::inet - '0.0.0.0'::inet), 'us3-cab10-ru99-idrac');\""

# Verify DNS
dig @172.30.16.141 us3-cab10-ru99-idrac.site.com
```

## Troubleshooting

### Service Won't Start
```bash
# Check status
ssh us3-sprmcr-l01 'sudo systemctl status kea-lease-monitor'

# View logs
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -xe'

# Test Vault
vault token lookup
vault read secrets/teams/core-infrastructure/server/kea_db
```

### DNS Records Not Created
```bash
# Check service logs
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor --since "10 minutes ago" | grep -i dns'

# Verify trigger
ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"\d hosts\" | grep trigger"

# Test SOLIDserver connection
ssh us3-sprmcr-l01 'python3 dns-add.py test-hostname 172.30.19.100'
```

## Files

### Python
- `python/src/baremetal/kea_lease_monitor.py` - Main service
- `python/src/baremetal/vault_credentials.py` - Vault integration
- `python/src/baremetal/solidserver_connection.py` - DNS API

### Ansible
- `ansible/playbooks/kea_deploy_with_dns.yml` - Deployment playbook
- `ansible/playbooks/deploy-kea-dns.sh` - Deployment script
- `ansible/roles/kea_deploy/` - Deployment role

### Documentation
- `docs/KEA_DNS_INTEGRATION.md` - Technical guide
- `docs/KEA_DNS_DEPLOYMENT.md` - Deployment summary
- `docs/KEA_DNS_DEPLOYMENT_CHECKLIST.md` - Deployment checklist

## Vault Paths

| Purpose | Path | Keys |
|---------|------|------|
| Kea Database | `secrets/teams/core-infrastructure/server/kea_db` | username, password |
| SOLIDserver | `secrets/teams/core-infrastructure/server/baremetal_dns` | username, password |

## Performance

- **DNS Sync**: < 2s for 100 reservations
- **Event Latency**: < 200ms from INSERT to DNS record
- **Memory**: ~50MB resident
- **CPU**: < 1% idle, ~5% during sync

## Next Steps

1. ✅ Review documentation: [KEA_DNS_INTEGRATION.md](KEA_DNS_INTEGRATION.md)
2. ✅ Follow checklist: [KEA_DNS_DEPLOYMENT_CHECKLIST.md](KEA_DNS_DEPLOYMENT_CHECKLIST.md)
3. 🚀 Deploy to production: `./deploy-kea-dns.sh us3-sprmcr-l01`
4. ✅ Verify deployment with testing procedures
5. 📊 Monitor service logs and DNS record creation

---

**Questions?** Check the troubleshooting section in [KEA_DNS_INTEGRATION.md](KEA_DNS_INTEGRATION.md)
