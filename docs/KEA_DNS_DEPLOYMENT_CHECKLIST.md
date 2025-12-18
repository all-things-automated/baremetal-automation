# Kea DNS Integration - Deployment Checklist

**Target Server**: us3-sprmcr-l01  
**Date**: December 18, 2025

## Pre-Deployment Checklist

### Environment Setup
- [ ] Export VAULT_ADDR environment variable
  ```bash
  export VAULT_ADDR="https://vault.site.com:8200"
  ```

- [ ] Export VAULT_TOKEN environment variable
  ```bash
  export VAULT_TOKEN="hvs.XXXXXXXXXXXXXXXXXXXX"
  ```

- [ ] Verify Vault access
  ```bash
  vault token lookup
  vault read secrets/teams/core-infrastructure/server/kea_db
  vault read secrets/teams/core-infrastructure/server/baremetal_dns
  ```

### Target Server Access
- [ ] Verify SSH connectivity
  ```bash
  ansible us3-sprmcr-l01 -m ping
  ```

- [ ] Verify sudo access
  ```bash
  ssh us3-sprmcr-l01 'sudo whoami'
  ```

### Prerequisites Verification
- [ ] PostgreSQL installed and running
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl status postgresql'
  ```

- [ ] Kea database exists
  ```bash
  ssh us3-sprmcr-l01 'psql -h localhost -U kea -d kea -c "SELECT 1;"'
  ```

- [ ] SOLIDserver accessible
  ```bash
  ping -c 3 172.30.16.141
  ```

## Deployment Steps

### 1. Backup Current Configuration
- [ ] Backup existing kea_lease_monitor.py
  ```bash
  ssh us3-sprmcr-l01 'sudo cp /opt/baremetal-automation/kea_lease_monitor.py /opt/baremetal-automation/kea_lease_monitor.py.bak'
  ```

- [ ] Backup systemd service file
  ```bash
  ssh us3-sprmcr-l01 'sudo cp /etc/systemd/system/kea-lease-monitor.service /etc/systemd/system/kea-lease-monitor.service.bak'
  ```

### 2. Run Ansible Deployment
- [ ] Navigate to playbooks directory
  ```bash
  cd ansible/playbooks
  ```

- [ ] Make deployment script executable
  ```bash
  chmod +x deploy-kea-dns.sh
  ```

- [ ] Execute deployment
  ```bash
  ./deploy-kea-dns.sh us3-sprmcr-l01
  ```

  **OR manually:**
  ```bash
  ansible-playbook kea_deploy_with_dns.yml -e target_host=us3-sprmcr-l01
  ```

### 3. Verify Deployment
- [ ] Check Ansible playbook completed successfully
  - Look for "Deployment Successful" message
  - No failed tasks in output

- [ ] Verify files deployed
  ```bash
  ssh us3-sprmcr-l01 'ls -la /opt/baremetal-automation/{kea_lease_monitor.py,vault_credentials.py,solidserver_connection.py}'
  ```

- [ ] Check systemd service file updated
  ```bash
  ssh us3-sprmcr-l01 'sudo cat /etc/systemd/system/kea-lease-monitor.service | grep VAULT'
  ```

## Post-Deployment Verification

### Service Health
- [ ] Check kea-dhcp4-server status
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl status kea-dhcp4-server'
  ```
  - Should show: `Active: active (running)`

- [ ] Check kea-lease-monitor status
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl status kea-lease-monitor'
  ```
  - Should show: `Active: active (running)`
  - Should show: "Using event-driven database NOTIFY/LISTEN mode"

- [ ] View service logs
  ```bash
  ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor --since "5 minutes ago"'
  ```
  - Should show: "Retrieved database credentials from Vault"
  - Should show: "DNS record creation enabled: zone=site.com"
  - Should show: "DNS consistency check complete: N records created"

### PostgreSQL Trigger
- [ ] Verify trigger installed
  ```bash
  ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"SELECT tgname FROM pg_trigger WHERE tgname = 'reservation_notify_trigger';\""
  ```
  - Should return: `reservation_notify_trigger`

### DNS Sync Verification
- [ ] Check existing DNS records created
  ```bash
  ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor --since "10 minutes ago" | grep "DNS consistency check"'
  ```
  - Should show: "DNS consistency check complete: N records created" (where N ≥ 0)

- [ ] Verify DNS records resolve
  ```bash
  dig @172.30.16.141 us3-cab10-ru15-ilo.site.com
  dig @172.30.16.141 us3-cab10-ru17-idrac.site.com
  ```
  - Should return IP addresses for existing reservations

## Functional Testing

### Test DNS Sync Idempotency
- [ ] Run DNS sync again manually
  ```bash
  ssh us3-sprmcr-l01 'cd /opt/baremetal-automation && python3 kea_lease_monitor.py --db-host localhost --db-user kea --use-vault --enable-dns --dns-zone site.com --dns-scope internal --log-level INFO --once'
  ```
  - Should show: "DNS consistency check complete: 0 records created" (no duplicates)

### Test Real-time Event Detection
- [ ] **Terminal 1**: Watch service logs
  ```bash
  ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -f'
  ```

- [ ] **Terminal 2**: Insert test reservation
  ```bash
  ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"INSERT INTO hosts (dhcp_identifier_type, dhcp_identifier, dhcp4_subnet_id, ipv4_address, hostname) VALUES (1, decode('aabbccddee99', 'hex'), 1, ('172.30.19.199'::inet - '0.0.0.0'::inet), 'us3-cab10-ru99-idrac');\""
  ```

- [ ] **Terminal 1**: Verify notification received
  - Should show: "Received database notification"
  - Should show: "New reservation from database: 172.30.19.199 -> us3-cab10-ru99-idrac"
  - Should show: "[DNS] Created A record: us3-cab10-ru99-idrac.site.com -> 172.30.19.199"

- [ ] Verify DNS record created
  ```bash
  dig @172.30.16.141 us3-cab10-ru99-idrac.site.com
  ```
  - Should resolve to: 172.30.19.199

- [ ] Verify inventory file created
  ```bash
  ssh us3-sprmcr-l01 'ls -la /var/lib/kea/discovery/us3-cab10-discovery.yml'
  ```

- [ ] Clean up test reservation
  ```bash
  ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"DELETE FROM hosts WHERE hostname = 'us3-cab10-ru99-idrac';\""
  ```

### Performance Check
- [ ] Check service resource usage
  ```bash
  ssh us3-sprmcr-l01 'ps aux | grep kea_lease_monitor'
  ```
  - Memory: Should be < 100MB
  - CPU: Should be < 5% average

- [ ] Check event detection latency
  - Insert reservation and measure time to DNS record creation
  - Should be < 1 second

## Rollback Plan (If Needed)

### Stop Services
- [ ] Stop lease monitor
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl stop kea-lease-monitor'
  ```

### Restore Backup
- [ ] Restore previous kea_lease_monitor.py
  ```bash
  ssh us3-sprmcr-l01 'sudo cp /opt/baremetal-automation/kea_lease_monitor.py.bak /opt/baremetal-automation/kea_lease_monitor.py'
  ```

- [ ] Restore previous service file
  ```bash
  ssh us3-sprmcr-l01 'sudo cp /etc/systemd/system/kea-lease-monitor.service.bak /etc/systemd/system/kea-lease-monitor.service'
  ```

- [ ] Reload systemd
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl daemon-reload'
  ```

### Restart Services
- [ ] Start lease monitor
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl start kea-lease-monitor'
  ```

- [ ] Verify rollback successful
  ```bash
  ssh us3-sprmcr-l01 'sudo systemctl status kea-lease-monitor'
  ```

## Documentation

### Update Records
- [ ] Document deployment date/time
- [ ] Record any issues encountered
- [ ] Update inventory with new configuration
- [ ] Add notes to runbook if needed

### Notify Team
- [ ] Inform team of successful deployment
- [ ] Share service endpoints and monitoring links
- [ ] Document any special considerations

## Sign-off

- [ ] All verification checks passed
- [ ] No errors in service logs
- [ ] DNS records creating successfully
- [ ] Real-time events detected and processed
- [ ] Performance within acceptable limits
- [ ] Documentation updated

**Deployed By**: _______________  
**Date/Time**: _______________  
**Status**: _______________  
**Notes**: _______________

---

## Quick Reference Commands

### View Logs
```bash
# Real-time logs
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -f'

# Last 100 lines
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor -n 100'

# Since specific time
ssh us3-sprmcr-l01 'sudo journalctl -u kea-lease-monitor --since "1 hour ago"'
```

### Service Management
```bash
# Status
ssh us3-sprmcr-l01 'sudo systemctl status kea-lease-monitor'

# Restart
ssh us3-sprmcr-l01 'sudo systemctl restart kea-lease-monitor'

# Stop
ssh us3-sprmcr-l01 'sudo systemctl stop kea-lease-monitor'

# Start
ssh us3-sprmcr-l01 'sudo systemctl start kea-lease-monitor'
```

### Database Queries
```bash
# List all reservations
ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"SELECT hostname, inet '0.0.0.0' + ipv4_address AS ip FROM hosts ORDER BY hostname;\""

# Check trigger status
ssh us3-sprmcr-l01 "psql -h localhost -U kea -d kea -c \"SELECT * FROM pg_trigger WHERE tgname = 'reservation_notify_trigger';\""
```

### DNS Checks
```bash
# Query DNS record
dig @172.30.16.141 <hostname>.site.com

# List all DNS records in zone
dig @172.30.16.141 site.com AXFR
```
