# Kea Static Leases Automation (Control Agent + host_cmds)

## What we’re trying to accomplish

We want devices to **use DHCP** normally, but still keep a **consistent (static) IP** assigned by the DHCP server.

To do that, we will automatically convert selected dynamic leases into **Kea host reservations** (“static leases”) by calling Kea’s **Control Agent REST API**. This lets us create/update reservations **without editing config files or restarting Kea**.

You already have **event-driven detection of new leases**. We’ll use that event to trigger the reservation workflow.

---

## High-level approach

### Core idea
1. A new device gets a lease via DHCP.
2. Your existing event detection sees the new lease.
3. Automation decides whether the device should be “pinned” (static from DHCP).
4. Automation calls Kea’s API to add a host reservation for that device.
5. On renew/rebind, the device keeps the same IP because Kea now has a reservation.

---

## Components involved

- **Kea DHCP4**  
  Issues leases. We enable a control socket so it can accept management commands from Control Agent.

- **Kea Control Agent**  
  Exposes a **REST endpoint** used by automation to send management commands.

- **host_cmds hook library**  
  Enables reservation management commands (e.g., `reservation-add`) while Kea is running.

- **Hosts database (PostgreSQL/MySQL)**  
  Stores reservations so they persist and can be managed via API (no config file edits).

- **Lease event handler (your automation)**  
  Your existing mechanism that detects new leases and triggers actions.

---

## Setup summary (what must be configured)

1. **Give each Kea subnet a stable `id`**  
   The reservation API needs `subnet-id` to know where to place the reservation.

2. **Enable a Kea DHCP4 control socket**  
   Control Agent uses this socket to issue commands to DHCP4.

3. **Configure a Hosts DB backend** (PostgreSQL or MySQL)  
   Reservations are stored in the DB for durability and centralized management.

4. **Load the `host_cmds` hook library** in Kea DHCP4  
   This provides `reservation-add`, `reservation-del`, `reservation-get`, etc.

5. **Configure and run Kea Control Agent**
   - Bind to `127.0.0.1` or a dedicated management interface
   - Enable authentication (basic auth is fine for lab; restrict network access)

---

## Automation workflow (event-driven)

### Inputs (from the lease event)
- Subnet (or `subnet-id`)
- Device identifier (usually MAC / `hw-address`)
- Leased IP
- Optional: hostname, vendor, tags, VLAN, etc.

### Decision step (your policy)
Examples:
- Only auto-pin devices in specific subnets (e.g., mgmt VLAN)
- Only auto-pin allowlisted OUIs or known device types
- Only auto-pin devices that meet a naming rule
- Require manual approval for unknown devices

### Action (API call)
Automation calls Control Agent with:
- `command`: `reservation-add`
- `reservation`: `{ subnet-id, hw-address, ip-address, hostname }`
- target: write to the **database** so it persists

### Output
- A stored reservation for that device, making its IP “static via DHCP”.

---

## Operational notes

- A reservation typically becomes authoritative on **renew/rebind** (or immediately if the same IP is reused).
- Keep reserved addresses **outside dynamic pools** (recommended) to avoid collisions.
- Log everything (device identifier, IP, subnet-id, request/response) for auditability.

---

## Security checklist (minimum)

- Bind Control Agent to **localhost** unless there is a strong reason not to.
- Require authentication for the Control Agent API.
- If remote access is needed, restrict by firewall and/or place behind a trusted reverse proxy/TLS solution.
- Use a dedicated “automation” credential (don’t reuse admin creds).

---

## What success looks like

- New devices still come online via DHCP normally.
- Devices that meet the automation criteria get a reservation created automatically.
- Those devices consistently receive the same IP from Kea going forward.
- All changes are logged and repeatable without manual config edits or service restarts.
