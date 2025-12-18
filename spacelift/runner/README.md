# Spacelift Runner - Bare-Metal Automation

This Docker image provides an Ansible execution environment for Spacelift to run bare-metal lifecycle automation playbooks.

## Purpose

Execute Ansible playbooks for bare-metal server lifecycle management within Spacelift stacks:
- **Discovery**: Query BMCs via Redfish API, collect hardware inventory
- **Registration**: Create/update NetBox DCIM resources
- **Future**: Provisioning, configuration, decommissioning

## Base Image

**Base**: `public.ecr.aws/spacelift/runner-terraform:latest`

Includes:
- Terraform and OpenTofu
- Common CLI tools (curl, jq, git, etc.)
- AWS CLI
- Docker client

**Additions**:
- Ansible Core 2.16+
- Ansible Collections: `community.general`, `netbox.netbox`
- Python libraries: pynetbox, pyyaml, requests, cryptography

## Build Instructions

### Local Build

```bash
cd spacelift/runner

# Build image
docker build -t baremetal-ansible-runner:latest .

# Test image
docker run --rm baremetal-ansible-runner:latest ansible --version
docker run --rm baremetal-ansible-runner:latest ansible-galaxy collection list
```

### Push to Registry

```bash
# Tag for your registry
docker tag baremetal-ansible-runner:latest <your-registry>/baremetal-ansible-runner:1.0.0

# Push to registry
docker push <your-registry>/baremetal-ansible-runner:1.0.0
```

### ECR Example (AWS)

```bash
# Authenticate to ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Tag for ECR
docker tag baremetal-ansible-runner:latest \
  <account-id>.dkr.ecr.us-east-1.amazonaws.com/baremetal-ansible-runner:1.0.0

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/baremetal-ansible-runner:1.0.0
```

## Usage in Spacelift

### Stack Configuration

In your Spacelift stack settings:

```hcl
# .spacelift/config.yml or via UI
runner_image: <your-registry>/baremetal-ansible-runner:1.0.0
```

### Environment Variables

Required environment variables (set in Spacelift stack):

```bash
# NetBox Configuration
NETBOX_URL=https://netbox.global.plex/
NETBOX_TOKEN=<retrieved-from-vault>

# BMC Credentials
BMC_USERNAME=<retrieved-from-vault>
BMC_PASSWORD=<retrieved-from-vault>

# Optional: Override artifact directory
DISCOVERY_ARTIFACT_DIR=/tmp/artifacts
```

### Workflow Script

Example `workflow.sh` in Spacelift stack:

```bash
#!/bin/bash
set -euo pipefail

# Spacelift provides these inputs
SITE="${TF_VAR_site}"
CABINET="${TF_VAR_cabinet}"
BMC_IPS="${TF_VAR_bmc_ips}"  # JSON array

# Convert JSON array to Ansible format
BMC_TARGETS=$(echo "$BMC_IPS" | jq -r '[.[] | {ip: .}]')

# Execute lifecycle playbook
ansible-playbook playbooks/lifecycle.yml \
  -e "bmc_targets=$BMC_TARGETS" \
  -e "discovery_bmc_username=$BMC_USERNAME" \
  -e "discovery_bmc_password=$BMC_PASSWORD" \
  -e "nb_url=$NETBOX_URL" \
  -e "nb_token=$NETBOX_TOKEN" \
  -e "nb_auto_create_refs=true" \
  -v
```

## Image Contents

### Installed Collections

- `community.general` (>= 8.0.0)
  - Includes `redfish_info` module for BMC queries
- `netbox.netbox` (>= 3.18.0)
  - NetBox API modules for DCIM resource management

### Python Packages

| Package | Version | Purpose |
|---------|---------|---------|
| ansible-core | >= 2.16.0 | Ansible engine |
| pynetbox | >= 7.0.0 | NetBox Python client |
| pyyaml | >= 6.0 | YAML parsing for artifacts |
| requests | >= 2.32.0 | HTTP client |
| cryptography | >= 43.0.0 | SSL/TLS support |
| pyOpenSSL | >= 24.0.0 | OpenSSL bindings |

### System Packages

- Python 3.x
- OpenSSH client
- Git
- sshpass (for password-based SSH)

## Repository Integration

This runner uses the repository's `ansible.cfg` configuration at runtime:

```ini
# ansible/ansible.cfg (mounted in Spacelift workspace)
[defaults]
roles_path = ./roles
host_key_checking = false
deprecation_warnings = false
stdout_callback = yaml
```

No additional Ansible configuration needed in the image.

## Testing

### Unit Test

```bash
# Build and test locally
docker build -t test-runner .

# Verify Ansible version
docker run --rm test-runner ansible --version

# Verify collections installed
docker run --rm test-runner ansible-galaxy collection list

# Test playbook syntax (requires repo mounted)
docker run --rm -v $(pwd)/../..:/workspace test-runner \
  bash -c "cd /workspace/ansible && ansible-playbook playbooks/lifecycle.yml --syntax-check"
```

### Integration Test

```bash
# Run full lifecycle playbook (requires credentials)
docker run --rm \
  -v $(pwd)/../..:/workspace \
  -e BMC_USERNAME=test \
  -e BMC_PASSWORD=test \
  -e NETBOX_URL=https://netbox.test \
  -e NETBOX_TOKEN=test123 \
  test-runner \
  bash -c "cd /workspace/ansible && ansible-playbook playbooks/lifecycle.yml -e 'bmc_targets=[{ip:\"172.30.19.42\"}]' --check"
```

## Security Considerations

### Credentials

- **Never** hardcode credentials in the image
- Use Spacelift environment variables
- Retrieve credentials from Vault at runtime
- Rotate credentials regularly

### Image Scanning

Scan image for vulnerabilities before deployment:

```bash
# Using Trivy
trivy image baremetal-ansible-runner:latest

# Using Docker Scout
docker scout cves baremetal-ansible-runner:latest
```

### Network Access

Runner needs outbound access to:
- BMC management network (Redfish API - port 443)
- NetBox API (HTTPS - port 443)
- Vault server (HTTPS - port 8200)

## Maintenance

### Version Updates

**Ansible Collections:**
```bash
# Check for updates
docker run --rm baremetal-ansible-runner:latest \
  ansible-galaxy collection list --outdated

# Update requirements.yml with new versions
# Rebuild image
```

**Base Image:**
```bash
# Pull latest Spacelift runner
docker pull public.ecr.aws/spacelift/runner-terraform:latest

# Rebuild with latest base
docker build --no-cache -t baremetal-ansible-runner:latest .
```

### Changelog

- **v1.0.0** (2025-12-18): Initial release
  - Ansible Core 2.16+
  - Collections: community.general 8.0+, netbox.netbox 3.18+
  - Supports discovery and nb_register roles

## Troubleshooting

### Ansible Not Found

**Issue**: `ansible: command not found`

**Solution**: Ensure `ansible-core` is installed in build:
```dockerfile
RUN pip3 install --no-cache-dir ansible-core>=2.16.0
```

### Collection Not Found

**Issue**: `ERROR! couldn't resolve module/action 'netbox.netbox.netbox_device'`

**Solution**: Verify collection installed:
```bash
docker run --rm <image> ansible-galaxy collection list
```

### Permission Denied

**Issue**: Cannot write to `/mnt/workspace`

**Solution**: Check Spacelift workspace mount permissions. Artifacts should be written to `/tmp` or workspace subdirectories.

### SSL Certificate Errors

**Issue**: `SSL: CERTIFICATE_VERIFY_FAILED`

**Solution**: For self-signed certificates, set environment variable:
```bash
export PYTHONHTTPSVERIFY=0  # Development only
```

Or configure Ansible:
```yaml
# ansible.cfg
[defaults]
host_key_checking = false
```

## References

- [Spacelift Runner Image Documentation](https://docs.spacelift.io/concepts/stack/stack-settings#runner-image)
- [Ansible Documentation](https://docs.ansible.com/)
- [NetBox Ansible Collection](https://github.com/netbox-community/ansible_modules)
- [Community General Collection](https://docs.ansible.com/ansible/latest/collections/community/general/)

## Support

**Questions or Issues:**
- Repository: https://github.com/yourorg/baremetal
- Email: infrastructure@site.com
- Slack: #infrastructure-automation

---

**Maintained By**: Core Infrastructure Team  
**Last Updated**: December 18, 2025
