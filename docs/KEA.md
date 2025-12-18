# Kea DHCP Integration for Bare-Metal Discovery

This document describes the Kea DHCP hook integration that triggers automated bare-metal server discovery when BMCs receive DHCP leases.

## Overview

When a BMC obtains a DHCP lease on the BMC network, Kea's `lease4_commit` hook executes `kea_lease_hook.py` (located in `python/`), which generates an Ansible inventory file for the discovery workflow.

## Components

### `python/src/baremetal/kea_lease_hook.py`

Python script that:
- Receives lease information from Kea DHCP (IP, MAC, subnet, hostname)
- Generates Ansible inventory YAML with `bmc_targets` list (single lease)
- Validates output with proper YAML formatting
- Supports subnet filtering for multi-site deployments
- Logs all operations for troubleshooting

**Output Format:**
```yaml
bmc_targets:
- ip: 172.30.19.42
metadata:
  generated_at: '2025-12-05T10:30:00Z'
  source: kea_dhcp_hook
  lease_info:
    ip: 172.30.19.42
    mac: '00:11:22:33:44:55'
    hostname: us3-cab10-ru17-idrac
```

### `python/src/baremetal/kea_lease_monitor.py`

Continuous lease file monitor that:
- Polls Kea's lease CSV file (`/var/lib/kea/kea-leases4.csv`)
- Detects new leases and generates consolidated batch inventory
- Creates timestamped inventory files: `YYYYMMDD-HHMMSS-discovery.yml`
- Maintains `latest-discovery.yml` symlink for easy playbook access
- Supports one-time scan or continuous monitoring modes
- Tracks processed leases to avoid duplicates

**Output Format:**
```yaml
bmc_targets:
- ip: 172.30.19.42
- ip: 172.30.19.48
metadata:
  updated_at: '2025-12-05T18:15:09Z'
  source: kea_lease_monitor
  site: us3
  cabinet: cab10
  total_count: 2
  leases:
  - ip: 172.30.19.48
    mac: f0:d4:e2:fc:00:a0
    hostname: us3-cab10-ru18-idrac
    manufacturer: Dell
  - ip: 172.30.19.42
    mac: f0:d4:e2:fc:02:44
    hostname: us3-cab10-ru17-idrac
    manufacturer: Dell
```

**Manufacturer Detection:**
- Detected per-host from hostname suffix for future OEM-specific tasks
- `-idrac` or `idrac` → Dell
- `-ilo` or `ilo` → HP
- `-bmc` or `bmc` → Supermicro
- Unknown if no match
- Stored per-lease in `metadata.leases[].manufacturer`

**Filename Convention:**
- Format: `{site}-{cabinet}-discovery.yml`
- Site and cabinet extracted from hostname (e.g., `us3-cab10-ru17-idrac`)
- Examples: `us3-cab10-discovery.yml`, `us3-cab11-discovery.yml`, `dv-cab01-discovery.yml`
- Unknown: `unknown-unknown-discovery.yml` (when hostnames missing or inconsistent)
- Files are **permanent** - new IPs appended to existing files
- No timestamped versions - single file per site/cabinet combination

## Installation

### Prerequisites

```bash
# Python 3.8+
python3 --version

# PyYAML
pip3 install -r python/requirements.txt
```

### Kea DHCP Configuration

Add hook library to Kea configuration (`/etc/kea/kea-dhcp4.conf`):

```json
{
  "Dhcp4": {
    "hooks-libraries": [
      {
        "library": "/usr/lib/x86_64-linux-gnu/kea/hooks/libdhcp_run_script.so",
        "parameters": {
          "name": "/path/to/baremetal-automation/python/src/baremetal/kea_lease_hook.py",
          "sync": false
        }
      }
    ]
  }
}
```

### Script Deployment

```bash
# Copy script to Kea hook location
sudo cp python/src/baremetal/kea_lease_hook.py /usr/local/bin/
sudo chmod +x /usr/local/bin/kea_lease_hook.py

# Create output directory
sudo mkdir -p /var/lib/kea/discovery
sudo chown kea:kea /var/lib/kea/discovery
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KEA_HOOK_OUTPUT_DIR` | `/var/lib/kea/discovery` | Directory for generated inventory files |
| `KEA_HOOK_SUBNET_FILTER` | (none) | Comma-separated list of subnet IDs to process |
| `KEA_HOOK_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

### Kea Environment Variables (Automatically Set)

| Variable | Description |
|----------|-------------|
| `KEA_LEASE4_ADDRESS` | IPv4 address leased to BMC |
| `KEA_LEASE4_HWADDR` | BMC MAC address |
| `KEA_SUBNET4` | Kea subnet identifier |
| `KEA_LEASE4_HOSTNAME` | Client-provided hostname (if available) |

## Usage

### Lease Monitor (Recommended)

**Continuous Monitoring:**
```bash
# Production: Run as daemon or systemd service
python3 python/src/baremetal/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --poll-interval 30 \
  --log-level INFO

# Development: Run with debug output
python3 python/src/baremetal/kea_lease_monitor.py \
  --lease-file python/tests/fixtures/kea-leases4.csv \
  --output-dir python/tests/output \
  --poll-interval 5 \
  --log-level DEBUG
```

**One-Time Scan:**
```bash
# Process current leases once and exit
python3 python/src/baremetal/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --once
```

**Subnet Filtering:**
```bash
# Only process leases from specific subnets
python3 python/src/baremetal/kea_lease_monitor.py \
  --subnet-filter 1,10,20 \
  --log-level INFO
```

### Production (Kea Hook - Per Lease)

Kea automatically invokes the script on `lease4_commit` events. No manual intervention required.

### Testing (Manual Invocation)

```bash
# Basic test with required parameters
python3 python/src/baremetal/kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55

# Test with custom output directory
python3 python/src/baremetal/kea_lease_hook.py \
  --ip 172.30.19.42 \
  --mac 00:11:22:33:44:55 \
  --output-dir /tmp/kea-test

# Test with all parameters
python3 python/src/baremetal/kea_lease_hook.py \
  --ip 172.30.19.42 \
  --mac 00:11:22:33:44:55 \
  --hostname us3-cab10-ru17-idrac \
  --subnet 10 \
  --log-level DEBUG

# Simulate Kea environment
KEA_LEASE4_ADDRESS=172.30.19.42 \
KEA_LEASE4_HWADDR=00:11:22:33:44:55 \
KEA_SUBNET4=10 \
python3 python/src/baremetal/kea_lease_hook.py
```

### Validation

Use the project's YAML linter to verify generated inventory files:

```bash
# Validate specific cabinet inventory
python3 python/src/baremetal/lint_yaml.py /var/lib/kea/discovery/us3-cab10-discovery.yml

# Validate all cabinet inventories
python3 python/src/baremetal/lint_yaml.py /var/lib/kea/discovery/*-discovery.yml

# Check for unknown cabinets that need review
python3 python/src/baremetal/lint_yaml.py /var/lib/kea/discovery/unknown-*.yml
```

## Integration with Discovery Workflow

### Recommended Approach: Lease Monitor + External Vars File

Use the lease monitor to generate/update consolidated inventory files per cabinet:

```bash
# Run discovery with specific cabinet inventory
ansible-playbook ansible/playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab10-discovery.yml

# Process different cabinet
ansible-playbook ansible/playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab11-discovery.yml

# Review unknown sites/cabinets (missing hostnames)
ansible-playbook ansible/playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/unknown-unknown-discovery.yml
```

**Workflow:**
1. `kea_lease_monitor.py` polls lease file continuously
2. Detects new leases and extracts site + cabinet from hostnames
3. Updates existing inventory file or creates new one: `{site}-{cabinet}-discovery.yml`
4. Appends new IPs to existing file (permanent, incremental updates)
5. Playbook reads `bmc_targets` from vars file via `-e @file`

**Benefits:**
- Permanent inventory files per cabinet
- Incremental updates (no duplicate processing)
- Cabinet-level granularity for discovery runs
- Easy audit: one file per physical cabinet

**Benefits:**
- Clean separation: inventory defines hosts, vars files provide data
- Generated files are already in correct YAML format
- No modifications to existing inventory structure
- Easy to switch between different discovery runs
- Follows Ansible best practices

### Option 1: Direct Ansible Invocation (Per-Lease Hook)

Configure Kea hook to trigger Ansible directly:

```bash
#!/bin/bash
# Wrapper script called by Kea
INVENTORY_FILE=$(/usr/local/bin/kea_lease_hook.py "$@")

if [ $? -eq 0 ]; then
  ansible-playbook \
    ansible/playbooks/discovery.yml \
    -e @"$INVENTORY_FILE"
fi
```

### Option 2: Lease Monitor + Scheduled Playbook Runs

Run lease monitor continuously and trigger discovery on a schedule:

```bash
# Start lease monitor (systemd service or screen/tmux)
python3 python/src/baremetal/kea_lease_monitor.py \
  --output-dir /var/lib/kea/discovery \
  --poll-interval 30 \
  --log-level INFO

# Separate cron job triggers discovery every 5 minutes
*/5 * * * * ansible-playbook /path/to/ansible/playbooks/discovery.yml -e @/var/lib/kea/discovery/latest-discovery.yml
```

### Option 3: Lease Monitor + File Watcher (Immediate Processing)

Combine lease monitor with inotify for immediate discovery:

```bash
# Terminal 1: Start lease monitor
python3 python/src/baremetal/kea_lease_monitor.py

# Terminal 2: Watch for new inventory files
inotifywait -m -e create /var/lib/kea/discovery/ |
  while read path action file; do
    if [[ "$file" == *-discovery.yml ]]; then
      ansible-playbook ansible/playbooks/discovery.yml -e @"$path$file"
    fi
  done
```

### Option 4: Spacelift API Trigger (Production CI/CD)

Extend workflow to call Spacelift API after generating inventory:

```python
# Add to kea_lease_monitor.py after generate_batch_inventory()
def trigger_spacelift_discovery(inventory_file: Path):
    """Trigger Spacelift discovery stack via API."""
    spacelift_api_url = os.getenv('SPACELIFT_API_URL')
    spacelift_token = os.getenv('SPACELIFT_API_TOKEN')
    stack_id = os.getenv('SPACELIFT_DISCOVERY_STACK_ID')
    
    # API call implementation
    # ...
```

## Subnet Filtering

For multi-site deployments, filter which subnets trigger discovery:

```bash
# In Kea hook configuration
export KEA_HOOK_SUBNET_FILTER="10,20,30"

# Only process leases from subnets 10, 20, and 30
# Skip all other subnets
```

## Troubleshooting

### Enable Debug Logging

```bash
export KEA_HOOK_LOG_LEVEL=DEBUG
```

### Check Generated Files

```bash
ls -lh /var/lib/kea/discovery/
cat /var/lib/kea/discovery/172-30-19-42-bmc.yml
```

### Verify YAML Format

```bash
python3 -c "import yaml; yaml.safe_load(open('/var/lib/kea/discovery/172-30-19-42-bmc.yml'))"
```

### Kea Logs

```bash
sudo journalctl -u kea-dhcp4-server -f
tail -f /var/log/kea/kea-dhcp4.log
```

### Test Hook Execution

```bash
# Simulate Kea calling the hook
sudo -u kea \
  KEA_LEASE4_ADDRESS=172.30.19.42 \
  KEA_LEASE4_HWADDR=00:11:22:33:44:55 \
  KEA_SUBNET4=10 \
  /usr/local/bin/kea_lease_hook.py
```

## Security Considerations

- Run hook script as `kea` user (least privilege)
- Restrict output directory permissions: `700` or `750`
- Validate all input parameters (IP format, MAC format)
- Log all operations for audit trail
- Consider rate limiting for production environments
- Protect Spacelift API credentials if using API trigger

## Production Deployment on Ubuntu 24.04

### Step 1: Install Kea DHCP Server

```bash
# Update package list
sudo apt update

# Install Kea DHCP server and hook libraries
sudo apt install -y kea-dhcp4-server kea-ctrl-agent kea-admin

# Verify installation
kea-dhcp4 -v
```

### Step 2: Install Python Dependencies

```bash
# Install Python 3 and pip
sudo apt install -y python3 python3-pip python3-venv

# Install PyYAML globally or in venv
sudo pip3 install pyyaml

# Or create virtual environment (recommended)
cd /opt/baremetal-automation
python3 -m venv venv
source venv/bin/activate
pip3 install -r python/requirements.txt
```

### Step 3: Deploy Kea Lease Monitor

```bash
# Create application directory
sudo mkdir -p /opt/baremetal-automation
sudo git clone <your-repo> /opt/baremetal-automation
sudo chown -R kea:kea /opt/baremetal-automation

# Create output directory for inventory files
sudo mkdir -p /var/lib/kea/discovery
sudo chown kea:kea /var/lib/kea/discovery
sudo chmod 750 /var/lib/kea/discovery

# Create log directory
sudo mkdir -p /var/log/baremetal
sudo chown kea:kea /var/log/baremetal
```

### Step 4: Create Systemd Service for Lease Monitor

Create `/etc/systemd/system/kea-lease-monitor.service`:

```ini
[Unit]
Description=Kea DHCP Lease Monitor for BMC Discovery
Documentation=file:///opt/baremetal-automation/docs/KEA.md
After=network.target kea-dhcp4-server.service
Requires=kea-dhcp4-server.service

[Service]
Type=simple
User=kea
Group=kea
WorkingDirectory=/opt/baremetal-automation

# If using venv
ExecStart=/opt/baremetal-automation/venv/bin/python3 \
  /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --poll-interval 30 \
  --log-level INFO

# Or without venv
# ExecStart=/usr/bin/python3 \
#   /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py \
#   --lease-file /var/lib/kea/kea-leases4.csv \
#   --output-dir /var/lib/kea/discovery \
#   --poll-interval 30 \
#   --log-level INFO

# Environment variables (optional)
# Environment="BMC_USERNAME=admin"
# Environment="BMC_PASSWORD=changeme"

# Restart policy
Restart=always
RestartSec=10
StartLimitBurst=5
StartLimitInterval=300

# Resource limits
LimitNOFILE=4096

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kea-lease-monitor

[Install]
WantedBy=multi-user.target
```

```bash
# Reload systemd and enable service
sudo systemctl daemon-reload
sudo systemctl enable kea-lease-monitor.service
sudo systemctl start kea-lease-monitor.service

# Check status
sudo systemctl status kea-lease-monitor.service

# View logs
sudo journalctl -u kea-lease-monitor.service -f
```

### Step 5: Configure Kea DHCP Server

Edit `/etc/kea/kea-dhcp4.conf`:

```json
{
  "Dhcp4": {
    "interfaces-config": {
      "interfaces": ["ens192"]
    },
    
    "lease-database": {
      "type": "memfile",
      "persist": true,
      "name": "/var/lib/kea/kea-leases4.csv",
      "lfc-interval": 3600
    },
    
    "valid-lifetime": 600,
    "renew-timer": 300,
    "rebind-timer": 450,
    
    "subnet4": [
      {
        "id": 1,
        "subnet": "172.30.19.0/24",
        "pools": [
          { "pool": "172.30.19.100 - 172.30.19.200" }
        ],
        "option-data": [
          {
            "name": "routers",
            "data": "172.30.19.1"
          },
          {
            "name": "domain-name-servers",
            "data": "8.8.8.8, 8.8.4.4"
          }
        ]
      }
    ],
    
    "loggers": [
      {
        "name": "kea-dhcp4",
        "output_options": [
          {
            "output": "/var/log/kea/kea-dhcp4.log",
            "maxver": 8,
            "maxsize": 10485760,
            "flush": true
          }
        ],
        "severity": "INFO"
      }
    ]
  }
}
```

```bash
# Test configuration
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf

# Restart Kea DHCP server
sudo systemctl restart kea-dhcp4-server.service
sudo systemctl status kea-dhcp4-server.service
```

### Step 6: Verify Integration

```bash
# Check lease monitor is running
sudo systemctl status kea-lease-monitor.service

# Watch for new inventory files
watch -n 5 'ls -lh /var/lib/kea/discovery/'

# Monitor logs
sudo journalctl -u kea-lease-monitor.service -f

# Simulate BMC lease (for testing)
# Trigger DHCP request from BMC or use dhcping
```

### Step 7: Test Discovery Workflow

```bash
# Wait for lease monitor to generate inventory
ls -lh /var/lib/kea/discovery/

# Example output:
# us3-cab10-discovery.yml
# us3-cab11-discovery.yml

# Run discovery playbook with generated inventory
cd /opt/baremetal-automation/ansible
ansible-playbook playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab10-discovery.yml

# Validate inventory file
python3 /opt/baremetal-automation/python/src/baremetal/lint_yaml.py \
  /var/lib/kea/discovery/us3-cab10-discovery.yml
```

### Step 8: Monitoring and Maintenance

**Check Service Health:**
```bash
# Service status
sudo systemctl status kea-lease-monitor.service
sudo systemctl status kea-dhcp4-server.service

# Recent logs
sudo journalctl -u kea-lease-monitor.service -n 100 --no-pager

# Follow logs in real-time
sudo journalctl -u kea-lease-monitor.service -f
```

**Monitor Inventory Files:**
```bash
# List all cabinet inventories
ls -lh /var/lib/kea/discovery/

# Check cabinet totals
for file in /var/lib/kea/discovery/*-discovery.yml; do
  echo "=== $file ==="
  grep 'total_count:' "$file"
done

# View specific cabinet
cat /var/lib/kea/discovery/us3-cab10-discovery.yml
```

**Log Rotation:**

Create `/etc/logrotate.d/kea-lease-monitor`:

```
/var/log/baremetal/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 kea kea
    sharedscripts
    postrotate
        systemctl reload kea-lease-monitor.service > /dev/null 2>&1 || true
    endscript
}
```

### Troubleshooting

**Service Won't Start:**
```bash
# Check journal for errors
sudo journalctl -u kea-lease-monitor.service -n 50

# Verify Python script can execute
sudo -u kea python3 /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py --help

# Check permissions
ls -l /var/lib/kea/discovery/
ls -l /var/lib/kea/kea-leases4.csv
```

**No Inventory Files Generated:**
```bash
# Check if Kea is creating leases
sudo tail -f /var/lib/kea/kea-leases4.csv

# Verify lease monitor is polling
sudo journalctl -u kea-lease-monitor.service -f

# Test manually with debug output
sudo -u kea python3 /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --once \
  --log-level DEBUG
```

**Permission Errors:**
```bash
# Fix ownership
sudo chown -R kea:kea /var/lib/kea/discovery
sudo chown -R kea:kea /opt/baremetal-automation

# Fix permissions
sudo chmod 750 /var/lib/kea/discovery
sudo chmod +x /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py
```

### Optional: Scheduled Discovery Runs

Create cron job to run discovery automatically:

```bash
# Edit crontab for automation user
sudo crontab -e -u ansible

# Add entry (every 15 minutes for each site)
*/15 * * * * for inv in /var/lib/kea/discovery/*-discovery.yml; do ansible-playbook /opt/baremetal-automation/ansible/playbooks/discovery.yml -e @"$inv" >> /var/log/baremetal/discovery-cron.log 2>&1; done
```

Or create systemd timer for more control - see [systemd timer documentation](https://www.freedesktop.org/software/systemd/man/systemd.timer.html).

## Future Enhancements

See `docs/.DESIGN.md` for planned enhancements:
- Direct Spacelift API integration
- S3/object storage for inventory files
- Webhook notifications for discovery events
- Rate limiting and duplicate lease handling
- Site-aware routing for multi-datacenter deployments
