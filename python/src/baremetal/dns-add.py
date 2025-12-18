#!/usr/local/venv/smartserver/bin/python
"""DNS Record Creation Script for SOLIDserver integration."""
import logging
import re
import os, sys
import uuid
from SOLIDserverRest import *
from SOLIDserverRest import adv as sdsadv
from SOLIDserverRest.Exception import SDSError, SDSDNSError
import dns.resolver
import argparse

import custom_logging
import solidserver_connection
import vault_credentials
parser = argparse.ArgumentParser()

parser = argparse.ArgumentParser()

zones = ['site.com', 'erlog.com']
types = ['A', 'CNAME']
zone_to_server_mapping = {
    'external': 'dns-external-smart.site.com',
    'internal': 'dns-internal-smart.site.com'
}
zone_choices = list(zone_to_server_mapping.keys())


def case_insensitive_choice(choices):
    def check_case_insensitive(value):
        if value.lower() in (choice.lower() for choice in choices):
            return value.upper()
        raise argparse.ArgumentTypeError(f"{value} is not a valid option. Choose from {choices}")
    return check_case_insensitive


def validate_target(args):
    if args.type == 'A':
        if not re.match(r'^\d{1,3}(\.\d{1,3}){3}$', args.target):
            raise argparse.ArgumentTypeError(f"{args.target} is not a valid IP address for type 'A'")
    elif args.type == 'CNAME':
        if not re.match(r'^([a-zA-Z0-9-]+\.)+[a-zA-Z0-9-]+$', args.target):
            raise argparse.ArgumentTypeError(f"{args.target} is not a valid DNS name for type 'CNAME'")


requiredName = parser.add_argument_group('required arguments')
requiredName.add_argument('-n', '--name', type=str, required=True, help="DNS name to create")
requiredName.add_argument('-z', '--zone', type=str, required=True, choices=zones, help="Zone to create under")
requiredName.add_argument('-r', '--target', type=str, required=True, help="Target IP address or DNS name")
requiredName.add_argument('-t', '--type', type=case_insensitive_choice(['A', 'CNAME']), required=True, help="Record type")
requiredName.add_argument('-c', '--scope', type=str, required=True, choices=zone_choices, help="Scope: 'internal' or 'external'")

args, unknown = parser.parse_known_args()
validate_target(args)

parser.add_argument('-d', '--dryrun-only', action='store_true', help="Only validate, do not create (always validates first)")
parser.add_argument('-v', '--verbose', action='store_true', help="Show detailed API call information")
parser.add_argument('--use-vault', action='store_true', help="Retrieve SOLIDserver credentials from Vault")
parser.add_argument('--sds-host', default='172.30.16.141', help="SOLIDserver hostname/IP (default: 172.30.16.141)")
parser.add_argument('--sds-username', help="SOLIDserver username (overrides Vault/env)")
parser.add_argument('--sds-password', help="SOLIDserver password (overrides Vault/env)")

args = parser.parse_args()

custom_logging.setup_logging(
    script_name="dns-add.py",
    verbose=args.verbose
)

zone = args.zone
name = args.name.lower()
rrtype = str(args.type)
target = args.target
scope = args.scope

logging.info("=" * 60)
logging.info("PHASE 1: VALIDATION (DRY RUN)")
logging.info("=" * 60)
logging.info(f'Validating {rrtype} record: {name}.{zone} -> {target} ({scope})')

# Get SOLIDserver credentials (priority: command line > Vault > .env file)
if args.sds_username and args.sds_password:
    logging.debug("Using credentials from command line")
    sds_host = args.sds_host
    sds_user = args.sds_username
    sds_pass = args.sds_password
    # Create connection with provided credentials
    try:
        logging.debug(f"Connecting to SOLIDserver at {sds_host} as {sds_user}")
        sds = sdsadv.SDS(ip_address=sds_host, user=sds_user, pwd=sds_pass)
        sds.connect(method="native")
        logging.info("Successfully connected to SOLIDserver")
    except SDSError as e:
        logging.error(f"Connection failed: {e}")
        sys.exit(2)
elif args.use_vault:
    logging.info("Retrieving credentials from Vault...")
    try:
        client = vault_credentials.get_vault_client()
        creds = vault_credentials.get_solidserver_credentials(client)
        sds_host = args.sds_host
        sds_user = creds['sds_login']
        sds_pass = creds['sds_password']
        logging.debug(f"Connecting to SOLIDserver at {sds_host} as {sds_user}")
        sds = sdsadv.SDS(ip_address=sds_host, user=sds_user, pwd=sds_pass)
        sds.connect(method="native")
        logging.info("Successfully connected to SOLIDserver with Vault credentials")
    except Exception as e:
        logging.error(f"Vault connection failed: {e}")
        sys.exit(2)
else:
    # Fallback to .env file via solidserver_connection module
    try:
        sds = solidserver_connection.get_connection()
    except (RuntimeError, ConnectionError) as e:
        logging.error(f"Connection failed: {e}")
        sys.exit(2)


def find_record():
    """Check for existing DNS records to prevent duplicates."""
    logging.debug('Querying for existing records')
    parameters = {
        "WHERE": f"rr_full_name = '{name}.{zone}' AND dns_name = '{zone_to_server_mapping[scope]}' AND dnszone_name = '{zone}'"
    }
    try:
        my_rrs = sds.query("dns_rr_list", parameters, timeout=60)
    except SDSEmptyError:
        logging.debug("No existing records found")
        return True
    for rr in my_rrs:
        logging.debug(f"rr full name: {rr['rr_full_name']}")
        logging.error(f"Existing record found: {rr['rr_full_name']}")
        sys.exit(5)


def resolve_cname_to_a_record(cname):
    """Follow CNAME chain to validate target exists."""
    current_name = cname
    max_depth = 10
    depth = 0

    while depth < max_depth:
        try:
            answer = dns.resolver.resolve(current_name, 'CNAME')
            current_name = answer[0].target.to_text()
        except dns.resolver.NoAnswer:
            try:
                a_record_answer = dns.resolver.resolve(current_name, 'A')
                return a_record_answer[0].address, current_name
            except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN):
                return None
        except dns.resolver.NXDOMAIN:
            logging.error("Target domain does not exist")
            sys.exit(6)
        depth += 1

    logging.error("CNAME chain is too long or contains a loop")
    sys.exit(7)


def add_record(mz, mn, rrt, tgt):
    """Create DNS record in SOLIDserver."""
    logging.info(f"Creating {rrt} record {mn} with target {tgt} in zone {zone}")
    logging.info("Create DNS record " + mn)
    myname = str(mn + "." + mz)
    logging.debug(f"Full DNS name: {myname}")
    # create the DNS resource record object
    dns_rr = sdsadv.DNS_record(sds, myname)
    dns_rr.zone = dns_zone
    dns_rr.set_dns(ss_dns)
    dns_rr.set_ttl(600)
    dns_rr.set_async()
    dns_rr.set_sync = False

    if rrt == "CNAME":
        dns_rr.set_type(rrt, target=tgt)
    elif rrt == "A":
        dns_rr.set_type(rrt, ip=tgt)
    else:
        logging.error("Invalid record type - this shouldn't have happened")
        sys.exit(8)  # Invalid record type

    logging.debug("Creating dns_rr record:")
    # Push it in to EfficientIP (cross your fingers)
    try:
        dns_rr.create()
        # Log detailed record information for audit and debugging
        logging.info(dns_rr)
        logging.info(f"Successfully created {rrt} record: {mn}.{mz} -> {tgt}")
    except (SDSError, SDSDNSError) as e:
        logging.error(f"Failed to create DNS record: {e}")
        sys.exit(9)  # Record creation failed
    except BaseException as e:
        logging.error(f"Unexpected error creating DNS record: {e}")
        sys.exit(9)  # Record creation failed
    return True

logging.debug("Connection established, proceeding with DNS operations")

# Validate CNAME targets early to fail fast
if rrtype == "CNAME":
    logging.debug("Checking for valid target: " + target)
    result = resolve_cname_to_a_record(target)
    if result:
        final_a_record, curname = result
        logging.debug("Final IP record target for CNAME: " + final_a_record)
        logging.debug("Final CNAME name for new CNAME:   " + curname)
    else:
        logging.error("CNAME target resolution failed")
        sys.exit(6)  # Invalid target

# Get zone ID (ugly, hacky ... but this is how EfficientIP's API works)
# If you don't have the dnszone_id the create fails even though there is
# only one zone that meets the search parameters (per the documentation).
# This is what I had to do to make it work - blame EfficientIP's API design
logging.debug(f"Looking up zone ID for {zone} in {scope} scope")
zparameters = {
    "WHERE": "dns_name = '" + zone_to_server_mapping[scope] + "' AND dnszone_name = '"+zone+"'"
    }
try:
    my_zs = sds.query("dns_zone_list",zparameters,timeout=60)
except Exception as e:
    logging.error(f"Failed to query DNS zones: {e}")
    sys.exit(10)  # Zone query failed

raw_zone = []
if len(my_zs) == 1:
    logging.debug("got zone " + zone)
    raw_zone = my_zs[0]
elif len(my_zs) == 0:
    logging.error(f"No zones found matching criteria - check your zone and scope settings")
    sys.exit(11)  # Zone not found
else:
    logging.error(f"Got {len(my_zs)} zones when expecting 1 - this shouldn't happen")
    sys.exit(12)  # Multiple zones found (shouldn't happen)

# Set up the base connection to the solidserver
# Default DNS server - use internal unless scope is external
dns_server_name = zone_to_server_mapping.get(scope, 'dns-internal-smart.site.com')
logging.debug(f"Using DNS server: {dns_server_name}")

# Create DNS server object (no UUID formatting needed for server name)
ss_dns = sdsadv.DNS(name=dns_server_name, sds=sds)

# Create DNS zone object
dns_zone = sdsadv.DNS_zone(sds=sds, name=zone)
dns_zone.set_dns(ss_dns)
dns_zone.myid = raw_zone['dnszone_id']

# This API ... SUCKS. Calling each of these does different things, both are required.
try:
    ss_dns.refresh()
    dns_zone.refresh()
    logging.debug(f"DNS server and zone objects initialized successfully")
except Exception as e:
    logging.error(f"Failed to refresh DNS objects: {e}")
    sys.exit(13)  # DNS object refresh failed

# Final CNAME validation (yes, we do this twice because paranoia)
if rrtype == "CNAME":
    logging.debug("Final check for valid CNAME target: " + target)
    result = resolve_cname_to_a_record(target)
    if result:
        final_a_record, curname = result
        logging.debug("Final IP record target for CNAME: " + final_a_record)
        logging.debug("Final CNAME name for new CNAME:   " + curname)
    else:
        logging.error("CNAME target validation failed on final check")
        sys.exit(6)  # Invalid target

# Check for existing records (because duplicates are bad, mmkay?)
if find_record() is True:
    logging.info("[OK] No existing record found")
else:
    # This should be handled in find_record(), but better safe than sorry
    logging.error("Found existing record - aborting to prevent duplicates")
    sys.exit(5)  # Record already exists

# Validation complete - summarize what will be created
logging.info("=" * 60)
logging.info("VALIDATION PASSED")
logging.info("=" * 60)
logging.info(f"Record to create:")
logging.info(f"  Type:   {rrtype}")
logging.info(f"  Name:   {name}.{zone}")
logging.info(f"  Target: {target}")
logging.info(f"  Scope:  {scope} ({zone_to_server_mapping[scope]})")
logging.info(f"  Zone:   {zone} (ID: {raw_zone['dnszone_id']})")
logging.info("=" * 60)

# Check if dry-run only mode
if args.dryrun_only:
    logging.info("Dry-run only mode - validation complete, not creating record")
    sys.exit(0)  # Success (dry run)

# Proceed with actual creation
logging.info("=" * 60)
logging.info("PHASE 2: CREATION")
logging.info("=" * 60)
add_record(zone, name, rrtype, target)
logging.info(f"DNS record creation completed successfully")
sys.exit(0)  # Success
