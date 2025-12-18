# Python Utilities

This directory contains Python scripts for maintenance, validation, and quality assurance of the Ansible automation project.

## Scripts Overview

### fix_ansible_lint.py

Automatically fixes ansible-lint issues, focusing on trailing whitespace violations.

**Purpose:**
- Runs ansible-lint on roles or playbooks directories
- Automatically fixes `yaml[trailing-spaces]` violations
- Supports batch processing of multiple targets
- **Used in CI/CD pipeline for automated Ansible code validation**

**Usage:**
```bash
# Lint and fix all roles
python fix_ansible_lint.py ../ansible/roles

# Lint and fix all playbooks
python fix_ansible_lint.py ../ansible/playbooks

# Process multiple directories
python fix_ansible_lint.py ../ansible/roles ../ansible/playbooks
```

**Features:**
- Detects target type automatically (roles vs playbooks directories)
- Expands roles directory into individual role paths
- Processes playbook files individually
- Multi-target support with progress tracking
- Summary report with statistics

**Requirements:**
- Python 3.6+
- ansible-lint installed (`pip install ansible-lint`)

---

### lint_yaml.py

Simple YAML validator and formatter for discovery artifacts and configuration files.

**Purpose:**
- Validates YAML syntax across files and directories
- Normalizes YAML formatting to standard style
- Ensures artifacts are valid before processing

**Usage:**
```bash
# Validate YAML files
python lint_yaml.py ../ansible/playbooks/artifacts/

# Validate and reformat YAML
python lint_yaml.py --fix ../ansible/playbooks/artifacts/

# Process specific files
python lint_yaml.py file1.yml file2.yml

# Process multiple paths
python lint_yaml.py ../ansible/roles/ ../ansible/playbooks/
```

**Features:**
- Recursive directory scanning for `.yml` and `.yaml` files
- Validation-only mode (default)
- Auto-formatting mode with `--fix` flag
- Only rewrites files when changes needed
- Clear status indicators: `[OK]`, `[FIXED]`, `[ERROR]`, `[SKIP]`

**Formatting Style:**
- Preserves key order (`sort_keys=False`)
- Block style for collections
- Unicode support
- Consistent indentation

**Requirements:**
- Python 3.6+
- PyYAML installed (`pip3 install pyyaml`)

**Note:** Validates YAML output from `discovery_artifact.yml.j2` template to ensure proper formatting before NetBox registration.

---

### kea_lease_hook.py

Kea DHCP hook script that triggers automated bare-metal discovery when BMCs receive DHCP leases (per-lease processing).

**Purpose:**
- Integrates with Kea DHCP server `lease4_commit` hook
- Generates Ansible inventory files with single BMC IP per lease
- Provides real-time trigger mechanism for discovery automation
- Supports multi-site subnet filtering

**Usage:**
```bash
# Manual testing
python3 src/baremetal/kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55

# With custom output directory
python3 src/baremetal/kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55 --output-dir /tmp/kea-test

# Debug mode
python3 src/baremetal/kea_lease_hook.py --ip 172.30.19.42 --mac 00:11:22:33:44:55 --log-level DEBUG

# Production (called by Kea with environment variables)
KEA_LEASE4_ADDRESS=172.30.19.42 KEA_LEASE4_HWADDR=00:11:22:33:44:55 python3 src/baremetal/kea_lease_hook.py
```

**Features:**
- Generates Ansible-compatible inventory YAML (single lease)
- Validates IP address format
- Subnet filtering for multi-datacenter deployments
- Comprehensive logging and error handling
- Metadata tracking (timestamp, MAC, hostname)

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
```

**Environment Variables:**
- `KEA_HOOK_OUTPUT_DIR` - Output directory (default: `/var/lib/kea/discovery`)
- `KEA_HOOK_SUBNET_FILTER` - Comma-separated subnet IDs to process
- `KEA_HOOK_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `KEA_LEASE4_ADDRESS` - Leased IPv4 address (set by Kea)
- `KEA_LEASE4_HWADDR` - BMC MAC address (set by Kea)
- `KEA_SUBNET4` - Subnet identifier (set by Kea)
- `KEA_LEASE4_HOSTNAME` - Client hostname (set by Kea)

**Requirements:**
- Python 3.8+
- PyYAML installed (`pip3 install -r requirements.txt`)

---

### kea_lease_monitor.py

Continuous DHCP lease file monitor that generates consolidated batch inventories for automated discovery (recommended approach).

**Purpose:**
- Polls Kea lease CSV file for new DHCP leases
- Generates/updates permanent inventory files per site and cabinet
- Extracts site and cabinet ID from BMC hostnames (e.g., `us3-cab10-ru17-idrac`)
- Appends new IPs to existing files (incremental updates)
- Handles unknown/mixed sites or cabinets with `unknown-unknown-discovery.yml`
- Provides scalable alternative to per-lease hook processing
- Future-proof design supports database backend migration

**Usage:**
```bash
# Continuous monitoring (production)
python3 src/baremetal/kea_lease_monitor.py \
  --lease-file /var/lib/kea/kea-leases4.csv \
  --output-dir /var/lib/kea/discovery \
  --poll-interval 30

# One-time scan (testing)
python3 src/baremetal/kea_lease_monitor.py \
  --lease-file tests/fixtures/kea-leases4.csv \
  --output-dir tests/output \
  --once \
  --log-level DEBUG

# With subnet filtering
python3 src/baremetal/kea_lease_monitor.py \
  --subnet-filter 1,10,20 \
  --log-level INFO
```

**Features:**
- Permanent inventory files per cabinet (incremental updates)
- Cabinet-aware file naming: `{site}-{cabinet}-discovery.yml`
- Automatic hostname parsing: site prefix + cabinet ID (e.g., `us3-cab10`)
- Appends new IPs to existing files (no duplicates)
- Unknown site/cabinet handling for missing/inconsistent hostnames
- Pluggable architecture (FileLeaseSource, future DatabaseLeaseSource)
- Processed lease tracking (prevents duplicates)
- One-time scan or continuous monitoring modes
- Subnet filtering for multi-site deployments

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

**Filename Convention:**
- Format: `{site}-{cabinet}-discovery.yml`
- Hostname format: `{site}-{cabinet}-{rack}-{device}` (e.g., `us3-cab10-ru17-idrac`)
- Examples: `us3-cab10-discovery.yml`, `us3-cab11-discovery.yml`, `dv-cab01-discovery.yml`
- Unknown: `unknown-unknown-discovery.yml` (hostnames missing or inconsistent)
- Files are **permanent** and updated incrementally

**Manufacturer Detection:**
- Automatically detected per-host from hostname suffix
- Used for future OEM-specific Ansible tasks
- `-idrac` → Dell | `-ilo` → HP | `-bmc` → Supermicro
- Stored per-lease in `metadata.leases[].manufacturer`

**Ansible Integration:**
```bash
# Use specific cabinet inventory
ansible-playbook ansible/playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab10-discovery.yml

# Different cabinet
ansible-playbook ansible/playbooks/discovery.yml \
  -e @/var/lib/kea/discovery/us3-cab11-discovery.yml

# Review unknown cabinets
ls /var/lib/kea/discovery/unknown-*
```

**Command-Line Options:**
- `--lease-file PATH` - Kea lease CSV file (default: `/var/lib/kea/kea-leases4.csv`)
- `--output-dir PATH` - Output directory (default: `/var/lib/kea/discovery`)
- `--subnet-filter IDS` - Comma-separated subnet IDs to monitor
- `--poll-interval SECONDS` - Polling interval (default: 5)
- `--once` - Process once and exit (no continuous monitoring)
- `--log-level LEVEL` - DEBUG, INFO, WARNING, ERROR (default: INFO)

**Architecture:**
- Abstract `LeaseSource` interface for pluggable backends
- `FileLeaseSource` - Current CSV file implementation
- `DatabaseLeaseSource` - Future PostgreSQL/MySQL support (stub)
- No refactoring needed for database migration

**Requirements:**
- Python 3.8+
- PyYAML installed (`pip3 install -r requirements.txt`)

**Integration:**
See `docs/KEA.md` for Kea DHCP server configuration, systemd service setup, and workflow patterns.

---

## Installation

Install required Python packages:

```bash
# All utilities
pip3 install ansible-lint pyyaml

# Kea hook only
pip3 install -r requirements.txt
```

Or using requirements file:

```bash
pip3 install -r requirements.txt
```

---

## Common Workflows

### Pre-commit Validation

Before committing changes, validate all YAML files:

```bash
python lint_yaml.py ../ansible/
```

### Clean Up Ansible Roles

Fix linting issues across all roles:

```bash
python fix_ansible_lint.py ../ansible/roles
```

### Validate Discovery Artifacts

Check artifacts generated by discovery role:

```bash
python lint_yaml.py ../ansible/playbooks/artifacts/
```

### Format All YAML Files

Normalize formatting across entire project:

```bash
python lint_yaml.py --fix ../ansible/
```

---

## Output Standards

All scripts follow consistent output formatting:

- **[OK]** - Operation successful, no changes needed
- **[FIXED]** - File was modified/corrected
- **[ERROR]** - Operation failed (syntax error, file issue)
- **[SKIP]** - File skipped (invalid, not applicable)
- **[WARNING]** - Non-fatal issue detected

Exit codes:
- `0` - All operations successful
- `1` - One or more failures encountered

---

## Development Notes

### Script Standards

All Python utilities follow these conventions:
- ASCII-only output (no Unicode symbols)
- Status prefixes: `[OK]`, `[ERROR]`, `[WARNING]`, `[FIXED]`, `[SKIP]`
- Multi-file processing with `nargs="+"`
- Type hints for function signatures
- Comprehensive docstrings (module, class, function level)
- Summary output for batch operations

### Adding New Scripts

When creating new utilities:
1. Follow the established output format
2. Use `argparse` with `RawDescriptionHelpFormatter`
3. Include usage examples in module docstring
4. Support batch processing where applicable
5. Provide clear error messages
6. Update this README with script documentation
