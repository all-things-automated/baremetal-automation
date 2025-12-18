# Ansible Role: Discovery

[![MIT License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Ansible](https://img.shields.io/badge/ansible-2.17.14%2B-green.svg)](https://www.ansible.com/)

A comprehensive Ansible role for automated discovery and inventory collection from Redfish-compliant Baseboard Management Controllers (BMCs). This role queries BMC interfaces (Dell iDRAC, HPE iLO, etc.) and generates structured YAML artifacts containing detailed hardware inventory data.

## Overview

The `discovery` role automates the process of collecting hardware inventory from bare-metal servers via their BMC Redfish APIs. It produces clean, standardized YAML reports containing:

- Physical server identity and location information
- System hardware specifications
- Storage controllers and drive inventory
- Network interface configurations
- Virtual media status
- Comprehensive hardware metadata

### Key Features

- **Multi-BMC Discovery**: Process multiple BMCs in a single playbook run
- **Redfish Standard Compliance**: Works with Dell iDRAC, HPE iLO, and other Redfish-compliant BMCs
- **Structured Output**: Generates clean, parseable YAML artifacts
- **FQDN Resolution**: Automatically resolves and includes BMC FQDNs
- **Rack Location Parsing**: Extracts cabinet and rack unit information from hostnames
- **Idempotent**: Safe to run repeatedly without side effects
- **Comprehensive Inventory**: Captures system, storage, network, and virtual media details

## Requirements

### Ansible Version

- Ansible >= 2.17.14

### Collections

This role requires the following Ansible collections:

```yaml
collections:
  - community.general  # For redfish_info module
```

Install required collections:

```bash
ansible-galaxy collection install community.general
```

### Python Dependencies

The target control node (where Ansible runs) requires:

- Python >= 3.8
- `requests` Python library (for Redfish API communication)

### Network Access

- Network connectivity from the Ansible control node to BMC IP addresses
- BMC credentials with read access to Redfish APIs
- BMCs must support Redfish API version 1.0 or later

### Supported BMC Types

Tested and verified with:

- Dell iDRAC 9 (PowerEdge 14th/15th/16th generation servers)
- HPE iLO 5/6
- Supermicro Redfish-compliant BMCs
- Any Redfish 1.0+ compliant BMC implementation

## Role Variables

### Required Variables

These variables **must** be provided either through environment variables, extra vars, or encrypted vault files:

```yaml
# BMC authentication credentials
discovery_bmc_username: ""  # BMC username (e.g., "root", "admin")
discovery_bmc_password: ""  # BMC password

# List of target BMCs to discover
bmc_targets: []
  # Example:
  # - ip: "172.30.19.42"
  #   name: "optional-name"  # Optional friendly name
  # - ip: "172.30.19.48"
```

### Optional Variables (Defaults)

These variables have sensible defaults but can be overridden:

```yaml
# Output directory for discovery artifacts
# Default: ../artifacts relative to playbook directory
discovery_artifact_dir: "{{ playbook_dir }}/../artifacts"

# Template file name (Ansible will look in role's templates/ directory)
# Default: discovery_artifact.yml.j2
discovery_template_path: "discovery_artifact.yml.j2"

# Lifecycle state to embed in discovery artifacts
# Options: discovered, commissioned, deployed, repurpose-ready, or empty string
# Default: "discovered" (normal initial discovery)
# Use cases:
#   - "discovered": Initial discovery or post-wipe rediscovery
#   - "": Empty/null to preserve existing state in NetBox (audit discovery)
#   - Other states: Rarely used, typically set by commission/deploy/repurpose roles
discovery_lifecycle_state: "discovered"
```

### Recommended: Using Environment Variables

For security, provide credentials via environment variables:

```bash
export BMC_USERNAME="admin"
export BMC_PASSWORD="your-secure-password"
```

Then reference in your playbook:

```yaml
vars:
  discovery_bmc_username: "{{ lookup('env', 'BMC_USERNAME') }}"
  discovery_bmc_password: "{{ lookup('env', 'BMC_PASSWORD') }}"
```

### Recommended: Using Ansible Vault

For production environments, encrypt credentials:

```bash
ansible-vault create group_vars/all/vault.yml
```

Add encrypted credentials:

```yaml
vault_bmc_username: admin
vault_bmc_password: secure-password
```

Reference in playbook:

```yaml
vars:
  discovery_bmc_username: "{{ vault_bmc_username }}"
  discovery_bmc_password: "{{ vault_bmc_password }}"
```

## Dependencies

This role has **no role dependencies**. It is completely self-contained.

Required Ansible collections must be installed separately (see Requirements section).

## Example Playbooks

### Basic Usage

```yaml
---
- name: Discover bare-metal server inventory
  hosts: localhost
  gather_facts: true

  vars:
    discovery_bmc_username: "{{ lookup('env', 'BMC_USERNAME') }}"
    discovery_bmc_password: "{{ lookup('env', 'BMC_PASSWORD') }}"
    
    bmc_targets:
      - ip: "172.30.19.42"
      - ip: "172.30.19.48"
      - ip: "10.0.1.50"

  roles:
    - discovery
```

### Advanced Usage with Custom Output

```yaml
---
- name: Enterprise bare-metal discovery
  hosts: localhost
  gather_facts: true

  vars:
    # Credentials from vault
    discovery_bmc_username: "{{ vault_bmc_username }}"
    discovery_bmc_password: "{{ vault_bmc_password }}"
    
    # Custom artifact location (e.g., mounted NFS share)
    discovery_artifact_dir: "/mnt/inventory-share/discovery"
    
    # BMC targets from inventory or external source
    bmc_targets: "{{ groups['bmc_servers'] | map('extract', hostvars, 'bmc_ip') | list }}"

  roles:
    - discovery

  post_tasks:
    - name: Upload artifacts to S3
      amazon.aws.s3_sync:
        bucket: my-inventory-bucket
        file_root: "{{ discovery_artifact_dir }}"
        key_prefix: "baremetal-inventory/{{ ansible_date_time.date }}"
```

### Discovery with Dynamic Inventory

```yaml
---
- name: Discover from IPAM-sourced BMC list
  hosts: localhost
  gather_facts: true

  vars:
    discovery_bmc_username: "{{ lookup('env', 'BMC_USERNAME') }}"
    discovery_bmc_password: "{{ lookup('env', 'BMC_PASSWORD') }}"

  tasks:
    - name: Query IPAM for BMC addresses
      uri:
        url: "https://ipam.example.com/api/bmcs"
        return_content: yes
      register: ipam_result

    - name: Build BMC target list
      set_fact:
        bmc_targets: "{{ ipam_result.json | map(attribute='ip') | map('regex_replace', '^(.*)$', {'ip': '\\1'}) | list }}"

  roles:
    - discovery
```

## Output Format

### Artifact Structure

Each BMC generates a YAML artifact named `<BMC_IP>-discovery.yml` with the following structure:

```yaml
physical_identity:
  bmc_ip: 172.30.19.42
  bmc_name: us3-cab10-ru17-idrac
  bmc_fqdn: us3-cab10-ru17-idrac.site.com
  cabinet_id: '10'
  rack_unit_from: '17'
  rack_unit_to: '17'
  discover_timestamp: '2025-12-03T17:15:58Z'
  lifecycle_state: discovered  # Set by discovery_lifecycle_state variable

system_information:
- category: System
  type: System
  id: System.Embedded.1
  manufacturer: Dell Inc.
  model: PowerEdge R660
  serial_number: MXWSJ0047O01SH
  bios_version: 2.2.8
  power_state: 'On'
  # ... additional system fields

storage_controllers:
- category: Storage
  type: Controller
  id: BOSS.SL.12-1
  name: BOSS-N1 Monolithic
  # ... controller details

storage_drives:
- category: Storage
  type: Drive
  id: Disk.Direct.0-0:BOSS.SL.12-1
  capacity_gb: 447.13
  media_type: SSD
  # ... drive details

network_interfaces:
- category: Network
  type: NIC
  mac_address: C4:CB:E1:D6:12:AE
  speed_mbps: 25000
  # ... interface details

virtual_media:
- category: System
  type: VirtualMedia
  # ... virtual media details

collection_info:
  total_categories: 5
  categories_collected:
    - system_information
    - storage_controllers
    - storage_drives
    - network_interfaces
    - virtual_media
```

### Hostname Parsing Logic

The role automatically extracts location information from BMC FQDNs:

**Pattern**: `<site>-cab<cabinet_id>-ru<rack_unit>[-<rack_unit_end>]-<bmc_type>`

**Examples**:
- `us3-cab10-ru17-idrac` → Cabinet: 10, RU: 17-17
- `dc1-cab05-ru12-18-ilo` → Cabinet: 5, RU: 12-18 (multi-RU system)
- `lab-cab2-ru03-idrac` → Cabinet: 2, RU: 3-3

### Lifecycle State Control

The `discovery_lifecycle_state` variable controls what lifecycle state is embedded in discovery artifacts. This state is later used by the `nb_register` role to tag devices in NetBox.

**Common Use Cases**:

| Scenario | Set Variable To | Behavior |
|----------|----------------|----------|
| **Initial Discovery** | `"discovered"` (default) | New devices tagged as `lifecycle:discovered` in NetBox |
| **Audit Discovery** | `""` (empty string) | Preserves existing lifecycle tags in NetBox (no changes) |
| **Post-Wipe Rediscovery** | `"discovered"` | Forces devices back to `lifecycle:discovered` tag |
| **Commission Workflow** | `"commissioned"` | Set by commission role after successful commissioning |

**Example - Audit Discovery Without State Changes**:
```yaml
- hosts: localhost
  vars:
    discovery_lifecycle_state: ""  # Don't modify lifecycle tags
  roles:
    - discovery
    - nb_register
```

**Example - Force Rediscovery After Repurpose**:
```yaml
- hosts: localhost
  vars:
    discovery_lifecycle_state: "discovered"
    nb_lifecycle_force_overwrite: true  # Override existing tags
  roles:
    - discovery
    - nb_register
```

## Usage Tips

### Running the Discovery

```bash
# Basic run with environment variables
export BMC_USERNAME="admin"
export BMC_PASSWORD="password"
ansible-playbook discovery.yml

# Using vault for credentials
ansible-playbook discovery.yml --ask-vault-pass

# With extra vars
ansible-playbook discovery.yml \
  -e "discovery_bmc_username=admin" \
  -e "discovery_bmc_password=secret" \
  -e '{"bmc_targets":[{"ip":"172.30.19.42"}]}'

# Verbose output for debugging
ansible-playbook discovery.yml -vv
```

### Post-Processing Artifacts

The generated YAML artifacts can be:

1. **Validated** using the included Python linter:
   ```bash
   python lint_yaml.py artifacts/
   ```

2. **Normalized** with the `--fix` flag:
   ```bash
   python lint_yaml.py --fix artifacts/
   ```

3. **Imported** into databases or CMDBs:
   ```python
   import yaml
   with open('172.30.19.42-discovery.yml') as f:
       inventory = yaml.safe_load(f)
   ```

4. **Versioned** in Git for historical tracking
5. **Aggregated** for fleet-wide reporting

### Best Practices

1. **Credentials Security**:
   - Never commit credentials to version control
   - Use Ansible Vault or external secret management
   - Rotate BMC passwords regularly

2. **Scheduling**:
   - Run discovery during maintenance windows for production systems
   - Consider scheduled runs (e.g., via cron/Jenkins) for automated updates

3. **Artifact Management**:
   - Store artifacts in centralized location (NFS, S3, Git LFS)
   - Implement retention policies
   - Tag artifacts with discovery timestamps

4. **Error Handling**:
   - Discovery continues even if individual BMCs fail
   - Failed BMC queries are reported at the end with error messages
   - Summary shows successful vs. failed discovery counts
   - Review Ansible output for failed BMC connections
   - Verify network connectivity and firewall rules
   - Check BMC firmware compatibility

5. **Performance**:
   - BMCs are queried sequentially for reliability
   - Use batching for very large BMC fleets (split into multiple runs)
   - Consider adjusting `forks` setting in ansible.cfg for parallel playbook execution

## Troubleshooting

### Common Issues

**Issue**: `Connection refused` or timeout errors

**Solution**:
- Verify BMC IP addresses are reachable: `ping <BMC_IP>`
- Check firewall rules allow HTTPS (TCP 443) to BMCs
- Confirm BMC network interface is configured and enabled

**Issue**: `Authentication failed`

**Solution**:
- Verify credentials are correct
- Check for password special characters requiring escaping
- Ensure BMC user account has Redfish API access permissions

**Issue**: Missing data in artifacts

**Solution**:
- Check Redfish API support on BMC (firmware version)
- Review BMC logs for API errors
- Some older hardware may have incomplete Redfish implementations

**Issue**: Template rendering errors

**Solution**:
- Ensure template file exists at `discovery_template_path`
- Verify Jinja2 syntax in custom templates
- Check for missing or malformed Redfish data structures

### Debug Mode

Enable detailed debug output by uncommenting debug tasks in `tasks/main.yml`:

```yaml
- name: Debug host interface per BMC
  ansible.builtin.debug:
    msg: "{{ item.redfish_facts.host_interfaces | to_nice_yaml }}"
  loop: "{{ redfish_hostif.results }}"
```

## Testing

### Manual Testing

```bash
# Test against single BMC
ansible-playbook discovery.yml -e '{"bmc_targets":[{"ip":"172.30.19.42"}]}' -vv

# Validate generated artifacts
python lint_yaml.py artifacts/172.30.19.42-discovery.yml

# Check artifact structure
yq eval . artifacts/172.30.19.42-discovery.yml
```

### Integration Testing

See `tests/` directory for example test playbook and inventory.

## Known Limitations

### HPE iLO Support

**Current Status**: HPE iLO BMCs are not yet fully supported by this role.

While HPE iLO 5 and iLO 6 implement the Redfish standard, they have differences in their API schema and response structures compared to Dell iDRAC implementations. The current template and data processing logic are optimized for Dell hardware.

**What This Means**:
- Discovery attempts against HPE iLO BMCs may fail or produce incomplete data
- Some inventory fields may be missing or incorrectly formatted
- Template rendering may encounter errors with iLO-specific data structures

**Planned Support**:
HPE iLO compatibility is planned for a future release. Implementation will include:
- iLO-specific API schema handling
- Conditional template logic for vendor-specific fields
- Comprehensive testing against iLO 5 and iLO 6 firmware versions
- Documentation for iLO-specific configuration requirements

**Workarounds**:
Until native support is added, iLO users can:
1. Manually query iLO Redfish APIs using the `community.general.redfish_info` module
2. Create custom templates tailored to iLO response structures
3. Use HPE-specific tools (iLOrest, OneView) for inventory collection

**Tracking**: If you need HPE iLO support, please open an issue in the project repository with your use case and iLO firmware version.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Test changes against multiple BMC types
4. Submit a pull request with clear description

**Priority Contributions**:
- HPE iLO support implementation
- Additional vendor BMC testing (Supermicro, Lenovo, etc.)
- Template enhancements for edge cases

## License

MIT

## Author Information

**Author**: Ean Wilson

For issues, questions, or contributions, please open an issue in the project repository.
