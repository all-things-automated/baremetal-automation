# Kea DHCP Database Backend - Architecture & Deployment Plan

## Overview

This document outlines the database backend strategy for Kea DHCP static host reservations, supporting multi-site deployment with high availability and redundancy requirements.

---

## Requirements Analysis

### Functional Requirements
- Store Kea host reservations (MAC → IP mappings)
- Support Kea `host_cmds` API operations (add/delete/update)
- Persist across Kea service restarts
- Support queries during DHCP lease allocation (performance critical)
- Track reservation history/audit trail (optional but recommended)

### Non-Functional Requirements
- **High Availability**: Database failure should not bring down DHCP
- **Multi-Site**: Support 5 sites (us1, us2, us3, us4, dv)
- **Performance**: Sub-millisecond queries during DHCP operations
- **Backup/Recovery**: Daily backups, point-in-time recovery
- **Monitoring**: Health checks, replication lag alerts
- **Security**: Encrypted connections, least-privilege access

### Scale Estimates
- **Sites**: 5 active sites
- **Devices per site**: ~200-500 BMCs per site (estimate)
- **Total reservations**: ~2,500 max
- **Growth**: Moderate (new hardware purchases)
- **Query rate**: Low (only on DHCP lease allocation/renewal)

---

## Database Technology Comparison

### Option 1: PostgreSQL (RECOMMENDED)

**Pros:**
- [OK] Kea officially supports PostgreSQL (well-tested)
- [OK] Excellent replication (streaming, logical)
- [OK] Strong ACID guarantees
- [OK] Rich ecosystem (Patroni for HA, pgBackRest for backups)
- [OK] Better for write-heavy workloads
- [OK] Advanced features (JSONB, full-text search for future needs)
- [OK] Active community, frequent updates

**Cons:**
- [X] Slightly more complex initial setup than MySQL
- [X] Requires PostgreSQL expertise

**Recommended for:** Production environments requiring robust HA

### Option 2: MySQL/MariaDB

**Pros:**
- [OK] Kea officially supports MySQL
- [OK] Simpler replication setup (master-slave)
- [OK] Galera Cluster for multi-master (MariaDB)
- [OK] Familiar to many sysadmins
- [OK] Good performance for read-heavy workloads

**Cons:**
- [X] Replication can be more fragile
- [X] Galera adds complexity
- [X] Less robust for write conflicts in multi-master

**Recommended for:** Simpler environments, existing MySQL infrastructure

### Option 3: File-Based Backend (NOT RECOMMENDED)

**Pros:**
- [OK] Zero database dependencies
- [OK] Simple configuration

**Cons:**
- [X] No high availability
- [X] No replication
- [X] Single point of failure
- [X] Difficult to manage at scale

**Verdict:** Only for lab/testing, not production

---

## Recommended Architecture: PostgreSQL with Streaming Replication

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRODUCTION ARCHITECTURE                    │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│  Site: US3           │
│  Kea DHCP Server     │
│  (us3-sprmcr-l01)    │
├──────────────────────┤
│  Connection Pool:    │
│  - Primary: Write    │
│  - Standby: Read     │
│  - Failover: Auto    │
└─────────┬────────────┘
          │
          |
┌─────────────────────────────────────────┐
│         PostgreSQL Cluster              │
├─────────────────────────────────────────┤
│  Primary (Master)                       │
│  - kea-db-primary.us3.example.com      │
│  - Handles all writes                   │
│  - Streaming replication to standby    │
└────────┬────────────────────────────────┘
         │
         │ Async Streaming Replication
         |
┌─────────────────────────────────────────┐
│  Standby (Hot Standby)                  │
│  - kea-db-standby.us3.example.com      │
│  - Read-only queries (optional)         │
│  - Auto-promotes on primary failure     │
└─────────────────────────────────────────┘

Managed by: Patroni (HA automation)
Load Balancer: HAProxy or PgBouncer
Backup: pgBackRest (daily + WAL archiving)
Monitoring: pgMonitor + Prometheus
```

### Per-Site vs Centralized Decision

**Option A: Per-Site Database (RECOMMENDED)**
```
us3-kea → us3-postgres (primary + standby)
us1-kea → us1-postgres (primary + standby)
us2-kea → us2-postgres (primary + standby)
dv-kea  → dv-postgres (primary + standby)
```

**Pros:**
- [OK] Site isolation (database failure affects only one site)
- [OK] Better performance (local queries)
- [OK] Simpler network topology
- [OK] Independent maintenance windows

**Cons:**
- [X] More infrastructure to manage (5 database clusters)
- [X] Reservation data not centrally visible

**Option B: Centralized Database**
```
All Kea servers → Single PostgreSQL cluster (3-node)
```

**Pros:**
- [OK] Centralized management
- [OK] Unified view of all reservations
- [OK] Fewer database instances

**Cons:**
- [X] Single point of failure (affects all sites)
- [X] Network latency for remote sites
- [X] Higher load concentration

**DECISION: Per-Site Database**
- Prioritize site isolation and reliability
- DHCP is critical infrastructure, must not fail
- Cross-site replication can be added later if needed

---

## High Availability Strategy

### Patroni + PostgreSQL Streaming Replication

**Components:**
- **Patroni**: Automated failover and cluster management
- **etcd/Consul**: Distributed consensus for leader election
- **HAProxy/PgBouncer**: Connection pooling and routing

**Topology per site:**
```
┌─────────────────────────────────┐
│  kea-db-01 (Primary)            │
│  PostgreSQL 15.x                │
│  Patroni managed                │
└────────────┬────────────────────┘
             │
             ├── Sync Replication
             │
┌────────────|────────────────────┐
│  kea-db-02 (Standby)            │
│  PostgreSQL 15.x (read-only)    │
│  Patroni managed                │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  etcd cluster (3 nodes)         │
│  - Leader election              │
│  - Configuration store          │
└─────────────────────────────────┘

┌─────────────────────────────────┐
│  HAProxy (VIP)                  │
│  - Primary: port 5432 (write)   │
│  - Standby: port 5433 (read)    │
└─────────────────────────────────┘
```

**Failover Process:**
1. Primary node fails
2. Patroni detects failure (5-10 seconds)
3. Standby promoted to primary automatically
4. HAProxy updates routing
5. Kea reconnects to new primary (connection pool handles)
6. Total downtime: 10-15 seconds

**Recovery Time Objective (RTO):** < 30 seconds
**Recovery Point Objective (RPO):** 0 (synchronous replication)

---

## Deployment Architecture

### Hardware Requirements (Per Site)

**Database Node Specifications:**
- **CPU**: 4 cores (moderate load)
- **RAM**: 8GB minimum (4GB for PostgreSQL, 4GB for OS/cache)
- **Storage**: 50GB SSD (database + WAL archives)
- **Network**: 1Gbps (local network to Kea server)

**Can be Virtual Machines** (preferred for flexibility)

### Software Stack

```
OS:          Ubuntu 24.04 LTS
Database:    PostgreSQL 15.x
HA Manager:  Patroni 3.x
Consensus:   etcd 3.5.x (3-node cluster per site)
Pooler:      PgBouncer 1.21.x
Backup:      pgBackRest 2.49.x
Monitoring:  pg_exporter + Prometheus
```

---

## Ansible Deployment Strategy

### Roles to Create

```
ansible/
└── roles/
    ├── kea_database/
    │   ├── README.md
    │   ├── defaults/main.yml
    │   ├── tasks/
    │   │   ├── main.yml
    │   │   ├── install_postgresql.yml
    │   │   ├── configure_postgresql.yml
    │   │   ├── install_patroni.yml
    │   │   ├── configure_patroni.yml
    │   │   ├── install_etcd.yml
    │   │   ├── configure_etcd.yml
    │   │   ├── install_pgbouncer.yml
    │   │   ├── configure_pgbouncer.yml
    │   │   ├── create_kea_database.yml
    │   │   ├── configure_backups.yml
    │   │   └── configure_monitoring.yml
    │   ├── templates/
    │   │   ├── postgresql.conf.j2
    │   │   ├── patroni.yml.j2
    │   │   ├── etcd.conf.j2
    │   │   ├── pgbouncer.ini.j2
    │   │   └── kea_schema.sql.j2
    │   ├── files/
    │   │   └── kea_postgres_schema.sql
    │   └── handlers/main.yml
    │
    └── kea_deploy/  (existing - UPDATE)
        └── tasks/
            └── configure_database.yml  (NEW)
```

### Playbook Structure

```yaml
# playbooks/kea_database_deploy.yml
---
- name: Deploy Kea PostgreSQL Database Cluster
  hosts: kea_db_servers
  become: true
  
  vars:
    postgres_version: "15"
    patroni_version: "3.2.1"
    etcd_version: "3.5.11"
    kea_db_name: "kea"
    kea_db_user: "kea"
    kea_db_password: "{{ vault_kea_db_password }}"
    
  roles:
    - kea_database

# Inventory structure
# inventory/us3.yml
kea_db_servers:
  hosts:
    us3-kea-db-01:
      ansible_host: 172.30.19.10
      patroni_role: master
      patroni_priority: 100
    us3-kea-db-02:
      ansible_host: 172.30.19.11
      patroni_role: replica
      patroni_priority: 90
  vars:
    site: us3
    postgres_listen_address: "172.30.19.0/24"
    etcd_cluster:
      - 172.30.19.10
      - 172.30.19.11
      - 172.30.19.12
```

### Deployment Phases

**Phase 1: Initial Setup (Development)**
- Single PostgreSQL instance (no HA)
- Manual backups
- Basic monitoring
- Timeline: 1-2 days

**Phase 2: Production Preparation**
- Patroni + Streaming Replication
- Automated backups (pgBackRest)
- HAProxy/PgBouncer
- Monitoring integration
- Timeline: 1 week

**Phase 3: Production Rollout**
- Deploy to US3 (pilot)
- Monitor for 2 weeks
- Deploy to remaining sites
- Timeline: 1 month

---

## Database Schema (Kea Tables)

Kea automatically creates these tables when you run `kea-admin db-init`:

```sql
-- Core Kea tables (created by kea-admin)
hosts                 -- Static host reservations
dhcp4_options         -- DHCP options per reservation
lease4                -- Active DHCP leases
lease4_stat           -- Lease statistics
logs                  -- Kea daemon logs

-- Example reservation
INSERT INTO hosts (
    dhcp_identifier,
    dhcp_identifier_type,
    dhcp4_subnet_id,
    ipv4_address,
    hostname
) VALUES (
    decode('c4cbe1d612ae', 'hex'),  -- MAC address
    0,                               -- Identifier type (0=MAC)
    1,                               -- Subnet ID
    '172.30.19.42',                 -- IP address
    'us3-cab10-ru17-idrac'          -- Hostname
);
```

**Our additions (optional):**
```sql
-- Reservation audit trail
CREATE TABLE reservation_audit (
    id SERIAL PRIMARY KEY,
    mac_address TEXT NOT NULL,
    ip_address INET NOT NULL,
    hostname TEXT,
    subnet_id INTEGER,
    action TEXT,  -- 'CREATE', 'UPDATE', 'DELETE'
    created_by TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Reservation metadata (for our automation)
CREATE TABLE reservation_metadata (
    mac_address TEXT PRIMARY KEY,
    site TEXT,
    cabinet_id TEXT,
    rack_unit TEXT,
    bmc_type TEXT,
    discovery_timestamp TIMESTAMP,
    netbox_device_id INTEGER,
    notes TEXT
);
```

---

## Backup Strategy

### pgBackRest Configuration

**Backup Types:**
- **Full**: Weekly (Sunday 2 AM)
- **Differential**: Daily (2 AM)
- **Incremental**: Every 6 hours
- **WAL Archiving**: Continuous (real-time)

**Retention:**
- Full backups: 4 weeks
- Differential backups: 2 weeks
- Incremental backups: 1 week
- WAL archives: 2 weeks

**Storage:**
- Primary: Local storage on DB server
- Secondary: Remote backup server (rsync/NFS)
- Cloud: Optional (AWS S3/Azure Blob)

**Recovery Testing:**
- Monthly test restore to separate VM
- Document restore procedures
- Automate with Ansible playbook

---

## Monitoring & Alerting

### Metrics to Track

**Database Health:**
- PostgreSQL up/down
- Replication lag (critical if > 10 seconds)
- Connection pool saturation
- Disk space usage
- Query performance (slow queries)

**Patroni Health:**
- Leader/replica status
- Failover events
- Configuration drift

**Kea-Specific:**
- Reservation count per subnet
- Failed reservation operations
- Database connection errors in Kea logs

### Alert Thresholds

**Critical (page immediately):**
- PostgreSQL down on primary
- Replication lag > 60 seconds
- Disk space < 10%
- Patroni failover event

**Warning (email/Slack):**
- Replication lag > 10 seconds
- Connection pool > 80% utilized
- Slow queries (> 1 second)
- Disk space < 20%

---

## Security Considerations

### Network Security
- **Firewall**: Restrict PostgreSQL (5432) to Kea servers only
- **SSL/TLS**: Enforce encrypted connections (required)
- **VPN/Private Network**: Database on management VLAN

### Authentication
- **Kea User**: Limited permissions (SELECT, INSERT, UPDATE, DELETE on hosts table)
- **Admin User**: Full permissions (backups, maintenance)
- **Monitoring User**: Read-only access (pg_stat_* views)

### Password Management
- Store in Ansible Vault
- Rotate quarterly
- Use strong passwords (20+ characters)

### Audit Logging
- Enable PostgreSQL audit logs (pgaudit extension)
- Log all DDL/DML operations
- Retain logs for 90 days

---

## Cost & Resource Estimates

### Per-Site Infrastructure

**Option 1: Minimal HA (Recommended Start)**
- 2 VMs: Primary + Standby
- 4 cores, 8GB RAM, 50GB SSD each
- Cost: ~$100/month per site (cloud) or 2 physical hosts

**Option 2: Full HA with etcd**
- 4 VMs: Primary + Standby + 2 etcd nodes
- Cost: ~$150/month per site (cloud)

**Total for 5 sites (Option 1):**
- 10 VMs
- ~$500/month (cloud) or 10 physical hosts

### Labor Estimates

**Initial Setup:**
- Ansible role development: 2 weeks
- Testing and validation: 1 week
- Documentation: 3 days
- Total: 3-4 weeks

**Ongoing Maintenance:**
- Monitoring: 2 hours/week
- Backups/restores: 1 hour/week
- Updates: 4 hours/month
- Total: ~4 hours/week average

---

## Migration Path from Current Setup

### Current State (Assumed)
- Kea uses file-based reservations (config file)
- Manual edits + service restarts for changes
- No centralized management

### Migration Steps

**Step 1: Parallel Deployment (Lab)**
- Deploy PostgreSQL in lab (172.30.19.3)
- Configure Kea to use database (dual-mode testing)
- Validate reservation CRUD operations
- Timeline: 1 week

**Step 2: Migrate Existing Reservations**
- Export current reservations from config
- Convert to SQL INSERT statements
- Load into database
- Validate all reservations work
- Timeline: 2 days

**Step 3: Production Deployment (US3 Pilot)**
- Deploy PostgreSQL cluster in US3
- Switch us3-sprmcr-l01 to database backend
- Monitor for 2 weeks
- Timeline: 3 weeks (including monitoring)

**Step 4: Multi-Site Rollout**
- Deploy to US1, US2, DV sequentially
- 1 week per site (including monitoring)
- Timeline: 1 month

---

## Decision Matrix

| Factor | PostgreSQL | MySQL | File-Based |
|--------|-----------|-------|------------|
| HA Support | ***** | **** | * |
| Performance | ***** | **** | ***** |
| Complexity | *** | **** | ***** |
| Kea Support | ***** | ***** | ***** |
| Backup/Recovery | ***** | **** | *** |
| Multi-Site | ***** | **** | * |
| Audit Trail | ***** | **** | * |

**RECOMMENDATION: PostgreSQL with Patroni**

---

## Next Steps

1. **Review & Approval** (This week)
   - Review architecture with team
   - Get budget approval for infrastructure
   - Identify database administrators

2. **Lab Deployment** (Week 1-2)
   - Deploy single PostgreSQL instance in lab
   - Test Kea integration
   - Validate reservation operations

3. **Ansible Role Development** (Week 2-4)
   - Create `kea_database` Ansible role
   - Test in lab environment
   - Document deployment procedures

4. **Production Pilot - US3** (Week 5-7)
   - Deploy PostgreSQL cluster in US3
   - Switch Kea to database backend
   - Monitor for stability

5. **Multi-Site Rollout** (Week 8-12)
   - Deploy to US1, US2, US4, DV
   - Validate each site before proceeding
   - Update operational procedures

---

## Open Questions

1. **Existing Infrastructure**: Do you already have PostgreSQL or MySQL in your environment?
2. **Database Administrators**: Who will manage the database clusters?
3. **Backup Storage**: Where should backups be stored? (NAS, cloud, tape?)
4. **Network Topology**: Are database servers on same subnet as Kea servers?
5. **etcd Placement**: Run etcd on database nodes or separate VMs?
6. **Monitoring Integration**: Existing Prometheus/Grafana setup to integrate with?
7. **Budget**: Any budget constraints for additional VMs?

---

## References

- [Kea Administrator Reference Manual - Database Backend](https://kea.readthedocs.io/en/latest/arm/admin.html#database-backends)
- [Patroni Documentation](https://patroni.readthedocs.io/)
- [PostgreSQL High Availability](https://www.postgresql.org/docs/current/high-availability.html)
- [pgBackRest Documentation](https://pgbackrest.org/)
