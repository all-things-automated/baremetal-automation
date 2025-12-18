# Ansible Role: kea_deploy

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Ansible](https://img.shields.io/badge/ansible-2.17.14%2B-green.svg)](https://www.ansible.com/)

A comprehensive Ansible role for deploying and configuring Kea DHCP servers with automated BMC discovery integration. This role handles complete Kea installation, configuration management, hook script deployment, and systemd service setup for the lease monitor.

## Overview

The `kea_deploy` role automates the deployment of Kea DHCP infrastructure for bare-metal BMC discovery workflows. It provides:

- **Kea DHCP Server Installation**: Packages and dependencies (Ubuntu 24.04 LTS)
- **Configuration Management**: Jinja2-templated kea-dhcp4.conf with site-specific parameters
- **PostgreSQL Database Backend**: Static DHCP reservations with transactional integrity
- **Unified Lease Monitor Service**: Single service for discovery, database reservations, and DNS
- **Event-Driven DNS Integration**: Transactional DNS record creation with database reservations
- **Directory Structure**: Creates required directories with proper permissions
- **Validation**: Configuration syntax checking and service health verification

### Key Features

- **Idempotent Deployment**: Safe to run repeatedly for configuration updates
- **Multi-Site Support**: Parameterized for multiple datacenters/sites
- **Flexible Configuration**: Extensive variable defaults with per-site overrides
- **Unified Service Architecture**: Single lease monitor service for all functionality
- **Database-Driven Workflow**: PostgreSQL backend for static reservations
- **Transactional DNS**: Atomic database + DNS operations (rollback on failure)
- **Event-Driven Processing**: Immediate DNS creation upon lease detection
- **Security Best Practices**: Proper user permissions, restricted file access
- **Validation**: Pre-deployment config testing and post-deployment verification

## Requirements

### Ansible Version

- Ansible >= 2.17.14

### Target System

- **Operating System**: Ubuntu 24.04 LTS (or compatible Debian-based)
- **Architecture**: x86_64
- **Python**: Python 3.10+ with pip
- **Privileges**: Root or sudo access required

### Collections

This role uses standard Ansible modules (no external collections required):

```yaml
# Built-in modules used:
- ansible.builtin.apt
- ansible.builtin.template
- ansible.builtin.file
- ansible.builtin.systemd
- ansible.builtin.user
- ansible.builtin.pip
```

### Python Dependencies

Role automatically installs:
- `pyyaml>=6.0` (for lease monitor script)

## Role Variables

### Required Variables

These variables **must** be defined for your environment:

```yaml
# Network interface for DHCP server
kea_interface: "enp23s0f0np0"

# Subnet configuration
kea_subnet_cidr: "172.30.16.0/22"
kea_pool_start: "172.30.19.24"
kea_pool_end: "172.30.19.100"
kea_gateway: "172.30.16.1"

# DNS configuration
kea_dns_servers: "192.168.204.52"
kea_domain_name: "site.com"
```

### Optional Variables (with defaults)

```yaml
# Kea DHCP server configuration
kea_subnet_id: 1                          # Subnet identifier
kea_lease_lifetime: 600                   # Default lease time (seconds)
kea_max_lease_lifetime: 7200              # Maximum lease time (seconds)
kea_lfc_interval: 3600                    # Lease file cleanup interval (seconds)

# Database backend configuration (PostgreSQL for host reservations)
kea_enable_database: false                # Enable PostgreSQL database backend
kea_db_host: "localhost"                 # PostgreSQL server hostname
kea_db_port: 5432                         # PostgreSQL server port
kea_db_name: "kea"                        # Database name
kea_db_user: "kea"                        # Database username
kea_db_password: ""                       # Database password (use Ansible Vault)
kea_db_init_schema: true                  # Initialize Kea schema if not present
kea_db_validate_connection: true          # Test database connectivity before config

# DNS integration configuration (event-driven, transactional)
kea_enable_dns: false                     # Enable DNS record creation
kea_dns_zone: ""                          # DNS zone (e.g., example.com)

# Hook configuration
kea_enable_hook: false                    # Enable run_script hook
kea_hook_script_path: "/usr/share/kea/scripts/kea-ansible-hook.sh"
kea_hook_sync: false                      # Synchronous hook execution

# Lease monitor configuration
kea_enable_lease_monitor: true            # Deploy unified lease monitor service
kea_lease_monitor_poll_interval: 5        # Poll interval (seconds)
kea_lease_monitor_log_level: "INFO"      # Log level: DEBUG, INFO, WARNING, ERROR

# File paths
kea_config_dir: "/etc/kea"
kea_lease_file: "/var/lib/kea/kea-leases4.csv"
kea_discovery_output_dir: "/var/lib/kea/discovery"
kea_log_dir: "/var/log/kea"

# Application deployment
kea_app_base_dir: "/opt/baremetal-automation"
kea_venv_path: "{{ kea_app_base_dir }}/venv"
kea_use_venv: true                        # Use Python virtual environment

# Service management
kea_service_user: "kea"
kea_service_group: "kea"
kea_restart_services: true                # Restart services after config changes
```

### Advanced Variables

```yaml
# Additional subnet-specific DHCP options
kea_additional_options: []
# Example:
# kea_additional_options:
#   - name: "ntp-servers"
#     data: "192.168.1.10"
#   - name: "tftp-server-name"
#     data: "tftp.example.com"

# Custom hook libraries (advanced)
kea_custom_hooks: []
# Example:
# kea_custom_hooks:
#   - library: "/usr/lib/kea/hooks/libdhcp_mysql.so"
#     parameters:
#       type: "mysql"
#       host: "localhost"

# Firewall management (if using ufw)
kea_configure_firewall: false
kea_dhcp_port: 67
```

## Dependencies

None. This role is self-contained.

## Example Playbook

### Basic Single-Site Deployment

```yaml
---
- name: Deploy Kea DHCP server for BMC discovery
  hosts: dhcp_servers
  become: true
  
  vars:
    kea_interface: "enp23s0f0np0"
    kea_subnet_cidr: "172.30.16.0/22"
    kea_pool_start: "172.30.19.24"
    kea_pool_end: "172.30.19.100"
    kea_gateway: "172.30.16.1"
    kea_dns_servers: "192.168.204.52, 192.168.204.53"
    kea_domain_name: "site.com"
    kea_enable_lease_monitor: true
  
  roles:
    - kea_deploy
```

### Multi-Site Deployment with Group Variables

**Inventory** (`inventory/production.ini`):

```ini
[dhcp_servers]
us3-dhcp-01 ansible_host=10.0.3.10
us4-dhcp-01 ansible_host=10.0.4.10

[dhcp_servers:vars]
ansible_user=ansible
ansible_become=true

[us3]
us3-dhcp-01

[us4]
us4-dhcp-01
```

**Group Variables** (`group_vars/us3.yml`):

```yaml
---
# US3 Datacenter DHCP Configuration
kea_interface: "enp23s0f0np0"
kea_subnet_id: 1
kea_subnet_cidr: "172.30.16.0/22"
kea_pool_start: "172.30.19.24"
kea_pool_end: "172.30.19.100"
kea_gateway: "172.30.16.1"
kea_dns_servers: "192.168.204.52, 192.168.204.53"
kea_domain_name: "us3.site.com"
```

**Group Variables** (`group_vars/us4.yml`):

```yaml
---
# US4 Datacenter DHCP Configuration
kea_interface: "ens192"
kea_subnet_id: 2
kea_subnet_cidr: "172.31.16.0/22"
kea_pool_start: "172.31.19.24"
kea_pool_end: "172.31.19.100"
kea_gateway: "172.31.16.1"
kea_dns_servers: "192.168.205.52, 192.168.205.53"
kea_domain_name: "us4.site.com"
```

**Global Variables** (`group_vars/all.yml`):

```yaml
---
# Global Kea DHCP Settings
kea_lease_lifetime: 600
kea_max_lease_lifetime: 7200
kea_lfc_interval: 3600
kea_enable_lease_monitor: true
kea_lease_monitor_poll_interval: 30
kea_lease_monitor_log_level: "INFO"
```

**Playbook** (`playbooks/kea_deploy.yml`):

```yaml
---
- name: Deploy Kea DHCP servers across datacenters
  hosts: dhcp_servers
  become: true
  
  roles:
    - kea_deploy
  
  post_tasks:
    - name: Display deployment summary
      ansible.builtin.debug:
        msg: |
          Kea DHCP deployed on {{ inventory_hostname }}
          Subnet: {{ kea_subnet_cidr }}
          Pool: {{ kea_pool_start }} - {{ kea_pool_end }}
          Monitor: {{ 'enabled' if kea_enable_lease_monitor else 'disabled' }}
```

### Configuration Update Deployment

```yaml
---
- name: Update Kea DHCP configuration
  hosts: dhcp_servers
  become: true
  
  vars:
    kea_restart_services: true  # Force restart after config change
  
  roles:
    - kea_deploy
  
  tasks:
    - name: Validate Kea is running
      ansible.builtin.systemd:
        name: kea-dhcp4-server
        state: started
      check_mode: true
      register: kea_status
    
    - name: Display service status
      ansible.builtin.debug:
        msg: "Kea DHCP4 is {{ kea_status.status.ActiveState }}"
```

### Development/Testing Deployment

```yaml
---
- name: Deploy Kea DHCP for testing
  hosts: test_dhcp
  become: true
  
  vars:
    kea_interface: "eth0"
    kea_subnet_cidr: "192.168.100.0/24"
    kea_pool_start: "192.168.100.100"
    kea_pool_end: "192.168.100.200"
    kea_gateway: "192.168.100.1"
    kea_dns_servers: "8.8.8.8, 8.8.4.4"
    kea_domain_name: "test.local"
    kea_lease_lifetime: 300  # Shorter leases for testing
    kea_enable_lease_monitor: true
    kea_lease_monitor_log_level: "DEBUG"
  
  roles:
    - kea_deploy
```

### Database Backend with Transactional DNS

```yaml
---
- name: Deploy Kea DHCP with PostgreSQL backend and DNS integration
  hosts: dhcp_servers
  become: true
  
  vars:
    # Network configuration
    kea_interface: "enp23s0f0np0"
    kea_subnet_cidr: "172.30.16.0/22"
    kea_pool_start: "172.30.19.24"
    kea_pool_end: "172.30.19.100"
    kea_gateway: "172.30.16.1"
    kea_dns_servers: "192.168.204.52"
    kea_domain_name: "site.com"
    
    # Database backend configuration
    kea_enable_database: true
    kea_db_host: "{{ ansible_default_ipv4.address }}"  # Local PostgreSQL
    kea_db_port: 5432
    kea_db_name: "kea"
    kea_db_user: "kea"
    kea_db_password: "{{ vault_kea_db_password }}"  # From Ansible Vault
    kea_db_init_schema: true
    kea_db_validate_connection: true
    
    # DNS integration (event-driven)
    kea_enable_dns: true
    kea_dns_zone: "site.com"
  
  roles:
    - kea_deploy
  
  post_tasks:
    - name: Display deployment status
      ansible.builtin.debug:
        msg: |
          Database Backend: PostgreSQL @ {{ kea_db_host }}:{{ kea_db_port }}
          DNS Integration: {{ 'Enabled' if kea_enable_dns else 'Disabled' }}
          DNS Zone: {{ kea_dns_zone if kea_enable_dns else 'N/A' }}
          
          Workflow:
          1. BMC receives DHCP lease (memfile storage)
          2. Lease monitor detects new lease with hostname
          3. Discovery inventory file created
          4. Static reservation created in PostgreSQL
          5. DNS A record created (transactional)
          
          Transaction guarantees:
          - Both DB reservation AND DNS record succeed, or neither
          - Automatic rollback if DNS creation fails
          - No orphaned database entries without DNS
```

**Transaction-Based Workflow**:
```
DHCP Lease → Discovery YAML → Static Reservation → DNS Record
                                      ↓                 ↓
                              [TRANSACTION START]  [Same TX]
                                      ↓                 ↓
                                 INSERT hosts     CREATE A record
                                      ↓                 ↓
                                   SUCCESS? ←──── SUCCESS?
                                      ↓ YES            ↓ NO
                                   COMMIT         ROLLBACK
```

**Note**: When using database backend:
- Dynamic leases stored in memfile (CSV) for performance
- Static reservations stored in PostgreSQL database
- DNS records created atomically with reservations
- Requires PostgreSQL server (automatically configured)
- Use Ansible Vault to encrypt `kea_db_password`
- Database schema automatically initialized on first deployment
- DNS integration currently logs records (SOLIDserver integration pending)
- See [kea-database-backend.md](../../docs/kea-database-backend.md) for details

### Create Encrypted Password with Ansible Vault

```bash
# Create vault file for database password
ansible-vault create group_vars/dhcp_servers/vault.yml

# Content:
vault_kea_db_password: "your-secure-password-here"

# Use in playbook with --ask-vault-pass
ansible-playbook playbooks/kea_deploy.yml --ask-vault-pass
```

## Role Tasks Overview

The role performs the following tasks in order:

1. **Validation**: Check required variables are defined
2. **Package Installation**: Install Kea DHCP server and dependencies
3. **User/Group Setup**: Ensure kea system user exists
4. **Directory Structure**: Create required directories with proper permissions
5. **Python Environment**: Set up virtual environment and install dependencies
6. **Application Deployment**: Copy lease monitor script and utilities
7. **Configuration Rendering**: Generate kea-dhcp4.conf from template
8. **Configuration Validation**: Test configuration syntax
9. **Hook Deployment**: Deploy hook script if enabled
10. **Service Configuration**: Create systemd unit files
11. **Service Management**: Enable and start services
12. **Post-Deployment Validation**: Verify services are running

## Directory Structure Created

```
/etc/kea/
├── kea-dhcp4.conf                    # Main configuration file
└── kea-ctrl-agent.conf               # Control agent config (if needed)

/var/lib/kea/
├── kea-leases4.csv                   # Lease database
└── discovery/                        # Inventory output directory
    ├── us3-cab10-discovery.yml
    ├── us3-cab11-discovery.yml
    └── ...

/var/log/kea/
├── kea-dhcp4.log                     # DHCP server logs
└── kea-lease-monitor.log             # Lease monitor logs

/opt/baremetal-automation/
├── venv/                             # Python virtual environment
├── python/
│   └── src/baremetal/
│       ├── kea_lease_monitor.py
│       └── __init__.py
└── requirements.txt

/usr/share/kea/scripts/               # Optional hook scripts
└── kea-ansible-hook.sh
```

## Service Management

### Systemd Services Created

1. **kea-dhcp4-server.service** - Kea DHCP server (package-provided)
2. **kea-lease-monitor.service** - Unified lease monitor daemon (role-created)
   - Discovery inventory generation
   - Static reservation creation (if database enabled)
   - DNS record creation (if DNS enabled)

### Service Commands

```bash
# Check service status
sudo systemctl status kea-dhcp4-server
sudo systemctl status kea-lease-monitor

# View logs
sudo journalctl -u kea-dhcp4-server -f
sudo journalctl -u kea-lease-monitor -f

# Restart services
sudo systemctl restart kea-dhcp4-server
sudo systemctl restart kea-lease-monitor

# Reload configuration (without restart)
sudo systemctl reload kea-dhcp4-server

# Check database reservations (if database backend enabled)
psql -h localhost -U kea -d kea -c "SELECT hostname, encode(dhcp_identifier, 'hex') as mac, ipv4_address FROM hosts;"

# Manual test of lease monitor with database
sudo -u _kea python3 /opt/baremetal-automation/kea_lease_monitor.py \
  --db-host localhost --db-user kea --db-password 'password' \
  --enable-dns --dns-zone example.com \
  --once --log-level DEBUG
```

## Handlers

The role includes handlers for service management:

- `restart kea-dhcp4-server` - Restarts DHCP server when configuration changes
- `restart kea-lease-monitor` - Restarts lease monitor when script/config changes
- `reload kea-dhcp4-server` - Reloads configuration without full restart
- `restart postgresql` - Restarts PostgreSQL when network config changes (database mode)
- `reload postgresql` - Reloads PostgreSQL configuration (database mode)

## Tags

Use tags for selective task execution:

```bash
# Only install packages
ansible-playbook playbooks/kea_deploy.yml --tags packages

# Only update configuration
ansible-playbook playbooks/kea_deploy.yml --tags config

# Only manage services
ansible-playbook playbooks/kea_deploy.yml --tags services

# Skip service restart
ansible-playbook playbooks/kea_deploy.yml --skip-tags restart
```

Available tags:
- `packages` - Package installation
- `config` - Configuration file management
- `validation` - Configuration validation
- `scripts` - Hook script deployment
- `services` - Service management
- `restart` - Service restart operations

## Post-Deployment Verification

After role execution, verify deployment:

```bash
# Test configuration
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf

# Check services
sudo systemctl status kea-dhcp4-server kea-lease-monitor

# View recent logs
sudo journalctl -u kea-dhcp4-server -n 50
sudo journalctl -u kea-lease-monitor -n 50

# Check lease file
cat /var/lib/kea/kea-leases4.csv

# List generated inventories
ls -lh /var/lib/kea/discovery/
```

## Integration with Discovery Workflow

Once deployed, the Kea DHCP server automatically generates cabinet-aware inventory files:

```bash
# Inventory files are created as BMCs receive leases
/var/lib/kea/discovery/us3-cab10-discovery.yml
/var/lib/kea/discovery/us3-cab11-discovery.yml

# Run discovery against generated inventory
cd /opt/baremetal-automation/ansible
ansible-playbook playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab10-discovery.yml
```

## Troubleshooting

### Kea Won't Start

```bash
# Check configuration syntax
sudo kea-dhcp4 -t /etc/kea/kea-dhcp4.conf

# Check journal for errors
sudo journalctl -u kea-dhcp4-server -n 50

# Verify interface exists
ip link show {{ kea_interface }}

# Check permissions
sudo ls -la /var/lib/kea/
```

### Lease Monitor Not Generating Inventories

```bash
# Check service is running
sudo systemctl status kea-lease-monitor

# Check for leases in file
sudo cat /var/lib/kea/kea-leases4.csv

# View service logs
sudo journalctl -u kea-lease-monitor -n 50

# Run manually for debugging (without database)
sudo -u _kea python3 /opt/baremetal-automation/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --once \
  --log-level DEBUG

# Run manually with database and DNS
sudo -u _kea python3 /opt/baremetal-automation/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --db-host localhost --db-user kea --db-password 'password' \
  --enable-dns --dns-zone example.com \
  --sync-existing \
  --once \
  --log-level DEBUG
```

### Database Reservations Not Being Created

```bash
# Check if psycopg2 is installed
python3 -c "import psycopg2; print('psycopg2 installed')"

# Verify database connectivity
psql -h localhost -U kea -d kea -c "SELECT version();"

# Check existing reservations
psql -h localhost -U kea -d kea -c "SELECT * FROM hosts;"

# Check service command includes database parameters
ps aux | grep kea_lease_monitor

# Expected output should include:
# --db-host localhost --db-user kea --db-password ... --subnet-id 1 --sync-existing

# Verify service file has database config
cat /etc/systemd/system/kea-lease-monitor.service

# If service file was updated, reload systemd
sudo systemctl daemon-reload
sudo systemctl restart kea-lease-monitor
```

### DNS Records Not Being Created

```bash
# Check if DNS is enabled in service
ps aux | grep kea_lease_monitor | grep enable-dns

# View DNS-related logs
sudo journalctl -u kea-lease-monitor | grep DNS

# Expected log entries:
# "DNS record creation enabled: zone=example.com"
# "[DNS] Would create A record: hostname.example.com -> 172.30.19.42"
# "Transaction complete: reservation host_id=1, DNS record created"

# Note: DNS integration currently logs records (SOLIDserver integration pending)
```

### Permission Errors

```bash
# Fix ownership
sudo chown -R kea:kea /var/lib/kea/discovery
sudo chown -R kea:kea /opt/baremetal-automation

# Fix permissions
sudo chmod 750 /var/lib/kea/discovery
sudo chmod +x /opt/baremetal-automation/python/src/baremetal/kea_lease_monitor.py
```

## Security Considerations

- Kea runs as unprivileged `kea` user
- Output directory restricted to `kea:kea` with `750` permissions
- Configuration files readable only by root and kea group
- Lease monitor runs with minimal privileges
- No external network access required for lease monitor
- Logs sanitized of sensitive information

## Maintenance

### Configuration Updates

To update configuration:

1. Modify variables in inventory/group_vars
2. Run playbook: `ansible-playbook playbooks/kea_deploy.yml`
3. Services restart automatically if `kea_restart_services: true`

### Log Rotation

Role automatically configures logrotate for Kea logs:

```
/var/log/kea/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 kea kea
    sharedscripts
    postrotate
        systemctl reload kea-dhcp4-server > /dev/null 2>&1 || true
        systemctl reload kea-lease-monitor > /dev/null 2>&1 || true
    endscript
}
```

## License

MIT

## Author Information

This role was created for the bare-metal automation project.

For issues or contributions, see the project repository.
