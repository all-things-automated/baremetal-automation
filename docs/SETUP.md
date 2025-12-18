# Bare-Metal Automation - Execution Environment Setup

This guide provides instructions for setting up an Ansible Execution Environment (EE) for the bare-metal discovery and NetBox registration automation. An Execution Environment is a containerized Ansible control node that includes all dependencies, ensuring consistent and reproducible automation across environments.

## Table of Contents

- [What is an Execution Environment?](#what-is-an-execution-environment)
- [System Requirements](#system-requirements)
- [Installing Prerequisites](#installing-prerequisites)
- [Building the Execution Environment](#building-the-execution-environment)
- [Running Playbooks with the EE](#running-playbooks-with-the-ee)
- [Environment Variables](#environment-variables)
- [NetBox Configuration](#netbox-configuration)
- [Verification](#verification)
- [Troubleshooting](#troubleshooting)

## What is an Execution Environment?

An Ansible Execution Environment (EE) is a container image that serves as an Ansible control node. It packages:

- **ansible-core** and **ansible-runner**
- **Python** runtime and dependencies
- **Ansible Collections** (community.general, netbox.netbox)
- **Python packages** (pynetbox, requests, pyyaml)
- **Custom content** specific to this project

**Benefits:**
- Consistent environment across all users
- No local Python dependency conflicts
- Portable and shareable
- Simplified onboarding for new team members
- Works on any system with Podman/Docker

## System Requirements

### Operating System

- **RHEL/CentOS/Rocky/AlmaLinux**: 8 or later
- **Fedora**: 36 or later
- **Ubuntu**: 20.04 LTS or later
- **Debian**: 11 or later

### Prerequisites

- **Container Runtime**: Podman (recommended) or Docker
- **Python**: 3.8 or later
- **pip**: Python package installer
- **Network Access**: 
  - Access to container registries (quay.io, ghcr.io)
  - Connectivity to target BMC IP addresses
  - Connectivity to NetBox API endpoint

## Installing Prerequisites

### RHEL/CentOS/Rocky/AlmaLinux/Fedora

```bash
# Install Podman, Python, and pip
sudo dnf install -y podman python3 python3-pip

# Verify installations
podman --version
python3 --version
pip3 --version
```

### Ubuntu/Debian

```bash
# Update package index
sudo apt update

# Install Podman, Python, and pip
sudo apt install -y podman python3 python3-pip

# Verify installations
podman --version
python3 --version
pip3 --version
```

### Install Ansible Builder and Navigator

```bash
# Install ansible-navigator (includes ansible-builder)
pip3 install --user ansible-navigator

# Add to PATH if needed
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify installations
ansible-navigator --version
ansible-builder --version
```

**Expected output:**
```
ansible-navigator 3.x.x
ansible-builder 3.x.x
```

## Building the Execution Environment

### Create Execution Environment Definition

Create `execution-environment.yml` in the project root:

```yaml
---
version: 3

build_arg_defaults:
  ANSIBLE_GALAXY_CLI_COLLECTION_OPTS: '--pre'

images:
  base_image:
    name: quay.io/ansible/creator-base:latest

dependencies:
  galaxy: requirements.yml
  python: requirements.txt
  system: bindep.txt

additional_build_steps:
  append_final:
    - RUN pip3 install --upgrade pip setuptools
```

### Create Requirements Files

**Create `requirements.yml`** (Ansible Collections):

```yaml
---
collections:
  - name: community.general
    version: ">=8.0.0"
  - name: netbox.netbox
    version: ">=3.0.0"
```

**Create `requirements.txt`** (Python packages):

```txt
ansible-core>=2.17.14
pynetbox>=7.0.0
requests>=2.31.0
pyyaml>=6.0
```

**Create `bindep.txt`** (System packages):

```txt
python38-devel [platform:centos-8 platform:rhel-8]
python3-devel [platform:fedora platform:centos-9 platform:rhel-9]
git [platform:rpm]
```

### Build the Container Image

```bash
# Navigate to project directory
cd /path/to/baremetal

# Build the execution environment
ansible-builder build --tag baremetal-ee:latest --container-runtime podman

# Build process will take 5-10 minutes
```

**Build output should end with:**
```
Complete! The build context can be found at: context
The ansible-builder build context has been generated
The build context has been copied to the build directory
Building image baremetal-ee:latest using podman...
Successfully tagged localhost/baremetal-ee:latest
```

### Verify the Image

```bash
# List container images
podman images

# Should show:
# REPOSITORY                TAG      IMAGE ID      CREATED        SIZE
# localhost/baremetal-ee    latest   abc123def456  2 minutes ago  1.2GB

# Inspect the image
podman inspect baremetal-ee:latest

# Test the image
ansible-navigator exec --execution-environment-image baremetal-ee:latest -- ansible --version
```

## Running Playbooks with the EE

### Using ansible-navigator (Recommended)

**Run discovery playbook:**

```bash
cd ansible

ansible-navigator run playbooks/discovery.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --pull-policy missing \
  --eev BMC_USERNAME \
  --eev BMC_PASSWORD
```

**Run NetBox registration playbook:**

```bash
ansible-navigator run playbooks/register.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --pull-policy missing \
  --eev NETBOX_URL \
  --eev NETBOX_TOKEN
```

**ansible-navigator flags explained:**
- `--execution-environment-image`: Specifies the EE container image to use
- `--mode stdout`: Display output directly (use `--mode interactive` for TUI)
- `--pull-policy missing`: Only pull image if not present locally
- `--eev <VAR>`: Pass environment variable into the container

### Using Podman/Docker Directly

You can also run the EE directly with Podman:

```bash
podman run --rm -it \
  -v $(pwd):/runner:Z \
  -e BMC_USERNAME="${BMC_USERNAME}" \
  -e BMC_PASSWORD="${BMC_PASSWORD}" \
  -e NETBOX_URL="${NETBOX_URL}" \
  -e NETBOX_TOKEN="${NETBOX_TOKEN}" \
  baremetal-ee:latest \
  ansible-playbook /runner/ansible/playbooks/discovery.yml
```

**Flags explained:**
- `--rm`: Remove container after execution
- `-it`: Interactive terminal
- `-v $(pwd):/runner:Z`: Mount current directory (`:Z` for SELinux)
- `-e VAR="value"`: Pass environment variables
- `baremetal-ee:latest`: The EE image to run
- `ansible-playbook ...`: Command to execute inside container

### Create Convenience Scripts

**Create `run-discovery.sh`:**

```bash
#!/bin/bash
set -e

ansible-navigator run ansible/playbooks/discovery.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --pull-policy missing \
  --eev BMC_USERNAME \
  --eev BMC_PASSWORD \
  "$@"
```

**Create `run-register.sh`:**

```bash
#!/bin/bash
set -e

ansible-navigator run ansible/playbooks/register.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --pull-policy missing \
  --eev NETBOX_URL \
  --eev NETBOX_TOKEN \
  "$@"
```

**Make scripts executable:**

```bash
chmod +x run-discovery.sh run-register.sh
```

**Usage:**

```bash
# Run discovery
./run-discovery.sh

# Run registration with verbosity
./run-register.sh -vv
```

## Environment Variables

### BMC Credentials

Set BMC authentication credentials:

```bash
# Add to ~/.bashrc or ~/.bash_profile for persistence
export BMC_USERNAME="admin"
export BMC_PASSWORD="your-secure-bmc-password"
```

Apply changes:
```bash
source ~/.bashrc
```

### NetBox Credentials

Set NetBox API credentials:

```bash
# Add to ~/.bashrc or ~/.bash_profile for persistence
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-netbox-api-token-here"
```

Apply changes:
```bash
source ~/.bashrc
```

### Verify Environment Variables

```bash
echo $BMC_USERNAME
echo $NETBOX_URL
# Outputs should show your configured values
```

### Security Note

**Never commit credentials to version control!**

For production environments, consider:
- **Ansible Vault**: Encrypt credentials in repository
- **Secret Management**: HashiCorp Vault, CyberArk
- **CI/CD Secrets**: GitLab CI/CD Variables, Jenkins Credentials

## NetBox Configuration

### Create NetBox API Token

1. Log into NetBox web interface
2. Navigate to: **User Menu** > **Profile** > **API Tokens**
3. Click **Add a token**
4. Set permissions:
   - `dcim.*` (Full DCIM access)
   - `ipam.*` (Full IPAM access)
   - `extras.*` (For custom links and fields)
5. Copy the generated token and set as `NETBOX_TOKEN` environment variable

### Create NetBox Custom Fields (Optional)

For tracking discovery metadata:

**Custom Field 1: discover_artifact**
- Navigate to: **Customization** > **Custom Fields** > **Add**
- Settings:
  - **Name**: `discover_artifact`
  - **Type**: Text
  - **Content Type**: `dcim > device`
  - **Description**: Discovery artifact filename

**Custom Field 2: lifecycle_state**
- Navigate to: **Customization** > **Custom Fields** > **Add**
- Settings:
  - **Name**: `lifecycle_state`
  - **Type**: Selection
  - **Choices**: `discovered`, `commissioned`, `deployed`
  - **Content Type**: `dcim > device`
  - **Description**: Device lifecycle state

### Pre-create NetBox Objects (if not using auto-create)

If `nb_auto_create_refs: false`, manually create:

1. **Sites**: **Organization** > **Sites** > **Add** (e.g., `US3`)
2. **Device Roles**: **Devices** > **Device Roles** > **Add** (e.g., `Lab Server`)
3. **Manufacturers**: **Devices** > **Manufacturers** > **Add** (e.g., `Dell Inc.`)
4. **Device Types**: **Devices** > **Device Types** > **Add** (e.g., `PowerEdge R660`)

## Verification

### Test Execution Environment

```bash
# Test ansible-navigator
ansible-navigator --version

# Test EE image exists
podman images | grep baremetal-ee

# Test running ansible inside EE
ansible-navigator exec \
  --execution-environment-image baremetal-ee:latest \
  -- ansible --version
```

### Test Ansible Collections in EE

```bash
# Verify community.general collection
ansible-navigator doc community.general.redfish_info \
  --execution-environment-image baremetal-ee:latest

# Verify netbox.netbox collection
ansible-navigator doc netbox.netbox.netbox_device \
  --execution-environment-image baremetal-ee:latest
```

### Test BMC Connectivity

```bash
# Test Redfish API access (outside container)
curl -k -u $BMC_USERNAME:$BMC_PASSWORD https://172.30.19.42/redfish/v1/
```

Should return JSON response from BMC.

### Test NetBox API Connectivity

```bash
# Test NetBox API (outside container)
curl -H "Authorization: Token $NETBOX_TOKEN" $NETBOX_URL/api/
```

Should return JSON response from NetBox API.

## Troubleshooting

### Podman Not Found

```bash
# Verify installation
which podman

# Reinstall if needed
sudo dnf install -y podman  # RHEL/Fedora
sudo apt install -y podman   # Ubuntu/Debian
```

### ansible-navigator Not in PATH

```bash
# Add to PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# Verify
ansible-navigator --version
```

### Build Fails with Permission Errors

```bash
# Ensure proper permissions
chmod -R 755 ansible/

# Run build with sudo if needed (not recommended)
sudo ansible-builder build --tag baremetal-ee:latest
```

### Container Cannot Access Network

```bash
# Check Podman network
podman network ls

# Recreate default network
podman network rm podman
podman network create podman
```

### Environment Variables Not Passed

Ensure you use `--eev` flag with ansible-navigator:

```bash
ansible-navigator run playbooks/discovery.yml \
  --execution-environment-image baremetal-ee:latest \
  --eev BMC_USERNAME \
  --eev BMC_PASSWORD
```

Or pass explicitly with Podman:

```bash
podman run --rm -it \
  -e BMC_USERNAME="${BMC_USERNAME}" \
  -e BMC_PASSWORD="${BMC_PASSWORD}" \
  baremetal-ee:latest ...
```

### SELinux Denials (RHEL/Fedora)

If volume mounts fail:

```bash
# Add :Z flag to volume mount
-v $(pwd):/runner:Z

# Or temporarily set SELinux to permissive
sudo setenforce 0
```

### Image Build is Slow

First build takes 5-10 minutes. Subsequent builds use cache.

```bash
# Force clean rebuild
ansible-builder build --tag baremetal-ee:latest --no-cache
```

## Quick Start

### Complete Setup from Scratch

```bash
# 1. Install prerequisites
sudo dnf install -y podman python3 python3-pip
pip3 install --user ansible-navigator

# 2. Clone repository
git clone https://github.com/your-org/baremetal.git
cd baremetal

# 3. Create requirements files (use examples above)
# - execution-environment.yml
# - requirements.yml
# - requirements.txt
# - bindep.txt

# 4. Build execution environment
ansible-builder build --tag baremetal-ee:latest --container-runtime podman

# 5. Set environment variables
export BMC_USERNAME="admin"
export BMC_PASSWORD="your-password"
export NETBOX_URL="https://netbox.example.com"
export NETBOX_TOKEN="your-token"

# 6. Configure BMC targets
vi ansible/playbooks/discovery.yml
# Update bmc_targets list

# 7. Run discovery
ansible-navigator run ansible/playbooks/discovery.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --eev BMC_USERNAME \
  --eev BMC_PASSWORD

# 8. Run registration
ansible-navigator run ansible/playbooks/register.yml \
  --execution-environment-image baremetal-ee:latest \
  --mode stdout \
  --eev NETBOX_URL \
  --eev NETBOX_TOKEN

# 9. Verify in NetBox
# Navigate to Devices > Devices in NetBox UI
```

## Additional Resources

- **Ansible Execution Environments**: https://docs.ansible.com/projects/ansible/latest/getting_started_ee/
- **Ansible Navigator Documentation**: https://ansible.readthedocs.io/projects/navigator/
- **Ansible Builder Documentation**: https://ansible.readthedocs.io/projects/builder/
- **Podman Documentation**: https://docs.podman.io/
- **Discovery Role README**: [ansible/roles/discovery/README.md](ansible/roles/discovery/README.md)
- **NetBox Registration Role README**: [ansible/roles/nb_register/README.md](ansible/roles/nb_register/README.md)

## Next Steps

1. **Automate Builds**: Create CI/CD pipeline to build and publish EE images
2. **Version Control**: Tag EE images with version numbers
3. **Registry**: Push images to private container registry
4. **Scheduled Jobs**: Set up cron jobs to run discovery/registration
5. **Monitoring**: Implement logging and alerting for automation runs
6. **Security**: Integrate with enterprise secret management

## Support

For issues or questions:
- Review role-specific READMEs in `ansible/roles/`
- Check Ansible EE documentation: https://docs.ansible.com/projects/ansible/latest/getting_started_ee/
- Consult NetBox documentation: https://docs.netbox.dev

