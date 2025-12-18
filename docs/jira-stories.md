# Jira Stories - Bare-Metal Automation Project

## Epic: Bare-Metal Discovery and Registration Automation

**Epic Description**: Automate the discovery of bare-metal servers via Redfish BMC APIs and register discovered hardware into NetBox DCIM. Integrate with Kea DHCP for automated lease-triggered discovery workflows.

**Business Value**: Eliminate manual server inventory processes, reduce time-to-production for new hardware, ensure accurate DCIM records, and enable infrastructure-as-code practices for bare-metal environments.

---

## Sprint 1: Python Lease Monitoring Foundation

### Story 1: Optimize Lease Metadata Structure

**Story Points**: 3

**Description**:
As a DevOps engineer, I need the Kea lease monitor to produce clean, non-redundant YAML output so that Ansible inventories are easier to read and maintain.

**Background**:
The current implementation includes IP addresses in both the `bmc_targets` list and the `metadata.leases` section, creating unnecessary duplication. IP addresses should only exist in the inventory hosts section.

**Acceptance Criteria**:
- [ ] Remove IP addresses from `metadata.leases` section in kea_lease_monitor.py
- [ ] IP addresses remain in `bmc_targets` list for Ansible inventory compatibility
- [ ] Each lease in metadata contains only: mac, hostname, manufacturer
- [ ] Existing discovery inventories continue to work without modification
- [ ] YAML output passes yamllint validation
- [ ] No breaking changes to downstream Ansible playbooks

**Technical Notes**:
- Modify `_parse_lease_line()` method to exclude IP from lease details dict
- Update both migration path and new lease processing logic
- Maintain backward compatibility with existing artifacts

**Testing**:
- Unit tests pass for lease parsing
- Integration test with live Kea DHCP lease file
- Validate YAML structure with multiple leases
- Test Ansible inventory consumption

---

### Story 2: Implement Rack Unit Sorting for Inventory Ordering

**Story Points**: 5

**Description**:
As a datacenter operator, I need discovery inventories to list servers in rack unit order so that I can quickly identify physical server locations and maintain logical organization.

**Background**:
Current implementation lists servers in arbitrary order. Physical rack layout requires servers sorted by rack unit (RU) for operational efficiency and troubleshooting.

**Acceptance Criteria**:
- [ ] Extract rack unit number from BMC hostnames (e.g., us3-cab10-ru17-idrac → 17)
- [ ] Handle multi-RU devices correctly (us3-cab10-ru17-18-idrac → sort by highest RU: 17)
- [ ] Sort hosts in ascending rack unit order within cabinet inventories
- [ ] Gracefully handle hostnames without RU information (append at end)
- [ ] Maintain site and cabinet grouping in inventory structure
- [ ] Documentation updated with hostname format requirements

**Technical Notes**:
- Implement `_extract_rack_unit()` helper method
- Use regex pattern: `ru(\d+)(?:-(\d+))?`
- Sort hosts before writing inventory YAML
- Handle edge cases: missing RU, invalid formats, non-standard naming

**Testing**:
- Unit tests for RU extraction with various hostname formats
- Test multi-RU device sorting
- Verify sort order in generated inventories
- Test with production hostname patterns from all sites

---

### Story 3: Add BMC DNS Name Monitoring Service

**Story Points**: 8

**Description**:
As a system administrator, I need automated monitoring of BMC DNS registrations so that discovery workflows trigger immediately when new servers are powered on and receive DHCP leases.

**Background**:
Current workflow requires manual triggering of discovery after BMCs receive DHCP leases. Automating DNS monitoring enables lights-out provisioning.

**Acceptance Criteria**:
- [ ] Monitor DNS for BMC hostname registrations in discovery subnets
- [ ] Extract site, cabinet, and rack unit from BMC hostnames
- [ ] Trigger Ansible discovery playbook when new BMC detected
- [ ] Log all discovery triggers with timestamp and BMC details
- [ ] Handle DNS query failures gracefully with retry logic
- [ ] Integrate with existing kea_lease_monitor workflow
- [ ] Systemd service configuration for automatic startup
- [ ] Service restart on failure with exponential backoff

**Technical Notes**:
- Create `bmc_dns_watcher.py` script
- Use dnspython library for DNS queries
- Poll interval: configurable (default 60 seconds)
- Maintain state file to track processed BMCs
- Support both forward and reverse DNS lookups
- Ansible playbook invocation with proper error handling

**Testing**:
- Unit tests for hostname parsing
- Integration test with test DNS server
- Mock Ansible playbook execution
- Test service restart behavior
- Validate state file handling across restarts

---

### Story 4: Create Infrastructure Health Analyzer

**Story Points**: 5

**Description**:
As a network engineer, I need visibility into Kea DHCP infrastructure health so that I can proactively address capacity and performance issues before they impact operations.

**Background**:
No current tooling exists to analyze Kea lease pool utilization, identify configuration issues, or monitor performance metrics.

**Acceptance Criteria**:
- [ ] Report lease pool utilization percentage per subnet
- [ ] Identify potential configuration issues (pool too small, lease lifetime)
- [ ] Monitor lease file growth rate and performance
- [ ] Generate alerts when utilization exceeds thresholds (80%, 90%, 95%)
- [ ] Provide recommendations for pool expansion
- [ ] Output in JSON format for integration with monitoring systems
- [ ] Command-line interface with multiple report formats (text, JSON, CSV)

**Technical Notes**:
- Create `kea_infrastructure_analyzer.py` script
- Parse Kea lease files and configuration
- Calculate utilization metrics
- Support multiple subnet analysis
- Configurable alert thresholds

**Testing**:
- Unit tests for utilization calculations
- Test with various lease file sizes
- Validate threshold alerting logic
- Test output format generation

---

## Sprint 2: Kea DHCP Ansible Role Development

### Story 5: Create Kea Deployment Ansible Role Foundation

**Story Points**: 13

**Description**:
As a DevOps engineer, I need a comprehensive Ansible role to deploy Kea DHCP servers so that I can consistently provision DHCP infrastructure across multiple sites using infrastructure-as-code practices.

**Background**:
Manual Kea DHCP server setup is error-prone and inconsistent. An Ansible role enables repeatable, tested deployments with proper configuration management.

**Acceptance Criteria**:
- [ ] Role installs Kea DHCP packages (kea-dhcp4-server, kea-ctrl-agent, kea-admin)
- [ ] Creates kea service user and group with proper permissions
- [ ] Establishes directory structure (/opt/kea, /var/lib/kea/discovery, /var/log/kea)
- [ ] Deploys Python monitoring scripts from controller to target
- [ ] Renders Kea DHCP4 configuration from Jinja2 template
- [ ] Configures hook library for lease event processing
- [ ] Creates custom systemd services (kea-lease-monitor, bmc-dns-watcher)
- [ ] Implements validation tasks to verify deployment
- [ ] All tasks are idempotent and safe to re-run
- [ ] Comprehensive README with usage examples

**Technical Notes**:
- Role structure: defaults/, vars/, tasks/, templates/, handlers/, meta/
- Support both physical and virtual environments
- Use environment variables for sensitive data (BMC credentials)
- Tag tasks for selective execution (packages, config, services)
- Python virtual environment for script dependencies

**Testing**:
- Test on Ubuntu 24.04 LTS
- Validate idempotency (run twice, no changes on second run)
- Test with minimal and comprehensive variable sets
- Verify service startup and health

**Definition of Done**:
- Role deployed successfully to test environment (172.30.19.3)
- All services running and healthy
- Discovery inventories generating correctly
- Documentation complete with examples

---

### Story 6: Implement State-Based Lifecycle Management

**Story Points**: 8

**Description**:
As a system administrator, I need the ability to cleanly remove Kea deployments so that I can decommission servers, roll back failed deployments, or migrate DHCP services without leaving orphaned configurations.

**Background**:
Current deployment is one-way only. Production requires ability to cleanly remove all components while optionally preserving packages and service accounts.

**Acceptance Criteria**:
- [ ] Implement `kea_state` variable with values: "present" or "absent"
- [ ] Create comprehensive removal task file (remove.yml)
- [ ] Stop and disable all Kea-related services (dhcp4, lease-monitor, dns-watcher)
- [ ] Remove custom systemd service files
- [ ] Clean up configuration files (/etc/kea/)
- [ ] Remove application directories (/opt/kea, /var/lib/kea/discovery)
- [ ] Optional package removal (kea_remove_packages flag, default: false)
- [ ] Optional user/group removal (kea_remove_user flag, default: false)
- [ ] Display removal summary with actions taken
- [ ] Role entry point routes to install or remove based on state

**Technical Notes**:
- Conservative defaults: preserve packages and users unless explicitly requested
- Separate package list for removal (exclude Python system packages)
- Use `ignore_errors: true` for service operations (may not exist)
- Trigger systemd daemon-reload after service file removal
- End playbook execution after removal with `meta: end_play`

**Testing**:
- Test basic removal (default flags)
- Test full removal with all flags enabled
- Verify no orphaned files or services
- Test reinstall after removal

---

### Story 7: Fix Docker Container Path Resolution

**Story Points**: 3

**Description**:
As a developer, I need Python scripts to deploy correctly from Dockerized Ansible controller so that the role works in both container and native environments.

**Background**:
Current implementation uses incorrect relative paths from `playbook_dir`, causing file-not-found errors when running from Docker container with `/baremetal` mount.

**Acceptance Criteria**:
- [ ] Fix all Python script source paths in python.yml task file
- [ ] Change from `{{ playbook_dir }}/../python/` to `{{ playbook_dir }}/../../python/`
- [ ] Remove incorrect `remote_src: true` parameter (files come from controller)
- [ ] Scripts deploy successfully from Docker Ansible controller
- [ ] Scripts deploy successfully from native Ansible installation
- [ ] Document path resolution logic in role README

**Technical Notes**:
- Docker mount: `/baremetal` → `c:\Users\ETWilson\work\Repositories\baremetal`
- Playbook location: `/baremetal/ansible/playbooks/`
- Python source: `/baremetal/python/src/baremetal/`
- Required navigation: `../../` (up two levels from playbooks/)

**Testing**:
- Deploy from Docker controller to test target
- Verify all 4 files copy correctly (kea_lease_monitor.py, bmc_dns_watcher.py, __init__.py, requirements.txt)
- Check file permissions and ownership on target

---

### Story 8: Add Template Safety for Optional Variables

**Story Points**: 2

**Description**:
As a DevOps engineer, I need Kea DHCP configuration templates to handle optional variables safely so that deployments don't fail when advanced features are not configured.

**Background**:
Current template causes `AnsibleUndefinedVariable` errors when optional variables like `kea_custom_hooks` and `kea_additional_options` are not defined.

**Acceptance Criteria**:
- [ ] Add "is defined" checks for all optional template variables
- [ ] Use pattern: `{% if variable is defined and variable %}`
- [ ] Apply to kea_custom_hooks conditional block
- [ ] Apply to kea_additional_options conditional block
- [ ] Template renders successfully with minimal variable set
- [ ] Template renders successfully with all optional variables
- [ ] No AnsibleUndefinedVariable errors

**Technical Notes**:
- File: `templates/kea-dhcp4.conf.j2`
- Short-circuit evaluation prevents accessing undefined variables
- Maintain JSON syntax validity in rendered output

**Testing**:
- Test with defaults only (no optional variables)
- Test with each optional variable individually
- Test with all optional variables
- Validate JSON syntax of rendered config

---

### Story 9: Disable Unwanted Kea System Services

**Story Points**: 3

**Description**:
As a system administrator, I need only the required Kea services running so that system resources aren't wasted and deployment isn't interfered with by unnecessary daemons.

**Background**:
Ubuntu Kea packages automatically enable kea-dhcp-ddns, kea-dhcp6-server, and kea-ctrl-agent services. Only kea-dhcp4-server is needed for this use case.

**Acceptance Criteria**:
- [ ] Stop and disable kea-dhcp-ddns service after installation
- [ ] Stop and disable kea-dhcp6-server service after installation
- [ ] Stop and disable kea-ctrl-agent service after installation
- [ ] Only kea-dhcp4-server remains enabled and running
- [ ] Services remain disabled after system reboot
- [ ] Removal tasks handle all system services

**Technical Notes**:
- Add task in install.yml after package installation
- Include all system services in remove.yml service list
- Use `ignore_errors: true` (services may not exist on all systems)

**Testing**:
- Verify service states with `systemctl is-enabled`
- Confirm only dhcp4-server running with `systemctl list-units`
- Test after system reboot
- Validate removal includes all services

---

### Story 10: Standardize Variable Naming Across Role

**Story Points**: 2

**Description**:
As a developer, I need consistent variable naming throughout the role so that the code is maintainable and errors from undefined variables are eliminated.

**Background**:
Inconsistent use of `kea_discovery_dir` vs `kea_discovery_output_dir` causes undefined variable errors in removal tasks.

**Acceptance Criteria**:
- [ ] Use canonical variable name: `kea_discovery_output_dir` throughout role
- [ ] Update all task files to use consistent naming
- [ ] Update all template files to use consistent naming
- [ ] Define variable in defaults/main.yml as single source of truth
- [ ] Search entire role for any remaining inconsistencies
- [ ] Document variable in role README

**Technical Notes**:
- Canonical definition: `kea_discovery_output_dir: "/var/lib/kea/discovery"`
- Update locations: remove.yml (2 instances)
- Use grep to find all variable references before finalizing

**Testing**:
- Role deployment with default variables succeeds
- Removal tasks execute without undefined variable errors
- yamllint passes on all YAML files

---

## Sprint 3: Deployment Orchestration and Documentation

### Story 11: Create Production Deployment Playbooks

**Story Points**: 5

**Description**:
As a DevOps engineer, I need production-ready playbooks to deploy and manage Kea DHCP servers so that I can execute deployments consistently across environments.

**Acceptance Criteria**:
- [ ] Create kea_deploy.yml playbook for standard deployments
- [ ] Create kea_deploy_example.yml with comprehensive variable examples
- [ ] Create kea_remove.yml playbook for removal operations
- [ ] Use environment variables for credentials (BMC_USERNAME, BMC_PASSWORD)
- [ ] Include post-deployment validation tasks
- [ ] Include post-removal verification tasks
- [ ] Document usage with examples for each playbook
- [ ] Support multi-site deployment through inventory groups

**Technical Notes**:
- Target host group: kea_servers
- Gather facts: true (needed for validation)
- Become: true (requires root privileges)
- Tag playbooks for selective task execution

**Testing**:
- Deploy to test environment (172.30.19.3)
- Verify all services start correctly
- Test removal and validate cleanup
- Test with different variable combinations

---

### Story 12: Create Lab Inventory and Reference Configurations

**Story Points**: 3

**Description**:
As a developer, I need lab inventory and reference configurations so that I can quickly test deployments and have examples of proper configuration structure.

**Acceptance Criteria**:
- [ ] Create lab-kea-inv.yml inventory for development testing
- [ ] Configure for 172.30.19.3 test server
- [ ] Define subnet 172.30.19.0/24 with pool range 172.30.19.50-100
- [ ] Create reference kea-dhcp4.conf showing proper structure
- [ ] Create reference systemd service files for monitoring services
- [ ] Document inventory variables and their purposes
- [ ] Include connection settings (ansible_user, become method)

**Technical Notes**:
- Inventory location: ansible/inventory/lab-kea-inv.yml
- Reference configs location: kea_dhcp/, systemd/
- Use as templates for production inventories
- Document any lab-specific settings

**Testing**:
- Validate inventory syntax with ansible-inventory
- Test deployment to lab environment
- Verify reference configs are valid

---

### Story 13: Write Comprehensive Deployment Documentation

**Story Points**: 8

**Description**:
As a team member, I need comprehensive documentation covering architecture, deployment procedures, and troubleshooting so that I can understand, deploy, and maintain the Kea DHCP infrastructure.

**Acceptance Criteria**:
- [ ] Create DEPLOYMENT.md with step-by-step procedures
  - Prerequisites and requirements
  - Initial setup and configuration
  - Deployment execution steps
  - Post-deployment validation
  - Troubleshooting common issues
  - Production deployment checklist
- [ ] Create KEA_DEPLOY_QUICKREF.md for quick reference
  - Common commands
  - Configuration quick reference
  - Service management
  - File locations
- [ ] Update KEA.md with latest architecture details
  - Role structure and components
  - Lifecycle management
  - Service dependencies
  - Integration points
- [ ] Create KEA_DEPLOY_COMPLETION.md documenting implementation
  - Feature implementation status
  - Testing results
  - Known limitations
  - Future work roadmap
- [ ] Update .env.example with Kea-specific variables
- [ ] Update role README.md with comprehensive examples

**Technical Notes**:
- Use proper Markdown formatting
- Include code examples and command outputs
- Add architecture diagrams where helpful
- Link related documentation
- Follow project documentation standards

**Testing**:
- Peer review all documentation
- Validate all commands and examples work
- Test deployment following documentation exactly

---

## Sprint 4: Integration and Testing

### Story 14: Integrate DNS Watcher with Discovery Workflow

**Story Points**: 8

**Description**:
As a datacenter operator, I need the DNS watcher to automatically trigger discovery playbooks so that new servers are inventoried in NetBox immediately after powering on.

**Background**:
Complete end-to-end automation requires DNS monitoring to invoke Ansible discovery and NetBox registration without manual intervention.

**Acceptance Criteria**:
- [ ] DNS watcher detects new BMC registrations in real-time
- [ ] Ansible discovery playbook invoked with correct inventory
- [ ] Discovery artifacts generated with proper site/cabinet/RU metadata
- [ ] NetBox registration triggered after successful discovery
- [ ] Failed discovery attempts logged with error details
- [ ] Retry logic for transient failures (3 attempts with exponential backoff)
- [ ] State management prevents duplicate processing
- [ ] Metrics logged: discovery time, success rate, failure reasons

**Technical Notes**:
- Use subprocess to invoke ansible-playbook
- Pass dynamic inventory via extra-vars
- Capture stdout/stderr for logging
- Implement proper error handling and retry logic
- Track processed BMCs in state file

**Testing**:
- End-to-end test: DHCP lease → DNS registration → discovery → NetBox
- Test failure scenarios (Ansible errors, network issues)
- Validate retry logic with simulated failures
- Verify state file prevents duplicates

---

### Story 15: Multi-Site Production Deployment

**Story Points**: 13

**Description**:
As a network architect, I need Kea DHCP deployed to all datacenter sites so that bare-metal discovery automation is available organization-wide.

**Background**:
Currently deployed only to US3 site. Full automation requires deployment to US1, US2, DV, and US3 sites.

**Acceptance Criteria**:
- [ ] Deploy to US1 site Kea server
- [ ] Deploy to US2 site Kea server
- [ ] Deploy to US3 site Kea server (production validation)
- [ ] Deploy to DV site Kea server
- [ ] Each site configured with correct subnet ranges
- [ ] Each site generating site-specific discovery inventories
- [ ] All monitoring services running and healthy
- [ ] Cross-site inventory management validated
- [ ] Failover/HA considerations documented

**Technical Notes**:
- Site-specific variables in inventory
- Subnet ranges per site (coordinate with network team)
- Discovery output directories per site
- DNS server configuration per site
- Monitor resource utilization (CPU, memory, disk)

**Testing**:
- Deploy to each site sequentially
- Validate services on each site
- Test discovery workflow per site
- Monitor for 24 hours per site before next deployment
- Load testing with multiple concurrent leases

---

### Story 16: Implement OEM-Specific Discovery Enhancements

**Story Points**: 13

**Description**:
As a systems engineer, I need manufacturer-specific Redfish queries so that we capture all available hardware details for Dell, HP, and Supermicro servers.

**Background**:
Generic Redfish queries miss OEM-specific extensions. Each manufacturer provides additional data through proprietary endpoints.

**Acceptance Criteria**:
- [ ] Detect BMC manufacturer from Redfish response
- [ ] Implement Dell-specific queries (iDRAC extensions)
  - RAID controller details
  - Storage enclosure information
  - System event log
  - Lifecycle controller status
- [ ] Implement HP-specific queries (iLO extensions)
  - IML (Integrated Management Log)
  - Array controller details
  - Power supply details
- [ ] Implement Supermicro-specific queries
  - IPMI sensor data
  - FRU information
- [ ] Gracefully handle missing OEM extensions
- [ ] Update artifact template with OEM-specific data structure
- [ ] NetBox registration role handles OEM data

**Technical Notes**:
- Use community.general.redfish_info with OEM categories
- Conditional task execution based on manufacturer
- Maintain backward compatibility with existing artifacts
- Document OEM-specific data structures

**Testing**:
- Test with physical Dell server
- Test with physical HP server
- Test with physical Supermicro server
- Verify artifact structure for each OEM
- Test NetBox registration with OEM data

---

### Story 17: Implement High Availability for Kea DHCP

**Story Points**: 21

**Description**:
As a network architect, I need Kea DHCP deployed in high-availability configuration so that DHCP services remain available during server maintenance or failures.

**Background**:
Single Kea DHCP server per site creates single point of failure. Production requires HA configuration with lease database replication.

**Acceptance Criteria**:
- [ ] Design HA architecture (active-active or active-passive)
- [ ] Implement lease database replication between HA pairs
- [ ] Configure Kea HA hook library
- [ ] Implement health checking between HA peers
- [ ] Automatic failover on primary failure
- [ ] Load balancing for active-active configuration
- [ ] Monitoring and alerting for HA status
- [ ] Update Ansible role to support HA deployment
- [ ] Runbook for HA failover procedures
- [ ] Disaster recovery procedures

**Technical Notes**:
- Use Kea HA hook: libdhcp_ha.so
- Lease database: PostgreSQL or MySQL (not memfile)
- Network configuration: shared VLAN for HA communication
- Consider using virtual IP for DHCP service
- HAProxy or keepalived for IP failover

**Testing**:
- Test primary server failure scenario
- Test network partition (split-brain)
- Test lease synchronization
- Load testing with failover
- Verify monitoring alerts trigger correctly
- Disaster recovery drill

---

## Sprint 5: Monitoring and Operations

### Story 18: Implement Centralized Logging and Monitoring

**Story Points**: 8

**Description**:
As a DevOps engineer, I need centralized logging and monitoring for Kea DHCP services so that I can troubleshoot issues quickly and maintain operational visibility.

**Acceptance Criteria**:
- [ ] Configure rsyslog to forward Kea logs to central syslog server
- [ ] Implement log aggregation (ELK stack or equivalent)
- [ ] Create Grafana dashboards for Kea metrics
  - Lease pool utilization per site
  - Lease grant/release rates
  - Discovery trigger frequency
  - Service health status
- [ ] Configure Prometheus exporters for Kea metrics
- [ ] Set up alerting rules (AlertManager or equivalent)
  - Pool utilization > 80%
  - Service down
  - High error rate
  - Slow response time
- [ ] Create operational runbook for common alerts

**Technical Notes**:
- Use kea-exporter for Prometheus metrics
- Leverage existing monitoring infrastructure
- Retain logs for 90 days minimum
- Alert channels: email, Slack, PagerDuty

**Testing**:
- Verify logs appearing in central aggregation
- Validate dashboard metrics match reality
- Trigger test alerts and verify delivery
- Simulate failure scenarios and validate alerts

---

### Story 19: Create Operational Runbooks

**Story Points**: 5

**Description**:
As an operations team member, I need comprehensive runbooks for common operational tasks so that I can maintain Kea DHCP infrastructure without deep technical knowledge of every component.

**Acceptance Criteria**:
- [ ] Runbook: Deploying new Kea DHCP server
- [ ] Runbook: Upgrading Kea DHCP version
- [ ] Runbook: Troubleshooting discovery failures
- [ ] Runbook: Expanding DHCP pool ranges
- [ ] Runbook: Handling HA failover
- [ ] Runbook: Emergency rollback procedures
- [ ] Runbook: Certificate renewal
- [ ] Runbook: Log analysis and debugging
- [ ] Runbook: Performance tuning
- [ ] Each runbook includes: prerequisites, steps, validation, rollback

**Technical Notes**:
- Use consistent format across all runbooks
- Include example commands with expected output
- Link to related documentation
- Version control runbooks with code

**Testing**:
- Peer review by operations team
- Walkthrough each runbook with team member unfamiliar with system
- Validate all commands and procedures work

---

### Story 20: Implement Automated Testing Pipeline

**Story Points**: 13

**Description**:
As a DevOps engineer, I need an automated CI/CD pipeline for testing Ansible roles so that changes are validated before production deployment.

**Background**:
Manual testing is time-consuming and inconsistent. Automated testing catches regressions early and enables confident deployments.

**Acceptance Criteria**:
- [ ] Implement Molecule testing framework for kea_deploy role
- [ ] Create test scenarios: default, minimal, full-featured, removal
- [ ] Configure Docker-based test environment
- [ ] Implement ansible-lint in CI pipeline
- [ ] Implement yamllint in CI pipeline
- [ ] Python unit tests for monitoring scripts
- [ ] Integration tests for end-to-end workflow
- [ ] Configure GitLab CI/CD pipeline
- [ ] Automated testing on every commit to feature branches
- [ ] Require passing tests before merge to master

**Technical Notes**:
- Use Molecule with Docker driver
- Test on Ubuntu 24.04 container
- Mock external dependencies (NetBox API, Redfish endpoints)
- Store test results as pipeline artifacts

**Testing**:
- Validate CI pipeline runs on test commit
- Verify all test scenarios execute
- Test failure detection (introduce intentional failure)
- Verify merge blocking on test failures

---

## Story Point Summary

| Sprint | Stories | Total Points | Focus Area |
|--------|---------|--------------|------------|
| Sprint 1 | 4 | 21 | Python Lease Monitoring Foundation |
| Sprint 2 | 6 | 36 | Kea DHCP Ansible Role Development |
| Sprint 3 | 3 | 16 | Deployment Orchestration and Documentation |
| Sprint 4 | 4 | 55 | Integration and Testing |
| Sprint 5 | 3 | 26 | Monitoring and Operations |
| **Total** | **20** | **154** | **Complete Automation Stack** |

---

## Story Point Reference Guide

| Points | Complexity | Time Estimate | Description |
|--------|------------|---------------|-------------|
| 1 | Trivial | < 2 hours | Simple config change, documentation update |
| 2 | Simple | 2-4 hours | Small feature, straightforward implementation |
| 3 | Easy | 4-8 hours | Minor feature with some complexity |
| 5 | Medium | 1-2 days | Standard feature, moderate complexity |
| 8 | Complex | 2-3 days | Complex feature, multiple components |
| 13 | Very Complex | 3-5 days | Major feature, significant integration |
| 21 | Huge | 1-2 weeks | Epic-level work, multiple features |

---

## Sprint Planning Notes

### Sprint 1 Focus
Foundation work on Python monitoring scripts. These are prerequisites for the Ansible role deployment.

**Dependencies**: None  
**Risk**: Low  
**Team Size**: 1-2 developers

### Sprint 2 Focus
Core Ansible role development. Highest complexity due to Docker path issues and lifecycle management.

**Dependencies**: Sprint 1 complete  
**Risk**: Medium (Docker environment challenges)  
**Team Size**: 2-3 developers

### Sprint 3 Focus
Deployment automation and documentation. Enables team knowledge sharing.

**Dependencies**: Sprint 2 complete  
**Risk**: Low  
**Team Size**: 1-2 developers + technical writer

### Sprint 4 Focus
Integration testing and multi-site rollout. Highest story point total due to production deployments.

**Dependencies**: Sprints 1-3 complete  
**Risk**: High (production deployments, OEM-specific testing)  
**Team Size**: 2-3 developers + operations team

### Sprint 5 Focus
Production hardening with monitoring, runbooks, and CI/CD pipeline.

**Dependencies**: Sprint 4 complete  
**Risk**: Medium (requires monitoring infrastructure)  
**Team Size**: 2-3 developers + SRE team

---

## Definition of Ready (DoR)

Before moving a story to "In Progress":
- [ ] Story has clear acceptance criteria
- [ ] Technical approach documented or discussed
- [ ] Dependencies identified and available
- [ ] Test environment available
- [ ] Story points estimated by team
- [ ] Story prioritized in backlog

---

## Definition of Done (DoD)

Before moving a story to "Done":
- [ ] All acceptance criteria met
- [ ] Code reviewed and approved
- [ ] Unit tests written and passing
- [ ] Integration tests passing (where applicable)
- [ ] Documentation updated
- [ ] Deployed to test environment and validated
- [ ] No critical bugs or technical debt introduced
- [ ] Conventional commit created following project standards
- [ ] Code merged to feature branch

---

## Epic Success Metrics

### Operational Metrics
- **Time to Discovery**: < 5 minutes from power-on to NetBox registration
- **Automation Rate**: 95% of discoveries require no manual intervention
- **Accuracy**: 99% of discovered data matches physical reality
- **Availability**: 99.9% uptime for DHCP services (with HA)

### Business Metrics
- **Time Savings**: 2 hours saved per server provisioning
- **Error Reduction**: 90% reduction in inventory discrepancies
- **Cost Avoidance**: Eliminate 100+ hours/year of manual inventory
- **Scalability**: Support 500+ bare-metal servers across 4 sites

### Technical Metrics
- **Test Coverage**: > 80% for Python code, 100% for Ansible roles (Molecule)
- **Deployment Time**: < 30 minutes for new Kea DHCP server
- **Recovery Time**: < 15 minutes for service restoration
- **Documentation**: 100% of components documented with examples

---

## Risk Management

### High-Priority Risks

**Risk 1: Production DHCP Disruption**
- **Probability**: Medium
- **Impact**: High
- **Mitigation**: Deploy to test environment first, implement HA, maintain rollback capability
- **Owner**: Network Architecture Team

**Risk 2: OEM-Specific Redfish Incompatibilities**
- **Probability**: High
- **Impact**: Medium
- **Mitigation**: Test with physical hardware from each OEM, implement graceful fallbacks
- **Owner**: Discovery Team

**Risk 3: NetBox API Changes**
- **Probability**: Low
- **Impact**: Medium
- **Mitigation**: Pin NetBox API version, implement API versioning checks, maintain test coverage
- **Owner**: Integration Team

**Risk 4: Resource Constraints on Kea Servers**
- **Probability**: Medium
- **Impact**: Medium
- **Mitigation**: Capacity planning, monitoring alerts, load testing before production
- **Owner**: Operations Team

---

## Post-Sprint Retrospective Questions

1. **What went well?**
   - Which automation components exceeded expectations?
   - What documentation was most helpful?

2. **What could be improved?**
   - Were story points accurate?
   - Did we encounter unexpected blockers?
   - Was testing adequate?

3. **Action items for next sprint**
   - Technical debt to address
   - Process improvements
   - Tool or infrastructure needs

---

## Related Documentation

- [DESIGN.md](DESIGN.md) - Architecture and design decisions
- [TESTING.md](TESTING.md) - Testing procedures and validation
- [DEPLOYMENT.md](DEPLOYMENT.md) - Deployment guide
- [KEA.md](KEA.md) - Kea DHCP architecture
- [.copilot-instructions.md](../.github/copilot-instructions.md) - Project coding standards

---

**Document Version**: 1.0  
**Last Updated**: December 15, 2025  
**Status**: Ready for Sprint Planning  
**Next Review**: After Sprint 1 completion
