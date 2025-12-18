# NetBox Setup Guide

This document describes the required NetBox configuration for the bare-metal automation roles.

## Overview

The `nb_register` role uses **NetBox tags** to track device lifecycle state. Tags are **automatically created** by the role and require **no manual NetBox configuration**. This approach provides:

- [OK] Zero-configuration setup
- [OK] Visual color-coded status indicators
- [OK] Easy filtering in NetBox UI
- [OK] No API version dependencies

## Lifecycle Tags (Auto-Created)

The role automatically creates and manages the following lifecycle tags:

| Tag Name | Color | Description |
|----------|-------|-------------|
| `lifecycle:discovered` | Blue (2196f3) | Device discovered but not yet commissioned |
| `lifecycle:commissioned` | Orange (ff9800) | Device commissioned and ready for OS deployment |
| `lifecycle:deployed` | Green (4caf50) | Device deployed with OS and in production |
| `lifecycle:repurpose-ready` | Grey (9e9e9e) | Device decommissioned and ready for rediscovery |

**Tag Creation**: When `nb_auto_create_refs: true`, tags are automatically created with the colors defined in `nb_lifecycle_tag_colors`.

**Tag Protection**: The role preserves existing lifecycle tags by default (`nb_lifecycle_force_overwrite: false`), preventing accidental demotion of commissioned/deployed devices.

## API Token Requirements

The NetBox API token used by the roles must have the following permissions:

### Minimum Required Permissions

| Resource | Permissions |
|----------|-------------|
| **dcim \| device** | View, Add, Change |
| **dcim \| device type** | View, Add (if `nb_auto_create_refs: true`) |
| **dcim \| device role** | View, Add (if `nb_auto_create_refs: true`) |
| **dcim \| manufacturer** | View, Add (if `nb_auto_create_refs: true`) |
| **dcim \| site** | View, Add (if `nb_auto_create_refs: true`) |
| **dcim \| rack** | View, Add (if `nb_auto_create_refs: true`) |
| **dcim \| interface** | View, Add, Change |
| **dcim \| inventory item** | View, Add (if `nb_create_storage_inventory: true`) |
| **ipam \| ip address** | View, Add, Change |
| **ipam \| service** | View, Add (if `nb_create_bmc_interface: true`) |
| **extras \| tag** | View, Add (for lifecycle tag auto-creation) |

### Creating an API Token

1. Navigate to your NetBox user profile (top-right corner)
2. Click **API Tokens** tab
3. Click **Add a token**
4. Configure:
   - **Write enabled**: Yes
   - **Description**: Bare-Metal Automation
5. Copy the generated token immediately (it won't be shown again)
6. Set in environment: `export NETBOX_TOKEN="your-token-here"`

## Verification

After running the `nb_register` role, verify lifecycle tags were created:

```bash
curl -X GET \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Accept: application/json" \
  "https://netbox.example.com/api/extras/tags/?name__ic=lifecycle"
```

You should see all four lifecycle tags with their configured colors.

To verify tags on a specific device:

```bash
curl -X GET \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Accept: application/json" \
  "https://netbox.example.com/api/dcim/devices/?name=DEVICE_NAME"
```

Check the `tags` array in the response for lifecycle tag entries.

## NetBox Version Compatibility

| NetBox Version | Status | Notes |
|----------------|--------|-------|
| 3.0.x | [OK] Supported | Minimum tested version |
| 3.1.x - 3.7.x | [OK] Supported | Fully compatible |
| 4.0.x+ | [WARNING] Untested | Should work; API breaking changes possible |
| < 3.0 | [X] Unsupported | Custom field API may differ |

## Troubleshooting

### Tags not appearing on devices

**Cause**: `nb_auto_create_refs` is set to `false`, preventing automatic tag creation.

**Solution**: Set `nb_auto_create_refs: true` in your playbook or role vars.

### Wrong lifecycle tag applied

**Cause**: `nb_lifecycle_force_overwrite` is set to `true`, forcing discovered tag application.

**Solution**:
- Set `nb_lifecycle_force_overwrite: false` to preserve existing lifecycle tags
- Manually update device tags in NetBox UI if override was accidental

### Tags created but wrong colors

**Cause**: Tag was manually created before role ran, or color values are incorrect.

**Solution**:
1. Navigate to **Customization > Tags** in NetBox
2. Edit each lifecycle tag
3. Set colors according to `nb_lifecycle_tag_colors` values (hex without `#`)
4. Save changes

### Cannot filter by lifecycle tags in NetBox

**Cause**: Tag filtering requires NetBox UI familiarity.

**Solution**:
- In device list view, look for tag badges on each device
- Click any lifecycle tag badge to filter devices by that tag
- Use Advanced Search with `tag=lifecycle:discovered` syntax
