# Deployment Guide - Kea DHCP Monitoring Services

This guide covers deployment of the automated BMC discovery and inventory system.

## Prerequisites

- Ubuntu 24.04 LTS (tested on us3-sprmcr-l01)
- Kea DHCP 4 with memfile backend
- Python 3.8+
- PyYAML installed
- Root access for initial setup

## Architecture Overview

```
DHCP Lease (CSV)
    ↓
kea-lease-monitor.service (reads CSV, creates YAML)
    ↓
/var/lib/kea/discovery/{site}-{cabinet}-discovery.yml
    ↓
bmc-dns-watcher.service (validates hostnames, reports)
    ↓
Console output (future: SolidServer DNS API)
```

## Deployment Steps

### 1. Prepare Environment

```bash
# Create automation directory
sudo mkdir -p /opt/baremetal-automation
sudo chown _kea:_kea /opt/baremetal-automation

# Ensure discovery directory exists
sudo mkdir -p /var/lib/kea/discovery
sudo chown _kea:_kea /var/lib/kea/discovery
sudo chmod 755 /var/lib/kea/discovery

# Verify PyYAML is installed
python3 -c "import yaml" || sudo apt install python3-yaml
```

### 2. Deploy Python Scripts

```bash
# Copy scripts to production
sudo cp python/src/baremetal/kea_lease_monitor.py /opt/baremetal-automation/
sudo cp python/src/baremetal/bmc_dns_watcher.py /opt/baremetal-automation/

# Set ownership and permissions
sudo chown _kea:_kea /opt/baremetal-automation/*.py
sudo chmod 755 /opt/baremetal-automation/*.py
```

### 3. Test Scripts Manually

```bash
# Test lease monitor (one-time scan)
sudo -u _kea python3 /opt/baremetal-automation/kea_lease_monitor.py --once

# Verify inventory files created
ls -lah /var/lib/kea/discovery/

# Test DNS watcher with strict validation
sudo -u _kea python3 /opt/baremetal-automation/bmc_dns_watcher.py --once

# Test DNS watcher without strict validation
sudo -u _kea python3 /opt/baremetal-automation/bmc_dns_watcher.py --once --no-strict
```

### 4. Deploy Systemd Services

```bash
# Copy service files
sudo cp systemd/kea-lease-monitor.service /etc/systemd/system/
sudo cp systemd/bmc-dns-watcher.service /etc/systemd/system/

# Set permissions
sudo chmod 644 /etc/systemd/system/kea-lease-monitor.service
sudo chmod 644 /etc/systemd/system/bmc-dns-watcher.service

# Reload systemd
sudo systemctl daemon-reload
```

### 5. Enable and Start Services

```bash
# Enable services to start on boot
sudo systemctl enable kea-lease-monitor.service
sudo systemctl enable bmc-dns-watcher.service

# Start services
sudo systemctl start kea-lease-monitor.service
sudo systemctl start bmc-dns-watcher.service

# Check status
sudo systemctl status kea-lease-monitor.service
sudo systemctl status bmc-dns-watcher.service
```

### 6. Monitor Logs

```bash
# Follow lease monitor logs
sudo journalctl -u kea-lease-monitor.service -f

# Follow DNS watcher logs
sudo journalctl -u bmc-dns-watcher.service -f

# View recent entries
sudo journalctl -u kea-lease-monitor.service -n 50
sudo journalctl -u bmc-dns-watcher.service -n 50

# Filter by time
sudo journalctl -u kea-lease-monitor.service --since "10 minutes ago"
```

## Testing with Real Events

### Test Scenario: New BMC Discovery

1. **Power on BMC** (e.g., Dell iDRAC with hostname `us3-cab10-ru19-idrac`)

2. **Verify DHCP lease**:
   ```bash
   sudo tail -f /var/lib/kea/kea-leases4.csv
   # Should show: 172.30.19.XX,f0:d4:e2:XX:XX:XX,...,us3-cab10-ru19-idrac,...
   ```

3. **Check lease monitor logs**:
   ```bash
   sudo journalctl -u kea-lease-monitor.service -f
   # Expected: "Discovered: us3-cab10-ru19-idrac"
   # Or: "Discovered New Cabinet: US3-CAB10" (if first device in cabinet)
   ```

4. **Verify inventory file created**:
   ```bash
   cat /var/lib/kea/discovery/us3-cab10-discovery.yml
   # Should contain new hostname and IP
   ```

5. **Check DNS watcher logs**:
   ```bash
   sudo journalctl -u bmc-dns-watcher.service -f
   # Expected: "[OK] New hostname: us3-cab10-ru19-idrac (172.30.19.XX)"
   ```

### Test Scenario: Invalid Hostname Format

1. **Power on BMC with invalid hostname** (e.g., `test-server-01`)

2. **Check lease monitor**:
   ```bash
   sudo journalctl -u kea-lease-monitor.service -f
   # Expected: Debug message about hostname not matching convention
   # No inventory file created for this hostname
   ```

3. **DNS watcher should not report** (strict validation rejects invalid format)

## Service Management Commands

```bash
# Stop services
sudo systemctl stop kea-lease-monitor.service
sudo systemctl stop bmc-dns-watcher.service

# Restart services (e.g., after code updates)
sudo systemctl restart kea-lease-monitor.service
sudo systemctl restart bmc-dns-watcher.service

# Disable services
sudo systemctl disable kea-lease-monitor.service
sudo systemctl disable bmc-dns-watcher.service

# Check service configuration
systemctl cat kea-lease-monitor.service
systemctl cat bmc-dns-watcher.service
```

## Configuration Options

### Lease Monitor Service

Edit `/etc/systemd/system/kea-lease-monitor.service`:

```ini
ExecStart=/usr/bin/python3 /opt/baremetal-automation/kea_lease_monitor.py \
    --lease-file /var/lib/kea/kea-leases4.csv \    # Kea lease CSV path
    --output-dir /var/lib/kea/discovery \           # Output directory
    --poll-interval 5 \                             # Polling interval (seconds)
    --log-level INFO                                # DEBUG, INFO, WARNING, ERROR
```

### DNS Watcher Service

Edit `/etc/systemd/system/bmc-dns-watcher.service`:

```ini
ExecStart=/usr/bin/python3 /opt/baremetal-automation/bmc_dns_watcher.py \
    --watch-dir /var/lib/kea/discovery \            # Directory to monitor
    --poll-interval 10 \                            # Polling interval (seconds)
    --log-level INFO                                # DEBUG, INFO, WARNING, ERROR
    # --no-strict \                                 # Uncomment to disable strict validation
```

After editing, reload and restart:
```bash
sudo systemctl daemon-reload
sudo systemctl restart kea-lease-monitor.service
sudo systemctl restart bmc-dns-watcher.service
```

## Troubleshooting

### Lease Monitor Not Detecting Leases

```bash
# Check if lease file is being updated
ls -lh /var/lib/kea/kea-leases4.csv
sudo tail -f /var/lib/kea/kea-leases4.csv

# Check service status
sudo systemctl status kea-lease-monitor.service

# Check for errors
sudo journalctl -u kea-lease-monitor.service --since "5 minutes ago"

# Verify permissions
ls -l /opt/baremetal-automation/kea_lease_monitor.py
ls -ld /var/lib/kea/discovery
```

### DNS Watcher Not Reporting Hostnames

```bash
# Check if inventory files exist
ls -lah /var/lib/kea/discovery/

# Test one-time scan manually
sudo -u _kea python3 /opt/baremetal-automation/bmc_dns_watcher.py --once

# Check validation summary
sudo journalctl -u bmc-dns-watcher.service --since "10 minutes ago" | grep -A 20 "VALIDATION SUMMARY"

# Enable debug logging
sudo systemctl edit bmc-dns-watcher.service
# Add: --log-level DEBUG to ExecStart line
sudo systemctl daemon-reload
sudo systemctl restart bmc-dns-watcher.service
```

### Permission Issues

```bash
# Verify _kea user can access directories
sudo -u _kea ls -la /var/lib/kea/
sudo -u _kea ls -la /var/lib/kea/discovery/

# Fix ownership if needed
sudo chown -R _kea:_kea /var/lib/kea/discovery/
sudo chown _kea:_kea /opt/baremetal-automation/*.py
```

## Validation Summary Output

When DNS watcher runs with `--once`, it shows:

```
VALIDATION SUMMARY
======================================================================
Total processed:      15
Valid entries:        12
Invalid format:       2   (hostname pattern mismatch)
Invalid site:         0   (site code not in us1/us2/us3/us4/dv)
Invalid BMC type:     1   (BMC type not idrac/ilo/bmc)
Duplicate hostname:   0   (same hostname multiple times)
Duplicate IP:         0   (same IP multiple times)
IP conflict:          0   (hostname/IP mapping mismatch)
======================================================================
```

## Next Steps

Once services are running successfully:

1. **Monitor for 24-48 hours** to verify stability
2. **Test with various BMC types** (Dell iDRAC, HP iLO, Supermicro BMC)
3. **Test with rack unit ranges** (e.g., `us3-cab10-ru17-18-idrac`)
4. **Review validation statistics** from DNS watcher
5. **Plan SolidServer DNS integration** (extend `bmc_dns_watcher.py`)

## Security Considerations

- Services run as `_kea` user (non-root)
- Read-only access to Kea lease file
- Write access only to `/var/lib/kea/discovery/`
- SystemD security hardening enabled:
  - `NoNewPrivileges=true`
  - `PrivateTmp=true`
  - `ProtectSystem=strict`
  - `ProtectHome=true`

## Related Documentation

- [KEA.md](KEA.md) - Kea DHCP configuration
- [TESTING.md](TESTING.md) - Testing procedures
- [NETBOX_SETUP.md](NETBOX_SETUP.md) - NetBox integration
- [.github/copilot-instructions.md](../.github/copilot-instructions.md) - Development standards
