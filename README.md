# Bare-Metal Automation

Automated bare-metal server discovery and NetBox DCIM registration using Redfish BMC APIs with event-driven DHCP integration, DNS provisioning, and HashiCorp Vault credential management.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Configuration](#configuration)
- [Documentation](#documentation)
- [Development](#development)
- [Contributing](#contributing)
- [License](#license)

## Overview

This project provides comprehensive Ansible automation for bare-metal server lifecycle management with full event-driven workflow integration. The system automates hardware discovery, DNS provisioning, and asset registration in NetBox DCIM through a combination of Ansible roles, Python services, and event-driven orchestration.

**Core Components:**

- **discovery** - Queries BMCs via Redfish API and generates YAML artifacts
- **nb_register** - Processes artifacts and registers devices in NetBox DCIM
- **kea_deploy** - Deploys Kea DHCP with event-driven discovery, DNS integration, and Vault security

### Key Features

**Discovery & Registration:**
- Automated hardware inventory collection via Redfish
- NetBox integration with devices, interfaces, and inventory items
- Multi-dimensional tag system (lifecycle, automation, site-based)
- Idempotent operations safe for repeated execution
- Artifact-based workflow for review and reprocessing

**Event-Driven Automation:**
- Real-time DHCP lease monitoring with PostgreSQL NOTIFY/LISTEN
- Immediate DNS record creation on reservation changes
- Cabinet-aware batching for efficient Spacelift triggering
- Database-backed static DHCP reservations (PostgreSQL)
- Transactional DNS operations (atomic reservation + DNS creation)

**Security & Credential Management:**
- HashiCorp Vault integration for secure credential storage
- No hardcoded passwords in code or configuration
- Runtime credential retrieval from Vault
- Self-signed certificate support (VAULT_SKIP_VERIFY)

**Infrastructure Standards:**
- Strict hostname naming conventions for automation compatibility
- Cabinet and rack unit tracking via naming pattern
- Site-aware resource grouping and management
- Dynamic site tag generation from BMC naming conventions

## Quick Start

### Prerequisites

```bash
# Install Ansible and collections
pip install ansible
ansible-galaxy collection install -r ansible/collections/requirements.yml

# Optional: Python utilities for linting and validation
pip install ansible-lint pyyaml
```

### Configuration

1. Configure credentials:
```bash
cp .env.example .env
# Edit .env with your BMC and NetBox credentials
```

2. Define BMC targets in `ansible/inventory/localhost.yml`

3. Review role defaults in:
   - `ansible/roles/discovery/defaults/main.yml`
   - `ansible/roles/nb_register/defaults/main.yml`

### Usage

**Full lifecycle (discovery + registration):**
```bash
cd ansible
ansible-playbook playbooks/lifecycle.yml
```

**Discovery only:**
```bash
ansible-playbook playbooks/discovery.yml
```

**Registration only:**
```bash
ansible-playbook playbooks/register.yml
```

## Architecture

### Workflow

**Manual Discovery (Triggered):**
```
BMC Redfish APIs → discovery role → YAML artifacts → nb_register role → NetBox DCIM
```

**Event-Driven Automation (Real-Time):**
```
BMC Powers On → DHCP Lease → PostgreSQL INSERT → NOTIFY Event → DNS Record Created
                                                             ↓
                                                    Spacelift Stack Triggered
                                                             ↓
                                        Approval Gate → Ansible Execution (discovery + nb_register)
                                                             ↓
                                                        NetBox Updated
```

**Combined Workflow:**
1. BMC receives DHCP lease and sends hostname via DHCP Option 12
2. Kea creates static reservation in PostgreSQL
3. PostgreSQL trigger fires NOTIFY event
4. kea_lease_monitor receives event and creates DNS record via SOLIDserver
5. BMC accumulator batches per cabinet (5-minute window)
6. Spacelift stack triggered with BMC IP list for cabinet
7. Manual approval gate (production) or auto-approve (dev)
8. Ansible playbook executes in Spacelift runner container
9. Discovery role queries BMCs and generates artifacts
10. NetBox registration role creates/updates DCIM resources

### Roles

**discovery**
- Queries BMCs via Redfish API
- Extracts hardware inventory (system info, storage, network, processors)
- Generates structured YAML artifacts
- Parses FQDN from BMC host interfaces
- Extracts cabinet and rack unit from BMC naming convention
- Idempotent: Safe to rerun without side effects
- Stateful: Artifacts persist for reprocessing
- See [ansible/roles/discovery/README.md](ansible/roles/discovery/README.md) for details

**Spacelift Integration (In Development)**
- Custom Ansible runner image for execution in Spacelift
- Event-driven stack triggering from DHCP/DNS workflow
- Approval gates for production deployments
- See [spacelift/runner/README.md](spacelift/runner/README.md) for runner image
- Stateful: Artifacts persist for reprocessing

**nb_register**
- Loads discovery artifacts
- Creates/updates NetBox resources (sites, manufacturers, device types, devices)
- Applies lifecycle, automation, and site tags
- Enforces lifecycle tag mutual exclusivity
- Stateless: Safe to rerun without side effects

**kea_deploy**
- Deploys Kea DHCP server (Ubuntu 24.04 LTS)
- Configures PostgreSQL database backend for static reservations
- Deploys unified lease monitor service (discovery + reservations + DNS)
- Event-driven: Immediate processing on lease detection
- Transactional: Atomic database + DNS operations
- See [ansible/roles/kea_deploy/README.md](ansible/roles/kea_deploy/README.md) for details

### Tag System

**Lifecycle Tags** (mutually exclusive - only one per device):
- `discovered` - Initial discovery state
- `commissioned` - Validated and ready for deployment
- `deployed` - In production use
- `repurpose-ready` - Marked for decommissioning/reuse

**Automation Tags:**
- `automation-managed` - Device under automation control

**Site Tags** (dynamically generated):
- `site-us1`, `site-us2`, `site-us3`, `site-us4`, `site-dv`
- Extracted from BMC name prefix (e.g., `US1-cab01-svr01-bmc` → `site-us1`)

See [docs/LIFECYCLE_TAG_BEHAVIOR.md](docs/LIFECYCLE_TAG_BEHAVIOR.md) for detailed tag behavior.

## Repository Structure

```
baremetal-automation/
├── ansible/                        # Ansible automation root
│   ├── playbooks/
│   │   ├── discovery.yml           # BMC discovery playbook
│   │   ├── register.yml            # NetBox registration playbook
│   │   ├── lifecycle.yml           # Combined discovery + registration
│   │   ├── kea_deploy.yml          # Kea DHCP deployment with Vault/DNS
│   │   └── kea_remove.yml          # Kea DHCP removal/cleanup
│   ├── inventory/
│   │   ├── localhost.yml           # Local execution inventory
│   │   └── lab-kea-inv.yml         # Lab environment inventory
│   ├── artifacts/                  # Generated discovery artifacts (gitignored)
│   │   └── .gitkeep
│   ├── roles/
│   │   ├── discovery/              # BMC discovery role
│   │   │   ├── tasks/
│   │   │   │   ├── main.yml        # Entry point: validation, query, render
│   │   │   │   ├── query.yml       # Redfish API queries
│   │   │   │   └── render.yml      # Artifact generation from template
│   │   │   ├── templates/
│   │   │   │   └── discovery_artifact.yml.j2  # YAML artifact template
│   │   │   ├── defaults/
│   │   │   │   └── main.yml        # Default variables
│   │   │   └── README.md           # Role documentation
│   │   ├── nb_register/            # NetBox registration role
│   │   │   ├── tasks/
│   │   │   │   ├── main.yml        # Entry point: validation, artifact processing
│   │   │   │   ├── setup.yml       # NetBox connectivity validation
│   │   │   │   └── process_artifact.yml  # Per-artifact registration logic
│   │   │   ├── defaults/
│   │   │   │   └── main.yml        # Default variables
│   │   │   └── README.md           # Role documentation
│   │   └── kea_deploy/             # Kea DHCP with event-driven workflow
│   │       ├── tasks/
│   │       │   ├── main.yml        # Entry point: orchestrates deployment
│   │       │   ├── install.yml     # Kea package installation
│   │       │   ├── config.yml      # DHCP configuration generation
│   │       │   ├── database.yml    # PostgreSQL setup for reservations
│   │       │   ├── python.yml      # Python environment for lease monitor
│   │       │   ├── hooks.yml       # PostgreSQL trigger deployment
│   │       │   ├── services.yml    # Systemd service management
│   │       │   └── summary.yml     # Deployment summary display
│   │       ├── templates/
│   │       │   ├── kea-dhcp4.conf.j2          # Kea DHCP4 configuration
│   │       │   ├── kea_notify_trigger.sql.j2  # PostgreSQL NOTIFY trigger
│   │       │   └── kea-lease-monitor.service.j2  # Systemd service
│   │       ├── defaults/
│   │       │   └── main.yml        # Default variables
│   │       └── README.md           # Role documentation
│   ├── collections/
│   │   └── requirements.yml        # Ansible collection dependencies
│   └── ansible.cfg                 # Ansible configuration
├── docs/                           # Documentation
│   ├── DESIGN.md                   # Architecture and design decisions
│   ├── TESTING.md                  # Testing procedures and validation
│   ├── INFRASTRUCTURE_STANDARDS.md # Hostname naming conventions
│   ├── LIFECYCLE_TAG_BEHAVIOR.md   # Tag management rules
│   ├── NETBOX_SETUP.md             # NetBox configuration requirements
│   ├── KEA_DNS_INTEGRATION.md      # DNS integration architecture
│   ├── KEA_DNS_DEPLOYMENT.md       # Deployment summary and results
│   ├── KEA_DNS_DEPLOYMENT_CHECKLIST.md  # Step-by-step deployment guide
│   ├── KEA_DNS_QUICKSTART.md       # Quick reference guide
│   └── FILL_THESE_IN.md            # Configuration values to update
├── python/                         # Python utilities and services
│   ├── src/baremetal/
│   │   ├── kea_lease_monitor.py    # Unified DHCP/DNS/Vault service
│   │   ├── kea_lease_hook.py       # Kea DHCP hook (single lease)
│   │   ├── vault_credentials.py    # Vault credential retrieval
│   │   ├── solidserver_connection.py  # SOLIDserver DNS client
│   │   ├── solidserver_dns.py      # DNS record management wrapper
│   │   ├── dns-add.py              # Manual DNS record creation
│   │   ├── bmc_dns_watcher.py      # DNS monitoring service
│   │   ├── fix_ansible_lint.py     # Ansible linting automation
│   │   ├── lint_yaml.py            # YAML validation utility
│   │   └── custom_logging.py       # Logging utilities
│   ├── tests/                      # Unit tests
│   │   ├── fixtures/               # Test data
│   │   └── output/                 # Test output (gitignored)
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Environment variable template
│   └── README.md                   # Python utilities documentation
├── spacelift/                      # Spacelift integration
│   └── runner/
│       ├── Dockerfile              # Alpine-based Ansible runner
│       ├── requirements.txt        # Python packages
│       ├── requirements.yml        # Ansible collections
│       └── README.md               # Build and usage instructions
├── kea_dhcp/                       # Kea DHCP configuration examples
│   └── kea-dhcp4.conf              # Sample DHCP4 configuration
├── .redfish/                       # Redfish mockup data for testing
├── .github/
│   └── copilot-instructions.md     # Development standards and conventions
├── .gitignore                      # Git ignore patterns
├── .env.example                    # Environment variable template
├── FILL_THESE_IN.md                # Configuration guide for deployment
└── README.md                       # This file
```

### Key Directories

**`ansible/`** - All Ansible automation code including playbooks, roles, and inventories. Artifacts are generated here but gitignored for security.

**`python/`** - Python services and utilities for DHCP monitoring, DNS integration, Vault credential retrieval, and development tooling.

**`docs/`** - Comprehensive documentation covering architecture, testing, deployment procedures, and infrastructure standards.

**`spacelift/`** - Container-based execution environment for infrastructure-as-code workflows with approval gates.

**`.redfish/`** - DMTF DSP2043 mockup data for Redfish API testing without requiring live BMC hardware.
```

## Configuration

### Discovery Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `discovery_bmc_username` | `{{ lookup('env', 'BMC_USERNAME') }}` | BMC authentication username |
| `discovery_bmc_password` | `{{ lookup('env', 'BMC_PASSWORD') }}` | BMC authentication password |
| `discovery_artifact_dir` | `../playbooks/artifacts` | Output directory for artifacts |
| `discovery_template_path` | `discovery_artifact.yml.j2` | Jinja2 template for artifacts |
**Core Documentation:**
- **[DESIGN.md](docs/DESIGN.md)** - Architecture decisions and rationale
- **[TESTING.md](docs/TESTING.md)** - Testing procedures and validation
- **[INFRASTRUCTURE_STANDARDS.md](docs/INFRASTRUCTURE_STANDARDS.md)** - Hostname naming conventions and automation requirements
- **[LIFECYCLE_TAG_BEHAVIOR.md](docs/LIFECYCLE_TAG_BEHAVIOR.md)** - Tag management rules
- **[NETBOX_SETUP.md](docs/NETBOX_SETUP.md)** - NetBox prerequisites

**DNS Integration (Event-Driven Workflow):**
- **[KEA_DNS_INTEGRATION.md](docs/KEA_DNS_INTEGRATION.md)** - Technical architecture and implementation details
- **[KEA_DNS_DEPLOYMENT.md](docs/KEA_DNS_DEPLOYMENT.md)** - Deployment summary and test results
- **[KEA_DNS_DEPLOYMENT_CHECKLIST.md](docs/KEA_DNS_DEPLOYMENT_CHECKLIST.md)** - Step-by-step deployment guide
- **[KEA_DNS_QUICKSTART.md](docs/KEA_DNS_QUICKSTART.md)** - Quick reference guide

**Role Documentation:**
- **[discovery/README.md](ansible/roles/discovery/README.md)** - BMC discovery role
- **[nb_register/README.md](ansible/roles/nb_register/README.md)** - NetBox registration role
- **[kea_deploy/README.md](ansible/roles/kea_deploy/README.md)** - Kea DHCP with Vault/DNS integration

**Utilities:**
- **[python/README.md](python/README.md)** - Python utility documentation
- **[spacelift/runner/README.md](spacelift/runner/README.md)** - Spacelift runner image

### NetBox Registration Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `nb_url` | `{{ lookup('env', 'NETBOX_URL') }}` | NetBox instance URL |
| `nb_token` | `{{ lookup('env', 'NETBOX_TOKEN') }}` | NetBox API token |
| `nb_validate_certs` | `true` | Validate SSL certificates |
| `nb_auto_create_refs` | `false` | Auto-create missing objects |
| `nb_default_site` | `""` | Default site for devices |
| `nb_default_device_role` | `"Server"` | Default device role |
| `nb_apply_tags` | `['lifecycle', 'automation', 'site']` | Tag categories to apply |
| `nb_lifecycle_force_overwrite` | `false` | Force lifecycle tag replacement |
| `nb_create_bmc_interface` | `true` | Create BMC management interface |
| `nb_create_bmc_custom_link` | `true` | Add BMC hyperlink to devices |

See role README files for complete variable documentation.

## Services & Utilities

**Core Services (python/src/baremetal/):**
- **kea_lease_monitor.py** - Unified event-driven service for DHCP/DNS/Vault integration
  - Real-time processing via PostgreSQL NOTIFY/LISTEN
  - Automatic DNS record creation via SOLIDserver API
  - HashiCorp Vault credential retrieval
  - Cabinet-aware batching for Spacelift triggering (future)
- **vault_credentials.py** - HashiCorp Vault credential retrieval module
- **solidserver_connection.py** - SOLIDserver DNS API client module

**Development Utilities (python/):**
- **fix_ansible_lint.py** - Automatically fixes ansible-lint issues (used in CI/CD pipeline)
- **lint_yaml.py** - Validates and formats YAML artifacts (ensures `discovery_artifact.yml.j2` template outputs standard YAML)

```bash
# Validate Ansible roles
python python/fix_ansible_lint.py ansible/roles

# Validate discovery artifacts
python python/lint_yaml.py ansible/playbooks/artifacts/

# Install Python dependencies
pip install -r python/requirements.txt
```

## Development

### Development Standards

All code contributions must follow the conventions documented in [.github/copilot-instructions.md](.github/copilot-instructions.md):

**Ansible Standards:**
- **Idempotency** - All tasks must be safe for repeated execution
- **Task Naming** - Use standard action verbs (Validate, Ensure, Create, Extract, Build, Query, Display)
- **Loop Control** - Always use `loop_var` and `label` for clarity
- **Error Handling** - Validate early, fail fast with clear messages
- **Security** - Use `no_log: true` for credentials, environment variables for secrets
- **Variable Naming** - Use role-specific prefixes (`discovery_*`, `nb_*`, `bmc_*`)

**Python Standards:**
- Use ASCII-only characters for output messages (no Unicode symbols)
- Support multiple input paths with `nargs="+"`
- Provide `--dry-run` and `--verify` options
- Include comprehensive docstrings
- Use type hints for function signatures

**Git Workflow:**
- Branch naming: `<type>/<scope>-<short-description>` (e.g., `feat/discovery-add-storage`)
- Commit messages: `<type>(<scope>): <description>` (e.g., `fix(nb-register): prevent duplicate interfaces`)
- Follow Gitflow model with master as primary branch
- Delete branches after merging

### Testing and Validation

```bash
# Syntax validation
ansible-playbook ansible/playbooks/discovery.yml --syntax-check

# Ansible linting
ansible-lint ansible/roles/

# Automated lint fixing (CI/CD)
python python/src/baremetal/fix_ansible_lint.py ansible/roles

# YAML artifact validation
python python/src/baremetal/lint_yaml.py ansible/artifacts/

# Idempotency testing (run twice, verify no changes)
ansible-playbook ansible/playbooks/register.yml
ansible-playbook ansible/playbooks/register.yml  # Should show no changes
```

### Redfish API Exploration

The [.redfish/](.redfish/) directory contains DMTF DSP2043 mockup data for Redfish API exploration and testing without requiring live BMC hardware. This allows for:

- API response format verification
- Template development and testing
- JSON parsing validation
- Offline development and testing

## Contributing

Contributions are welcome! Please adhere to the following:

1. **Code Quality**
   - Follow Ansible best practices (idempotency, proper task naming)
   - Use descriptive loop variables and labels
   - Validate inputs with `ansible.builtin.assert`
   - Never hardcode credentials (use environment variables or Vault)

2. **Documentation**
   - Update role README files for new features
   - Add examples for new functionality
   - Document all role variables with defaults and descriptions
   - Update architecture diagrams if workflow changes

3. **Testing**
   - Test with `ansible-playbook --syntax-check`
   - Run `ansible-lint` and fix all issues
   - Verify idempotency (run twice, check for changes)
   - Test with different variable combinations

4. **Security**
   - Never commit credentials or secrets
   - Use `no_log: true` for sensitive tasks
   - Validate all external inputs
   - Follow principle of least privilege

## License

[Specify license]

## Support

For issues, questions, or contributions:

- **Documentation**: Refer to comprehensive guides in [docs/](docs/)
- **Role Details**: Review role-specific README files:
  - [discovery/README.md](ansible/roles/discovery/README.md)
  - [nb_register/README.md](ansible/roles/nb_register/README.md)
  - [kea_deploy/README.md](ansible/roles/kea_deploy/README.md)
- **Configuration**: See [FILL_THESE_IN.md](FILL_THESE_IN.md) for deployment setup guide
- **Standards**: Review [.github/copilot-instructions.md](.github/copilot-instructions.md) for development conventions
