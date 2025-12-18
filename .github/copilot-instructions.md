# Copilot Instructions - Bare-Metal Automation Project

## Project Overview

This project automates bare-metal server discovery via Redfish BMC APIs and registers discovered hardware into NetBox DCIM. It consists of:

**Ansible Roles:**
- **discovery**: Queries BMCs via Redfish and generates YAML artifacts
- **nb_register**: Reads artifacts and creates/updates NetBox resources

**Python Tools:**
- **kea_lease_monitor.py**: Monitors Kea DHCP leases and generates cabinet-specific Ansible inventories
- **kea_lease_hook.py**: Kea DHCP hook for single lease processing
- **lint_yaml.py**: YAML validation and formatting
- **fix_ansible_lint.py**: Automated ansible-lint fixing

**Integration:**
- Kea DHCP integration triggers automated discovery when BMCs receive leases
- Cabinet-aware inventory files: `{site}-{cabinet}-discovery.yml`
- Manufacturer detection (Dell/HP/Supermicro) for future OEM-specific tasks

## Git Workflow Standards

### Branch Naming Conventions

Follow this format: `<type>/<scope>-<short-description>`

**Types:**
- `feat` - New feature or enhancement
- `fix` - Bug fix
- `refactor` - Code restructure without behavior change
- `docs` - Documentation only changes
- `test` - Adding or updating tests
- `chore` - Maintenance tasks (dependencies, tooling)
- `perf` - Performance improvements

**Scopes (optional but recommended):**
- `discovery` - Discovery role
- `nb-register` - NetBox registration role
- `playbooks` - Playbook orchestration
- `python` - Python utilities
- `kea` - Kea DHCP integration
- `docs` - Documentation

**Examples:**
```
feat/discovery-add-storage-inventory
fix/nb-register-tag-overwrite
refactor/discovery-simplify-fqdn-extraction
docs/update-testing-procedures
chore/python-upgrade-dependencies
perf/nb-register-batch-interface-creation
```

**Guidelines:**
- Use lowercase with hyphens (kebab-case)
- Keep descriptions under 50 characters
- Be specific but concise
- Avoid generic names like `updates` or `changes`
- Delete branches after merging to keep repository clean

### Commit Message Standards

Follow conventional commits format: `<type>(<scope>): <description>`

**Format:**
```
<type>(<scope>): <subject>

[optional body]

[optional footer]
```

**Types:** Same as branch types above (feat, fix, refactor, docs, test, chore, perf)

**Scopes:** Same as branch scopes (discovery, nb-register, playbooks, python, docs)

**Examples:**
```
feat(discovery): add processor inventory collection
fix(nb-register): prevent duplicate interface creation
refactor(playbooks): consolidate tag management tasks
docs: update lifecycle tag behavior documentation
chore(python): add type hints to validation utilities
```

**Guidelines:**
- Use imperative mood: "add feature" not "added feature"
- No period at end of subject line
- Subject line under 60 characters
- Body explains what and why, not how
- Reference issues/tickets in footer when applicable

### Gitflow Workflow Model

This project follows **Gitflow** branching strategy for organized development and releases.

**Branch Structure:**
- **master** - Primary branch containing production-ready code
- **develop** - Integration branch for ongoing development (optional for smaller projects)
- **feature/** - Feature development branches (created from master/develop)
- **fix/** - Bug fix branches (created from master/develop)
- **release/** - Release preparation branches (optional for versioned releases)
- **hotfix/** - Emergency fixes for production issues (created from master)

**Workflow Pattern:**
1. Create feature/fix branches from master (or develop if used)
2. Develop and commit changes following commit standards
3. Merge back to master (or develop) with non-fast-forward merge (`--no-ff`)
4. Tag releases on master for version tracking
5. Delete feature branches after successful merge

**Merge Strategy:**
- Use `git merge --no-ff` to preserve branch history
- Create merge commits that show feature integration points
- Avoid fast-forward merges for feature branches

**Example Workflow:**
```bash
# Create feature branch
git checkout -b feat/discovery-add-storage master

# Make changes and commit
git add .
git commit -m "feat(discovery): add storage inventory collection"

# Merge back to master with merge commit
git checkout master
git merge --no-ff feat/discovery-add-storage

# Tag release if applicable
git tag -a v1.2.0 -m "Release version 1.2.0"

# Clean up
git branch -d feat/discovery-add-storage
```

**References:**
- [Gitflow Workflow (Atlassian)](https://www.atlassian.com/git/tutorials/comparing-workflows/gitflow-workflow)
- [A successful Git branching model](https://nvie.com/posts/a-successful-git-branching-model/) (original Gitflow article by Vincent Driessen)
- [GitHub Flow](https://docs.github.com/en/get-started/quickstart/github-flow) (simplified alternative for continuous deployment)

**Project Adaptations:**
- Master branch is primary (develop branch optional for larger teams)
- Branch naming follows `<type>/<scope>-<short-description>` convention
- All merges to master must be non-fast-forward to preserve history
- Feature branches deleted after merge to keep repository clean

### Documentation Standards

**Progress Notes**
Personal progress notes are tracked locally (gitignored) and follow this naming convention:
```
docs/.YYYY-MM-DD-progress.md
```
Examples:
- `docs/.2025-12-04-progress.md`
- `docs/.2025-12-05-progress.md`

These files are prefixed with `.` to keep them hidden and are excluded from version control via `.gitignore` pattern: `docs/.*-progress.md`

**Project Documentation**
Project documentation goes in `docs/` and is committed to version control:
- `DESIGN.md` - Architecture and design decisions
- `TESTING.md` - Testing procedures and validation
- `LIFECYCLE_TAG_BEHAVIOR.md` - Lifecycle tag operational behavior
- `NETBOX_SETUP.md` - NetBox configuration guide

## Core Principles

### 1. Idempotency
All Ansible tasks MUST be idempotent - safe to run multiple times without unwanted side effects.

**Guidelines:**
- Use `state: present` for resource creation (not explicit create commands)
- Use `when` conditions to skip unnecessary operations
- Register task results for conditional execution
- Avoid operations that accumulate (append, increment) without checks
- Use `changed_when: false` for read-only operations

**Examples:**
```yaml
# GOOD: Idempotent directory creation
- name: Ensure output directory exists
  ansible.builtin.file:
    path: "{{ discovery_artifact_dir }}"
    state: directory
    mode: '0755'

# GOOD: Idempotent NetBox resource creation
- name: Ensure NetBox site exists
  netbox.netbox.netbox_site:
    netbox_url: "{{ nb_url }}"
    netbox_token: "{{ nb_token }}"
    data:
      name: "{{ device_site }}"
      slug: "{{ device_site | lower }}"
    state: present
  when: nb_auto_create_refs
```

### 2. Error Handling

**Validation First:**
- Validate required variables at role entry point
- Use `ansible.builtin.assert` for parameter validation
- Fail fast with clear error messages

**Examples:**
```yaml
# Validate required parameters
- name: Validate required NetBox connection parameters
  ansible.builtin.assert:
    that:
      - nb_url | length > 0
      - nb_token | length > 0
    fail_msg: "nb_url and nb_token must be provided"
    quiet: true

# Fail with context when artifacts missing
- name: Fail if no artifacts found
  ansible.builtin.fail:
    msg: "No discovery artifacts found in {{ discovery_artifact_dir }}"
  when: artifacts_to_process | length == 0
```

**Graceful Degradation:**
- Use `when` conditions to skip optional features
- Use `omit` for optional parameters
- Provide sensible defaults for non-critical values

**Examples:**
```yaml
# Optional field handling
asset_tag: "{{ system_info.asset_tag if system_info.asset_tag else omit }}"

# Conditional feature execution
- name: Create BMC interface
  netbox.netbox.netbox_device_interface:
    # ... configuration ...
  when: nb_create_bmc_interface
```

### 3. Variable Naming Conventions

**Prefixes:**
- `discovery_*` - Variables for discovery role
- `nb_*` - Variables for NetBox registration role
- `bmc_*` - BMC-related variables
- `artifact_*` - Artifact-related variables

**Case:**
- Use `snake_case` for all variable names
- Use lowercase for boolean values: `true`/`false`
- Use descriptive names, avoid abbreviations unless common (BMC, FQDN, IP)

**Examples:**
```yaml
# GOOD
discovery_bmc_username: "admin"
nb_auto_create_refs: true
bmc_fqdn_map: {}

# BAD
usr: "admin"
autoCreate: true
FQDN_MAP: {}
```

### 4. Loop Control

Always use descriptive `loop_var` and `label` for clarity and to avoid variable collisions.

**Required:**
- `loop_var`: Custom variable name (not `item`)
- `label`: Short display value for output

**Examples:**
```yaml
# GOOD: Clear loop variable and concise label
- name: Register network interfaces in NetBox
  netbox.netbox.netbox_device_interface:
    data:
      device: "{{ device_name }}"
      name: "{{ interface.id }}"
      mac_address: "{{ interface.mac_address }}"
  loop: "{{ artifact_data.network_interfaces }}"
  loop_control:
    loop_var: interface
    label: "{{ interface.id }}"

# BAD: Uses default 'item' and no label
- name: Register network interfaces
  netbox.netbox.netbox_device_interface:
    data:
      device: "{{ device_name }}"
      name: "{{ item.id }}"
  loop: "{{ artifact_data.network_interfaces }}"
```

### 5. Task Naming

**Format:** `<Action verb> + <Resource/Object> + [Context/Location]`

**Action Verbs (Standard):**
- **Validate** - Check conditions or requirements
- **Ensure** - Idempotent resource creation (create if missing)
- **Create** - Explicit resource creation or registration
- **Extract** - Pull/parse data from existing structures
- **Build** - Construct new data structures or lists
- **Collect** - Gather multiple related items
- **Track** - Record information for later use
- **Query** - Retrieve data from external systems
- **Calculate** - Compute or determine values
- **Discover** - Find files or resources
- **Display** - Show information to user
- **Render** - Generate output from templates

**Guidelines:**
- Start with action verb from standard list above
- Be specific about resource being operated on
- Add context/location for clarity: "in NetBox", "from artifact", "for summary"
- Use "Ensure" for idempotent operations with `state: present`
- Use "Create" for explicit creation or registration operations
- Use "Query" instead of "Check" or "Get" for external API calls
- Use "Extract" instead of "Get" for parsing/extracting data
- Keep names under 60 characters when possible
- Avoid redundant words: "current", "already", "now"
- Never use generic verbs: "Process", "Handle", "Do", "Run"

**Examples:**
```yaml
# Resource Creation/Management
- name: Ensure NetBox site exists
- name: Ensure lifecycle tag exists in NetBox
- name: Create or update device in NetBox
- name: Create BMC management interface
- name: Create inventory items for storage drives

# Data Extraction/Manipulation
- name: Extract artifact metadata
- name: Extract lifecycle tag slugs from device
- name: Extract site from BMC name prefix
- name: Build device tag slugs list for NetBox
- name: Build BMC FQDN lookup map

# External System Queries
- name: Query existing device from NetBox
- name: Query BMC FQDN from host interfaces
- name: Query system resources via Redfish

# Validation/Tracking
- name: Validate required NetBox connection parameters
- name: Validate artifacts were discovered
- name: Track registered device for summary
- name: Calculate lifecycle tag application decision

# Output/Display
- name: Display discovery summary
- name: Display registration summary
- name: Render discovery artifacts from template

# GOOD Examples
- name: Ensure NetBox manufacturer exists
- name: Extract BMC FQDN components
- name: Query existing device from NetBox
- name: Build artifacts processing list
- name: Create network interfaces in NetBox
- name: Calculate lifecycle tag application decision
- name: Track registered device for summary
- name: Discover artifact files in directory

# BAD Examples (Avoid)
- name: Create site                          # Too vague
- name: Process BMC                          # Generic verb
- name: Register stuff                       # Unprofessional
- name: Get data                             # Use Extract/Query
- name: Check if device exists               # Use Query
- name: Set variable                         # Use Build/Calculate
- name: Do NetBox operations                 # Generic, no resource
- name: Handle artifacts                     # Generic verb
```

### 6. Sensitive Data Handling

**Never log sensitive data:**
- Use `no_log: true` for tasks with credentials or tokens
- Use `no_log: true` for tasks that output large data structures
- Mask credentials in task output using `loop_control: label`

**Examples:**
```yaml
# Prevent credential exposure
- name: Gather BMC FQDN
  community.general.redfish_info:
    category: Manager
    command: GetHostInterfaces
    baseuri: "{{ bmc.ip }}"
    username: "{{ discovery_bmc_username }}"
    password: "{{ discovery_bmc_password }}"
  register: redfish_hostif
  loop: "{{ bmc_targets }}"
  loop_control:
    loop_var: bmc
    label: "{{ bmc.name | default(bmc.ip) }}"
  # Credentials in task parameters - don't log full output

# Prevent large data dumps
- name: Render discovery artifact for each BMC
  ansible.builtin.template:
    src: "{{ discovery_template_path }}"
    dest: "{{ discovery_artifact_dir }}/{{ output_filename }}-discovery.yml"
  loop: "{{ redfish_info_results.results }}"
  loop_control:
    loop_var: result
  no_log: true  # Artifacts contain large data structures
```

### 7. Conditional Execution

**Use `when` for:**
- Optional features (`nb_create_bmc_interface`)
- Auto-creation flags (`nb_auto_create_refs`)
- Data validation (`| length > 0`)
- Feature gates (`nb_create_storage_inventory`)

**Combine conditions properly:**
```yaml
# Multiple conditions - all must be true
when:
  - nb_auto_create_refs
  - nb_default_device_role | length > 0

# Short-circuit evaluation
when: nb_auto_create_refs and physical_id.cabinet_id | length > 0
```

### 8. Data Extraction and Transformation

**Use `set_fact` for:**
- Extracting nested data
- Building derived values
- Creating lookup dictionaries
- Parsing structured data

**Patterns:**
```yaml
# Extract nested data
- name: Extract artifact metadata
  ansible.builtin.set_fact:
    physical_id: "{{ artifact_data.physical_identity }}"
    system_info: "{{ artifact_data.system_information[0] }}"

# Build derived values
- name: Extract site from BMC name prefix
  ansible.builtin.set_fact:
    device_site: "{{ bmc_name_parts[0] | upper }}"

# Build lookup dictionaries
- name: Build FQDN map for artifact rendering
  ansible.builtin.set_fact:
    bmc_fqdn_map: >-
      {{
        (bmc_fqdn_map | default({}))
        | combine({ item.bmc.ip: item.redfish_facts.host_interfaces.entries[0].ManagerEthernetInterface.FQDN })
      }}
  loop: "{{ redfish_hostif.results }}"
```

### 9. Template Usage

**Jinja2 templates for artifacts:**
- Separate logic from output
- Use YAML-safe formatting
- Handle null/empty values explicitly
- Match PyYAML output format (minimal quoting)

**Template best practices:**
```jinja2
{# Extract variables at top #}
{% set bmc_name = (bmc_fqdn | split('.'))[0] if bmc_fqdn else bmc_ip %}
{% set cabinet_match = bmc_name | regex_search('cab(\\d+)', '\\1') %}
{% set cabinet_id = cabinet_match[0] if cabinet_match else '' %}

{# Use explicit null for empty values #}
firmware_version: {{ item.firmware_version if item.firmware_version else 'null' }}

{# Use native YAML lists, not to_json #}
identifiers:
{% for ident in item.identifiers %}
- DurableName: {{ ident.DurableName }}
  DurableNameFormat: {{ ident.DurableNameFormat }}
{% endfor %}
```

### 10. Module Selection

**Prefer fully qualified collection names (FQCN):**
```yaml
# GOOD
ansible.builtin.template
ansible.builtin.set_fact
community.general.redfish_info
netbox.netbox.netbox_device

# AVOID
template
set_fact
redfish_info
```

**Use appropriate modules:**
- `ansible.builtin.file` for directories/files
- `ansible.builtin.template` for Jinja2 rendering
- `ansible.builtin.set_fact` for variable manipulation
- `ansible.builtin.include_vars` for loading YAML/JSON
- `ansible.builtin.include_tasks` for task reuse
- Collection-specific modules for external APIs (netbox.netbox.*, community.general.*)

### 11. Role Structure

**Standard layout:**
```
roles/
  <role_name>/
    README.md          # Comprehensive documentation
    defaults/
      main.yml         # Default variables (user-overridable)
    vars/
      main.yml         # Internal variables (not overridable)
    tasks/
      main.yml         # Entry point
      <subtask>.yml    # Included task files
    templates/
      <name>.j2        # Jinja2 templates
    meta/
      main.yml         # Role metadata
```

**Role design:**
- Single responsibility per role
- Clear entry point (`tasks/main.yml`)
- Use `include_tasks` for complex multi-step workflows
- Extensive README with examples
- Sensible defaults that work out-of-the-box

### 12. Configuration Management

**ansible.cfg standards:**
```ini
[defaults]
# Use lowercase true/false for booleans
host_key_checking = false
deprecation_warnings = false

# Descriptive callback plugins
stdout_callback = yaml
callback_whitelist = profile_tasks, timer

# Relative paths from ansible.cfg location
roles_path = ./roles
inventory = ./inventory
```

**Playbook standards:**
```yaml
---
- name: Descriptive playbook name
  hosts: localhost
  gather_facts: false  # Disable if not needed

  vars:
    # Use environment variables for credentials
    discovery_bmc_username: "{{ lookup('env', 'BMC_USERNAME') }}"
    nb_url: "{{ lookup('env', 'NETBOX_URL') }}"

  roles:
    - discovery
```

### 13. Documentation

**README requirements:**
- Overview and features
- Requirements (Ansible version, collections, Python packages)
- Role variables with defaults
- Example playbooks (basic and advanced)
- Troubleshooting section
- Security considerations

**Inline comments:**
- Comment complex logic
- Explain non-obvious decisions
- Document debugging aids (commented-out debug tasks)
- Reference external documentation for API-specific behavior

## Anti-Patterns to Avoid

**DO NOT:**
- Use `command` or `shell` modules when native modules exist
- Hardcode credentials in playbooks or roles
- Use `item` as loop variable without `loop_control`
- Create tasks that only work on first run
- Use `debug` tasks in production (comment them out)
- Ignore `changed` status (use `changed_when` when appropriate)
- Use uppercase boolean values (`True`/`False`)
- Omit `when` conditions for optional features
- Create monolithic task files (split into includes)
- Use short/cryptic variable names

## Testing and Validation

**Before committing:**
- Run `ansible-playbook --syntax-check`
- Test idempotency (run twice, verify no changes on second run)
- Verify with different variable combinations
- Test error conditions (missing vars, invalid credentials)
- Check that `no_log` is used appropriately
- Validate YAML artifacts with `yamllint`

**Validation patterns:**
```yaml
# Check syntax
ansible-playbook playbooks/discovery.yml --syntax-check

# Test idempotency
ansible-playbook playbooks/register.yml
ansible-playbook playbooks/register.yml  # Should show no changes

# Dry run (limited support)
ansible-playbook playbooks/discovery.yml --check
```

## Security Best Practices

1. **Credentials:**
   - Use environment variables
   - Use Ansible Vault for encrypted storage
   - Never commit credentials to version control

2. **API Tokens:**
   - Use least-privilege tokens
   - Rotate tokens regularly
   - Validate tokens before operations

3. **Certificate Validation:**
   - Enable in production (`validate_certs: true`)
   - Only disable for development/testing

4. **Logging:**
   - Use `no_log: true` for sensitive tasks
   - Sanitize output with `loop_control: label`
   - Avoid logging full API responses

## Code Review Checklist

When reviewing Ansible code:
- [ ] All tasks are idempotent
- [ ] Variables follow naming conventions
- [ ] Loops use `loop_control` with `loop_var` and `label`
- [ ] Task names are descriptive and consistent
- [ ] Sensitive data uses `no_log: true`
- [ ] Conditionals use `when` appropriately
- [ ] Boolean values are lowercase (`true`/`false`)
- [ ] FQCN used for all modules
- [ ] Error handling includes validation and clear messages
- [ ] Documentation is complete and accurate
- [ ] No hardcoded credentials or secrets
- [ ] Templates generate valid YAML
- [ ] Role defaults are sensible and documented

## Python Tooling Standards

**Script Requirements:**
- Use standard ASCII characters only (no Unicode symbols like ✓, ⚠, ✗)
- Use `[OK]`, `[WARNING]`, `[ERROR]` prefixes for status messages
- Support multiple input paths with `nargs="+"`
- Provide `--dry-run` and `--verify` options for validation
- Use type hints for function signatures
- Include comprehensive docstrings (module, class, function level)
- Use `argparse.RawDescriptionHelpFormatter` with usage examples in epilog

**Output Formatting:**
```python
# GOOD: ASCII-only status messages
print("[OK] Operation completed successfully")
print("[WARNING] Potential issue detected")
print("[ERROR] Operation failed")

# BAD: Unicode symbols that may not render in all terminals
print("✓ Success")
print("⚠ Warning")
```

**Multi-file Processing Pattern:**
```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", help="Path(s) to process")
    args = parser.parse_args()
    
    total_processed = 0
    failed_items = []
    
    for idx, path in enumerate(args.paths, 1):
        print(f"Processing {idx}/{len(args.paths)}: {path}")
        # ... process each path ...
    
    # Summary with aggregate results
    print("\nSUMMARY")
    print(f"Items processed: {len(args.paths)}")
    if failed_items:
        return 1
    return 0
```

## Examples Reference

See the following files for implementation examples:
- `ansible/roles/discovery/tasks/main.yml` - Loop control, data extraction, idempotent operations
- `ansible/roles/nb_register/tasks/process_artifact.yml` - Conditional execution, auto-creation, error handling
- `ansible/roles/nb_register/tasks/main.yml` - Validation, artifact discovery, include_tasks pattern
- `ansible/templates/discovery_artifact.yml.j2` - Jinja2 templating, YAML formatting
- `ansible/roles/discovery/README.md` - Documentation standards
- `ansible/roles/nb_register/README.md` - Comprehensive role documentation
- `python/fix_ansible_lint.py` - Python script with multi-file processing, ASCII-only output
