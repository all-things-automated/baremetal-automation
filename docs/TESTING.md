# Redfish Mockup Strategy

This document describes how Redfish mockup servers fit into the **Bare-Metal Lifecycle Automation** project and how to use them for development, testing, and onboarding new hardware platforms.

---

## Overview

A **Redfish mockup server** is a generic HTTP server that exposes a static Redfish tree (JSON files) and behaves like a “virtual BMC.”

In this project, the mockup server is used as a **virtual lab of BMCs** that you can hit with the *same* automation that will later target real iDRAC/iLO/BMC endpoints.

---

## BMC Test Targets

The following BMC targets have been tested or identified for testing:

### Currently Active

- **172.30.19.42** - Dell iDRAC (working)
- **172.30.19.48** - Dell iDRAC (working)

### Pending Investigation

- **172.30.19.49** - HP iLO
  - Status: API documentation research needed
  - Note: HP iLO uses different Redfish API patterns

- **172.30.19.78** - Non-standard Redfish implementation
  - Status: Schema differs from Dell iDRAC Redfish schema
  - Plan: DMTF MockUp Server will be used for testing this variant

---

## Why Use Redfish Mockups?

### 1. Safe, Offline Development

- Develop and debug the **probe** and **normalization** roles without touching real hardware.
- No risk of power operations or configuration changes to production/staging systems.
- No need for VPN or access to a lab.

### 2. Repeatable, Deterministic Tests

- Real hardware is dynamic (power state, firmware level, drive layout, etc.).
- Mockups serve **static JSON**, so tests see the same structure and values every run.
- Perfect for regression tests and schema validation.

### 3. Multi-OEM Compatibility

- Each OEM/platform has its own quirks (BIOS attributes, storage layout, NIC naming, OEM sections, actions).
- Using **multiple mockups** (Dell, HPE, Supermicro, Lenovo, etc.) lets us:
  - Detect vendor-specific breakage early.
  - Validate that normalization and policy code handles differences gracefully.

---

## How It Fits into the Bare-Metal Lifecycle Architecture

### Production Flow (Real Hardware)

High-level real-world flow:

1. **DHCP lease** from BMC network (Kea).
2. **Kea hook** triggers Spacelift/CI with:
   - `bmc_ip`
   - cabinet/slot metadata, etc.
3. Spacelift runs **probe** playbook against:
   - `https://<bmc_ip>/redfish/v1`
4. Probe:
   - Verifies Redfish health.
   - Harvests Redfish data (Systems, Chassis, Managers, Storage, NICs, BIOS, Boot, etc.).
   - Produces a **normalized YAML facts file**.
5. Downstream lifecycle jobs use that YAML + **intended state** (CSV) to:
   - Enforce BIOS/NIC/RAID/firmware policy.
   - Attach OS installer media and trigger OS install.
   - Update DNS (including `os_hostname-mgmt.domain.com` CNAMEs), CMDB, etc.

### Test/Dev Flow (Mock Hardware)

For dev/CI, the flow is identical except:

- There is **no DHCP/Kea hook**. CI or a developer manually triggers the pipeline.
- The playbooks target a **Redfish mockup server** instead of a real BMC:

  ```yaml
  redfish_base_url: "{{ lookup('env', 'REDFISH_BASE_URL') | default('https://' + bmc_ip + '/redfish/v1') }}"
