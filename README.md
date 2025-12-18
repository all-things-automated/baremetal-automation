# Bare-Metal Automation

Automated bare-metal server discovery and NetBox DCIM registration using Redfish BMC APIs.

## Overview

This project provides Ansible automation for bare-metal server lifecycle management:

- **discovery** role - Queries BMCs via Redfish API and generates YAML artifacts
- **nb_register** role - Processes artifacts and registers devices in NetBox DCIM
- **kea_deploy** role - Deploys Kea DHCP with event-driven discovery and DNS integration

### Key Features

- Automated hardware inventory collection via Redfish
- NetBox integration with devices, interfaces, and inventory items
- Multi-dimensional tag system (lifecycle, automation, site-based)
- Event-driven DHCP lease monitoring with automated discovery
- Database-backed static DHCP reservations (PostgreSQL)
- Transactional DNS record creation (integrated with reservations)
- Idempotent operations safe for repeated execution
- Artifact-based workflow for review and reprocessing
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

**Discovery-Driven (Triggered):**
```
BMC Redfish APIs → discovery role → YAML artifacts → nb_register role → NetBox DCIM
```

**Event-Driven (Automated):**
```
DHCP Lease → Lease Monitor → Discovery YAML + DB Reservation + DNS Record
```

**Combined:** Kea DHCP automates initial discovery, manual Ansible discovery collects detailed hardware inventory

### Roles

**discovery**
- Queries BMC Redfish endpoints
- Collects system information, network interfaces, processors, memory, storage
- Generates YAML artifacts in `ansible/playbooks/artifacts/`
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

## Project Structure

```
.
├── ansible/
│   ├── playbooks/
│   │   ├── discovery.yml       # Discovery-only playbook
│   │   ├── register.yml        # Registration-only playbook
│   │   ├── lifecycle.yml       # Full discovery + registration
│   │   └── artifacts/          # Generated discovery artifacts
│   ├── roles/
│   │   ├── discovery/          # BMC discovery role
│   │   └── nb_register/        # NetBox registration role
│   ├── templates/
│   │   └── discovery_artifact.yml.j2
│   └── ansible.cfg
├── docs/
│   ├── DESIGN.md               # Architecture and design decisions
│   ├── TESTING.md              # Testing procedures
│   ├── LIFECYCLE_TAG_BEHAVIOR.md
│   ├── NETBOX_SETUP.md         # NetBox configuration requirements
│   └── SETUP.md                # Detailed setup guide
├── python/
│   ├── fix_ansible_lint.py     # Ansible linting automation (CI/CD)
│   ├── lint_yaml.py            # YAML validation utility
│   └── README.md
├── .redfish/                   # Redfish mockup data for testing
├── .github/
│   └── copilot-instructions.md # Development standards
├── .env.example
└── .gitignore
```

## Configuration

### Discovery Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `discovery_bmc_username` | `{{ lookup('env', 'BMC_USERNAME') }}` | BMC authentication username |
| `discovery_bmc_password` | `{{ lookup('env', 'BMC_PASSWORD') }}` | BMC authentication password |
| `discovery_artifact_dir` | `../playbooks/artifacts` | Output directory for artifacts |
| `discovery_template_path` | `discovery_artifact.yml.j2` | Jinja2 template for artifacts |

### NetBox Registration Role Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `nb_url` | `{{ lookup('env', 'NETBOX_URL') }}` | NetBox instance URL |
| `nb_token` | `{{ lookup('env', 'NETBOX_TOKEN') }}` | NetBox API token |
| `nb_auto_create_refs` | `true` | Auto-create sites, manufacturers, device types |
| `nb_apply_tags` | `['lifecycle', 'automation', 'site']` | Tag categories to apply |
| `nb_lifecycle_force_overwrite` | `false` | Force lifecycle tag replacement |
| `nb_create_bmc_interface` | `true` | Create BMC management interface |
| `nb_create_bmc_custom_link` | `true` | Add BMC hyperlink to devices |

See role `defaults/main.yml` files for complete variable documentation.

## Documentation

- **[SETUP.md](docs/SETUP.md)** - Detailed installation and configuration
- **[DESIGN.md](docs/DESIGN.md)** - Architecture decisions and rationale
- **[TESTING.md](docs/TESTING.md)** - Testing procedures and validation
- **[KEA_WORKFLOW.md](docs/KEA_WORKFLOW.md)** - Event-driven DHCP workflow and database integration
- **[LIFECYCLE_TAG_BEHAVIOR.md](docs/LIFECYCLE_TAG_BEHAVIOR.md)** - Tag management rules
- **[NETBOX_SETUP.md](docs/NETBOX_SETUP.md)** - NetBox prerequisites
- **[python/README.md](python/README.md)** - Python utility documentation
- **[kea_deploy/README.md](ansible/roles/kea_deploy/README.md)** - Kea DHCP role documentation

## Python Utilities

Located in `python/`:

- **fix_ansible_lint.py** - Automatically fixes ansible-lint issues (used in CI/CD pipeline)
- **lint_yaml.py** - Validates and formats YAML artifacts (ensures `discovery_artifact.yml.j2` template outputs standard YAML)

```bash
# Validate Ansible roles
python python/fix_ansible_lint.py ansible/roles

# Validate discovery artifacts
python python/lint_yaml.py ansible/playbooks/artifacts/
```

## Development Standards

Follow conventions documented in `.github/copilot-instructions.md`:

- **Idempotency** - All tasks safe for repeated execution
- **Task Naming** - Use standard action verbs (Validate, Ensure, Create, Extract, Build, Query, Display)
- **Loop Control** - Always use `loop_var` and `label`
- **Error Handling** - Validate early, fail fast with clear messages
- **Security** - Use `no_log: true` for credentials, environment variables for secrets
- **Variable Naming** - Use role-specific prefixes (`discovery_*`, `nb_*`, `bmc_*`)

## Redfish Exploration

The `.redfish/` directory contains DMTF DSP2043 mockup data for Redfish API exploration and testing without live BMCs.

## Contributing

Contributions should adhere to project standards:

1. Follow Ansible best practices (idempotency, proper task naming)
2. Use descriptive loop variables and labels
3. Validate inputs with `ansible.builtin.assert`
4. Avoid hardcoded credentials (use environment variables)
5. Update documentation for new features
6. Test with `ansible-playbook --syntax-check` and `ansible-lint`

## License

[Specify license]

## Support

For issues or questions, refer to documentation in `docs/` or review role README files:
- `ansible/roles/discovery/README.md`
- `ansible/roles/nb_register/README.md`
