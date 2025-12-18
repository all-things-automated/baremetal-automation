# Kea DHCP Deployment - Quick Reference

## Quick Deploy

```bash
# Deploy to localhost with auto-detection
ansible-playbook -i inventory/localhost.yml playbooks/kea_deploy_example.yml \
  -e kea_pool_start=172.30.19.100 \
  -e kea_pool_end=172.30.19.200 \
  -e kea_dns_servers="172.30.19.10,172.30.19.11" \
  -e kea_domain_name=us3.example.com
```

## Service Management

```bash
# Check all services
systemctl status kea-dhcp4-server kea-lease-monitor bmc-dns-watcher

# Restart services
systemctl restart kea-dhcp4-server
systemctl restart kea-lease-monitor
systemctl restart bmc-dns-watcher

# View logs in real-time
journalctl -u kea-dhcp4-server -f
journalctl -u kea-lease-monitor -f
journalctl -u bmc-dns-watcher -f

# View last 100 lines
journalctl -u kea-lease-monitor -n 100
journalctl -u bmc-dns-watcher -n 100
```

## Discovery Monitoring

```bash
# List discovery files
ls -lh /var/lib/kea/discovery/

# Watch directory for changes
watch -n 2 'ls -lh /var/lib/kea/discovery/'

# View specific inventory
cat /var/lib/kea/discovery/us3-cab10-discovery.yml

# Count devices per cabinet
for f in /var/lib/kea/discovery/*.yml; do 
  echo "$f: $(grep -c 'hostname:' $f) devices"
done
```

## Troubleshooting

```bash
# Test Kea config syntax
kea-dhcp4 -t /etc/kea/kea-dhcp4.conf

# Check lease file
cat /var/lib/kea/kea-leases4.csv | head

# Verify permissions
ls -la /var/lib/kea/discovery/
ps aux | grep kea

# Check service user
id _kea

# Manual script test
sudo -u _kea python3 /opt/baremetal-automation/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --poll-interval 5 \
  --log-level DEBUG

sudo -u _kea python3 /opt/baremetal-automation/bmc_dns_watcher.py \
  --watch-dir /var/lib/kea/discovery \
  --poll-interval 10 \
  --log-level DEBUG
```

## Required Variables

| Variable | Example | Description |
|----------|---------|-------------|
| `kea_pool_start` | `172.30.19.100` | DHCP pool start IP |
| `kea_pool_end` | `172.30.19.200` | DHCP pool end IP |
| `kea_dns_servers` | `172.30.19.10, 172.30.19.11` | DNS servers (comma-separated) |
| `kea_domain_name` | `us3.example.com` | Domain name |

## Auto-Detected Variables

| Variable | Source | Override |
|----------|--------|----------|
| `kea_interface` | `ansible_default_ipv4.interface` | `-e kea_interface=eth0` |
| `kea_subnet_cidr` | Calculated from facts | `-e kea_subnet_cidr=172.30.19.0/24` |
| `kea_gateway` | `ansible_default_ipv4.gateway` | `-e kea_gateway=172.30.19.1` |

## Optional Configuration

```yaml
# Feature toggles
kea_enable_lease_monitor: true
kea_enable_dns_watcher: true

# Poll intervals (seconds)
kea_lease_monitor_poll_interval: 5
kea_dns_watcher_poll_interval: 10

# Validation
kea_dns_watcher_strict_validation: true

# Log levels
kea_lease_monitor_log_level: "INFO"
kea_dns_watcher_log_level: "INFO"

# Python environment
kea_use_venv: false              # false=system Python (python3-yaml via apt)
                                 # true=isolated venv (pip install)

# Paths
kea_app_base_dir: "/opt/baremetal-automation"
kea_discovery_output_dir: "/var/lib/kea/discovery"
```

**Note**: Ubuntu 24.04 uses PEP 668 which prevents direct pip installs to system Python. This role uses system packages (python3-yaml) by default. Set `kea_use_venv: true` if you need pip-installed packages.

## Common Scenarios

### Deploy to Multiple Sites

```bash
# Create inventory
cat > inventory/kea_servers.yml <<EOF
all:
  children:
    kea_servers:
      hosts:
        us3-kea-01:
          kea_pool_start: 172.30.19.100
          kea_pool_end: 172.30.19.200
          kea_dns_servers: "172.30.19.10,172.30.19.11"
          kea_domain_name: us3.example.com
        us4-kea-01:
          kea_pool_start: 172.31.19.100
          kea_pool_end: 172.31.19.200
          kea_dns_servers: "172.31.19.10,172.31.19.11"
          kea_domain_name: us4.example.com
EOF

# Deploy
ansible-playbook -i inventory/kea_servers.yml playbooks/kea_deploy_example.yml
```

### Update Python Scripts Only

```bash
ansible-playbook -i inventory/localhost.yml playbooks/kea_deploy_example.yml \
  --tags python
```

### Restart Services Only

```bash
ansible-playbook -i inventory/localhost.yml playbooks/kea_deploy_example.yml \
  --tags services
```

### Re-validate Deployment

```bash
ansible-playbook -i inventory/localhost.yml playbooks/kea_deploy_example.yml \
  --tags validation
```

## Expected Output

### Lease Monitor
```
[INFO] Discovered New Devices In: US3-CAB10
[INFO] Devices: ['us3-cab10-ru01-idrac', 'us3-cab10-ru02-idrac']
[INFO] Devices added to: us3-cab10-discovery.yml
```

### DNS Watcher
```
[INFO] New devices in us3-cab10-discovery.yml: ['us3-cab10-ru01-idrac']
[INFO] Hostname resolution:
[INFO]   us3-cab10-ru01-idrac -> 172.30.19.150
```

## Files Generated

```
/etc/kea/kea-dhcp4.conf
/etc/systemd/system/kea-lease-monitor.service
/etc/systemd/system/bmc-dns-watcher.service
/opt/baremetal-automation/kea_lease_monitor.py
/opt/baremetal-automation/bmc_dns_watcher.py
/var/lib/kea/discovery/*.yml
```
