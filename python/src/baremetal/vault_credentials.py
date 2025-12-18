#!/usr/bin/env python3
"""
HashiCorp Vault credential retrieval for baremetal automation.

Retrieves credentials from Vault KV v2 secrets engine.

Authentication Methods:
    1. Token (for testing/development) - VAULT_TOKEN
    2. AppRole (for production) - VAULT_ROLE_ID + VAULT_SECRET_ID

Environment variables:
    VAULT_ADDR - Vault server URL (e.g., https://vault.example.com:8200)
    
    For Token auth (testing):
        VAULT_TOKEN - Vault token
    
    For AppRole auth (production):
        VAULT_ROLE_ID - AppRole role ID
        VAULT_SECRET_ID - AppRole secret ID
    
    Optional:
        VAULT_NAMESPACE - Vault namespace (for Vault Enterprise)
        VAULT_SKIP_VERIFY - Skip TLS verification (use with caution)

Usage:
    from vault_credentials import get_vault_client, get_secret
    
    # Automatically detects auth method (token takes priority)
    client = get_vault_client()
    db_creds = get_secret(client, 'kea/database')
    sds_creds = get_secret(client, 'solidserver/dns')
"""

import os
import logging
from typing import Optional, Dict, Any
import hvac
from hvac.exceptions import VaultError


logger = logging.getLogger(__name__)


def get_vault_client(
    vault_addr: Optional[str] = None,
    token: Optional[str] = None,
    role_id: Optional[str] = None,
    secret_id: Optional[str] = None,
    namespace: Optional[str] = None,
    skip_verify: bool = False
) -> hvac.Client:
    """
    Create authenticated Vault client.
    
    Supports two authentication methods (priority order):
    1. Token authentication (VAULT_TOKEN) - for testing/development
    2. AppRole authentication (VAULT_ROLE_ID + VAULT_SECRET_ID) - for production
    
    Args:
        vault_addr: Vault server URL (default: from VAULT_ADDR env var)
        token: Vault token (default: from VAULT_TOKEN env var)
        role_id: AppRole role ID (default: from VAULT_ROLE_ID env var)
        secret_id: AppRole secret ID (default: from VAULT_SECRET_ID env var)
        namespace: Vault namespace for Enterprise (default: from VAULT_NAMESPACE env var)
        skip_verify: Skip TLS certificate verification (default: False or VAULT_SKIP_VERIFY)
        
    Returns:
        Authenticated hvac.Client instance
        
    Raises:
        ValueError: If required credentials are missing
        VaultError: If authentication fails
    """
    # Get configuration from environment variables
    vault_addr = vault_addr or os.environ.get('VAULT_ADDR')
    token = token or os.environ.get('VAULT_TOKEN')
    role_id = role_id or os.environ.get('VAULT_ROLE_ID')
    secret_id = secret_id or os.environ.get('VAULT_SECRET_ID')
    namespace = namespace or os.environ.get('VAULT_NAMESPACE')
    
    if os.environ.get('VAULT_SKIP_VERIFY', '').lower() in ('true', '1', 'yes'):
        skip_verify = True
    
    # Validate required parameters
    if not vault_addr:
        raise ValueError("VAULT_ADDR environment variable must be set")
    
    # Check which auth method is available
    use_token = bool(token)
    use_approle = bool(role_id and secret_id)
    
    if not use_token and not use_approle:
        raise ValueError(
            "Vault authentication credentials required. Provide either:\n"
            "  - VAULT_TOKEN (for testing/development)\n"
            "  - VAULT_ROLE_ID + VAULT_SECRET_ID (for production AppRole)"
        )
    
    try:
        # Create client
        client = hvac.Client(
            url=vault_addr,
            namespace=namespace,
            verify=not skip_verify
        )
        
        # Authenticate based on available credentials
        if use_token:
            # Token authentication (testing/development)
            client.token = token
            logger.info("Using Vault token authentication (testing mode)")
        else:
            # AppRole authentication (production)
            client.auth.approle.login(
                role_id=role_id,
                secret_id=secret_id
            )
            logger.info("Using Vault AppRole authentication (production mode)")
        
        # Verify authentication
        if not client.is_authenticated():
            raise VaultError("Failed to authenticate with Vault")
        
        logger.info(f"Successfully authenticated to Vault at {vault_addr}")
        if namespace:
            logger.info(f"Using namespace: {namespace}")
        
        return client
        
    except Exception as e:
        logger.error(f"Failed to connect to Vault: {e}")
        raise


def get_secret(
    client: hvac.Client,
    secret_path: str,
    mount_point: str = 'secret'
) -> Dict[str, Any]:
    """
    Retrieve secret from Vault KV v2 secrets engine.
    
    Args:
        client: Authenticated Vault client
        secret_path: Path to secret (e.g., 'kea/database')
        mount_point: KV v2 mount point (default: 'secret')
        
    Returns:
        Dictionary containing secret data
        
    Raises:
        VaultError: If secret retrieval fails
    """
    try:
        # Read secret from KV v2 engine
        response = client.secrets.kv.v2.read_secret_version(
            path=secret_path,
            mount_point=mount_point
        )
        
        secret_data = response['data']['data']
        logger.debug(f"Retrieved secret from {mount_point}/{secret_path}")
        
        return secret_data
        
    except Exception as e:
        logger.error(f"Failed to retrieve secret '{secret_path}': {e}")
        raise


def get_kea_database_credentials(
    client: hvac.Client, 
    secret_path: str = 'teams/core-infrastructure/server/kea_db',
    mount_point: str = 'secrets'
) -> Dict[str, str]:
    """
    Retrieve Kea database credentials from Vault.
    
    Expected fields: host, port, database, username, password
    
    Args:
        client: Authenticated Vault client
        secret_path: Path to secret in Vault (default: 'teams/core-infrastructure/server/kea_db')
        mount_point: KV v2 mount point (default: 'secret')
        
    Returns:
        Dict with db_host, db_port, db_name, db_user, db_password
    """
    secret = get_secret(client, secret_path, mount_point)
    
    return {
        'db_host': secret.get('host', 'localhost'),
        'db_port': int(secret.get('port', 5432)),
        'db_name': secret.get('database', 'kea'),
        'db_user': secret.get('username'),
        'db_password': secret.get('password')
    }


def get_solidserver_credentials(
    client: hvac.Client,
    secret_path: str = 'teams/core-infrastructure/server/baremetal_dns',
    mount_point: str = 'secrets'
) -> Dict[str, str]:
    """
    Retrieve SOLIDserver DNS credentials from Vault.
    
    Expected fields: username, password
    
    Args:
        client: Authenticated Vault client
        secret_path: Path to secret in Vault (default: 'teams/core-infrastructure/server/baremetal_dns')
        mount_point: KV v2 mount point (default: 'secrets')
        
    Returns:
        Dict with sds_login, sds_password
    """
    secret = get_secret(client, secret_path, mount_point)
    
    return {
        'sds_login': secret.get('username'),
        'sds_password': secret.get('password')
    }


def get_netbox_credentials(
    client: hvac.Client,
    secret_path: str = 'netbox/api',
    mount_point: str = 'secret'
) -> Dict[str, str]:
    """
    Retrieve NetBox credentials from Vault.
    
    Expected fields: url, token
    
    Args:
        client: Authenticated Vault client
        secret_path: Path to secret in Vault (default: 'netbox/api')
        mount_point: KV v2 mount point (default: 'secret')
        
    Returns:
        Dict with netbox_url, netbox_token
    """
    secret = get_secret(client, secret_path, mount_point)
    
    return {
        'netbox_url': secret.get('url'),
        'netbox_token': secret.get('token')
    }


def get_bmc_credentials(
    client: hvac.Client,
    secret_path: str = 'bmc/credentials',
    mount_point: str = 'secret'
) -> Dict[str, str]:
    """
    Retrieve BMC credentials from Vault.
    
    Expected fields: username, password
    
    Args:
        client: Authenticated Vault client
        secret_path: Path to secret in Vault (default: 'bmc/credentials')
        mount_point: KV v2 mount point (default: 'secret')
        
    Returns:
        Dict with bmc_username, bmc_password
    """
    secret = get_secret(client, secret_path, mount_point)
    
    return {
        'bmc_username': secret.get('username'),
        'bmc_password': secret.get('password')
    }
