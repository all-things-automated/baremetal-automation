# Lifecycle Tag Behavior

## Overview
Lifecycle tags are **mutually exclusive** - a device can only have ONE lifecycle tag at any time. When transitioning between lifecycle states, the old lifecycle tag is automatically replaced with the new one.

## Lifecycle States
```
discovered → commissioned → deployed → repurpose-ready → discovered (cycle)
```

## Tag Replacement Behavior

### Scenario 1: New Device (No Existing Tags)
```yaml
Current tags: []
Action: discovery role runs
Result: ['discovered', 'automation-managed', 'us3']
```

### Scenario 2: Device Already Discovered
```yaml
Current tags: ['discovered', 'automation-managed', 'us3']
Action: discovery role runs again
Result: ['discovered', 'automation-managed', 'us3']
```
**No change** - `nb_lifecycle_force_overwrite: false` prevents re-applying same tag

### Scenario 3: Commission Role Transitions Device
```yaml
Current tags: ['discovered', 'automation-managed', 'us3']
Action: commission role runs
Result: ['commissioned', 'automation-managed', 'us3']
```
**Lifecycle tag replaced** - `discovered` removed, `commissioned` added

### Scenario 4: Deploy Role Transitions Device
```yaml
Current tags: ['commissioned', 'automation-managed', 'us3']
Action: deploy role runs
Result: ['deployed', 'automation-managed', 'us3']
```
**Lifecycle tag replaced** - `commissioned` removed, `deployed` added

### Scenario 5: Force Overwrite Enabled
```yaml
Current tags: ['commissioned', 'automation-managed', 'us3']
Action: discovery role runs with nb_lifecycle_force_overwrite: true
Result: ['discovered', 'automation-managed', 'us3']
```
**Forced replacement** - Reverts device back to `discovered` state

## Implementation Details

### How It Works

**Step 1: Query Current Tags**
```yaml
- name: Extract lifecycle tag slugs from device
  ansible.builtin.set_fact:
    current_lifecycle_tag_slugs: >
      {{
        (nb_device_query.json.results[0].tags | default([]) 
        | selectattr('slug', 'match', '^(discovered|commissioned|deployed|repurpose-ready)$') 
        | map(attribute='slug') | list)
        if nb_device_query.json.count > 0
        else []
      }}
```
Extracts ONLY lifecycle tags (discovered, commissioned, deployed, repurpose-ready)

**Step 2: Decide Whether to Apply New Lifecycle Tag**
```yaml
- name: Calculate lifecycle tag application decision
  ansible.builtin.set_fact:
    should_apply_lifecycle: >
      {{
        nb_lifecycle_force_overwrite or (current_lifecycle_tag_slugs | length == 0)
      }}
```
Apply new lifecycle tag if:
- Force overwrite is enabled, OR
- Device has no lifecycle tags

**Step 3: Build Final Tag List**
```yaml
- name: Build device tag slugs list for NetBox
  ansible.builtin.set_fact:
    device_tags: >
      {{
        (
          ([nb_tags.lifecycle.slug] if ('lifecycle' in nb_apply_tags and should_apply_lifecycle) else current_lifecycle_tag_slugs) +
          (nb_tags | dict2items | selectattr('key', 'in', nb_apply_tags) | rejectattr('key', 'in', ['lifecycle', 'site']) | map(attribute='value.slug') | list) +
          ([site_tag_config.slug] if 'site' in nb_apply_tags else [])
        ) | unique
      }}
```

**Key Logic:**
- **If applying new lifecycle tag**: Use `nb_tags.lifecycle.slug` (replaces old)
- **If preserving existing**: Use `current_lifecycle_tag_slugs` (keeps old)
- **Other tags**: Always included (automation, site, etc.)
- **Deduplication**: `unique` filter ensures no duplicates

**Step 4: NetBox Device Update**
```yaml
- name: Create or update device in NetBox
  netbox.netbox.netbox_device:
    data:
      name: "{{ device_name }}"
      tags: "{{ device_tags }}"  # Replaces ALL tags
```
NetBox device module **replaces** the entire tag list, ensuring old lifecycle tags are removed.

## Configuration Options

### Default Behavior (Preserve Manual Changes)
```yaml
nb_lifecycle_force_overwrite: false
```
- Discovery role won't overwrite manually applied lifecycle tags
- Allows operators to manually set commissioned/deployed without automation reverting it
- Use case: Manual lifecycle management with automated discovery

### Force Overwrite (Automation Always Wins)
```yaml
nb_lifecycle_force_overwrite: true
```
- Discovery role always sets devices back to `discovered`
- Use case: Strict automation control, no manual lifecycle changes

## Role Design Patterns

### Discovery Role
```yaml
# ansible/roles/discovery/defaults/main.yml
discovery_lifecycle_state: "discovered"

# Always starts devices at 'discovered' state
# Respects nb_lifecycle_force_overwrite setting
```

### Commission Role (Future)
```yaml
# ansible/roles/commission/defaults/main.yml
commission_lifecycle_state: "commissioned"

# Transitions discovered → commissioned
# Should set nb_lifecycle_force_overwrite: true to ensure transition
```

### Deploy Role (Future)
```yaml
# ansible/roles/deploy/defaults/main.yml
deploy_lifecycle_state: "deployed"

# Transitions commissioned → deployed
# Should set nb_lifecycle_force_overwrite: true to ensure transition
```

## Testing Lifecycle Transitions

### Test 1: Discovery → Commission
```bash
# Step 1: Discover device
ansible-playbook lifecycle.yml
# Result: discovered tag

# Step 2: Commission device (future role)
ansible-playbook commission.yml --limit us3-cab10-ru18-idrac
# Result: commissioned tag (discovered removed)

# Step 3: Verify in NetBox
curl -H "Authorization: Token $TOKEN" \
  "$NETBOX_URL/api/dcim/devices/?name=us3-cab10-ru18-idrac" \
  | jq '.results[0].tags'
# Should show: [{"slug": "commissioned"}, {"slug": "automation-managed"}, {"slug": "us3"}]
```

### Test 2: Prevent Discovery from Reverting Commissioned Device
```bash
# Device currently has 'commissioned' tag

# Run discovery with force_overwrite: false (default)
ansible-playbook lifecycle.yml
# Result: commissioned tag preserved (not reverted to discovered)

# Run discovery with force_overwrite: true
ansible-playbook lifecycle.yml -e "nb_lifecycle_force_overwrite=true"
# Result: discovered tag applied (reverts from commissioned)
```

## NetBox Tag Configuration

### Required Lifecycle Tags
Create these tags in NetBox (or enable auto-creation):

```yaml
# Lifecycle - Discovered
name: "Lifecycle - Discovered"
slug: "discovered"
color: "2196f3"  # Blue
description: "Device discovered via BMC but not yet commissioned"

# Lifecycle - Commissioned
name: "Lifecycle - Commissioned"
slug: "commissioned"
color: "ff9800"  # Orange
description: "Device commissioned and ready for deployment"

# Lifecycle - Deployed
name: "Lifecycle - Deployed"
slug: "deployed"
color: "4caf50"  # Green
description: "Device deployed and in production use"

# Lifecycle - Repurpose Ready
name: "Lifecycle - Repurpose Ready"
slug: "repurpose-ready"
color: "9c27b0"  # Purple
description: "Device decommissioned and ready for repurposing"
```

### Tag Regex Pattern
The lifecycle tag extraction uses this regex pattern:
```regex
^(discovered|commissioned|deployed|repurpose-ready)$
```

**To add new lifecycle states:**
1. Create tag in NetBox
2. Update regex pattern in `process_artifact.yml`
3. Create corresponding role (e.g., `decommission`)

## Troubleshooting

### Problem: Device has multiple lifecycle tags
```yaml
Current tags: ['discovered', 'commissioned', 'automation-managed']
```

**Cause:** Manual tag addition or older code without mutual exclusion

**Solution:**
```bash
# Force re-run with overwrite to clean up
ansible-playbook lifecycle.yml -e "nb_lifecycle_force_overwrite=true"
```

### Problem: Lifecycle tag not being applied
```yaml
Current tags: ['automation-managed', 'us3']  # No lifecycle tag
```

**Diagnosis:**
```yaml
# Uncomment debug task in process_artifact.yml
- name: Display lifecycle decision
  ansible.builtin.debug:
    msg: "Device {{ device_name }}: Current tag slugs={{ current_lifecycle_tag_slugs | join(', ') or 'none' }}, Will apply={{ should_apply_lifecycle }}"
```

**Common causes:**
- `'lifecycle' not in nb_apply_tags`
- `should_apply_lifecycle: false` due to existing lifecycle tag
- `nb_auto_create_refs: false` preventing tag creation

### Problem: Discovery keeps reverting commissioned devices
```yaml
Device was commissioned, but discovery resets to discovered
```

**Cause:** `nb_lifecycle_force_overwrite: true` in inventory/playbook

**Solution:**
```yaml
# In inventory or group_vars
nb_lifecycle_force_overwrite: false  # Let commission role manage transitions
```

## Best Practices

### 1. Lifecycle Role Responsibilities
- **Discovery role**: Only applies `discovered` to new/untagged devices
- **Commission role**: Explicitly transitions `discovered` → `commissioned`
- **Deploy role**: Explicitly transitions `commissioned` → `deployed`

### 2. Force Overwrite Usage
- **Discovery**: Use `false` (preserve manual changes)
- **Commission**: Use `true` (force transition)
- **Deploy**: Use `true` (force transition)

### 3. Tag Validation
Add assertions to ensure clean lifecycle state:
```yaml
- name: Validate single lifecycle tag
  ansible.builtin.assert:
    that:
      - device_tags | select('match', '^(discovered|commissioned|deployed|repurpose-ready)$') | list | length == 1
    fail_msg: "Device must have exactly ONE lifecycle tag"
```

### 4. Audit Trail
Log lifecycle transitions for compliance:
```yaml
- name: Log lifecycle transition
  ansible.builtin.debug:
    msg: "Transitioning {{ device_name }} from {{ current_lifecycle_tag_slugs | join(',') | default('none') }} to {{ nb_tags.lifecycle.slug }}"
  when: should_apply_lifecycle
```

## Summary

[OK] **Mutually Exclusive**: Only ONE lifecycle tag per device  
[OK] **Automatic Replacement**: New lifecycle tag removes old one  
[OK] **Configurable**: Use `nb_lifecycle_force_overwrite` to control behavior  
[OK] **Non-Lifecycle Tags Preserved**: automation, site tags remain unchanged  
[OK] **NetBox Native**: Uses NetBox's tag replacement mechanism  

The system is designed for seamless lifecycle progression without tag accumulation.
