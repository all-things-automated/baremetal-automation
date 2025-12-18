#!/usr/bin/env python3

# SOLIDserver connection utility - Simple retry edition
# Because nobody wants to copy-paste the same connection boilerplate everywhere.
# This version uses simple, reliable connection-level retries instead of
# fighting with the SOLIDserverRest library's internal session management.
#
# Usage:
#     import solidserver_connection
#
#     # Get a connected SDS instance (handles all the auth nonsense)
#     sds = solidserver_connection.get_connection()
#
#     # Now use it exactly like you always have
#     my_rrs = sds.query("dns_rr_list", parameters, timeout=60)
#     # ... rest of your code unchanged

import logging
import base64
import os
import time
from SOLIDserverRest import *
from SOLIDserverRest import adv as sdsadv


def load_env_variable(var_name, env_file="/usr/local/bin/.env"):
    # Load environment variables from a .env file
    # Inline version so we don't need external dependencies
    try:
        with open(env_file, 'r') as file:
            for line in file:
                # Remove any leading/trailing whitespace and comments
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue

                # Split line into key and value
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if they exist
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Return value if the key matches the requested variable
                if key == var_name:
                    return value
    except FileNotFoundError:
        raise FileNotFoundError(f"The {env_file} file was not found.")

    # Raise error if variable is not found
    raise ValueError(f"{var_name} not found in {env_file} file.")


def get_env_decoded(var_name, env_file="/usr/local/bin/.env", encoding="utf-8"):
    # Get environment variable and base64 decode it
    # Inline version for password handling
    encoded_value = load_env_variable(var_name, env_file)

    try:
        decoded_bytes = base64.b64decode(encoded_value)
        return decoded_bytes.decode(encoding)
    except Exception as e:
        raise ValueError(f"Failed to base64 decode '{var_name}': {e}")


def get_env_int(var_name, env_file="/usr/local/bin/.env", default=None):
    # Get environment variable as integer
    try:
        value = load_env_variable(var_name, env_file)
        return int(value)
    except (FileNotFoundError, ValueError):
        if default is not None:
            return default
        raise


def get_connection(env_file="/usr/local/bin/.env", enable_retries=True):
    # Get a connected SOLIDserver instance with all the authentication handled
    # Returns the same sdsadv.SDS object you're used to working with
    # All configuration comes from the .env file because we're not savages
    # Simple retry logic at the connection level - much cleaner than fighting with library internals!

    # Load all config from .env file
    try:
        host = load_env_variable("SDS_HOST", env_file)
        login = load_env_variable("SDS_LOGIN", env_file)
        password = get_env_decoded("SDS_HASH", env_file)

        # Optional retry configuration from .env (with defaults)
        try:
            max_retries = get_env_int("SDS_MAX_RETRIES", env_file, default=3)
        except:
            max_retries = 3
        try:
            retry_delay = get_env_int("SDS_RETRY_DELAY", env_file, default=2)
        except:
            retry_delay = 2

    except (FileNotFoundError, ValueError, Exception) as e:
        raise RuntimeError(f"Failed to load SOLIDserver configuration from {env_file}: {e}")

    # Connection retry loop - simple and reliable!
    last_error = None

    for attempt in range(max_retries + 1):  # +1 because we want max_retries actual retries
        try:
            # Create the SDS connection object (same as you always did)
            logging.debug(f"Connecting to SOLIDserver at {host} as {login} (attempt {attempt + 1}/{max_retries + 1})")
            sds = sdsadv.SDS(ip_address=host, user=login, pwd=password)

            # Attempt connection
            sds.connect(method="native")
            logging.info(f"Successfully connected to SOLIDserver on attempt {attempt + 1}")
            return sds

        except SDSError as e:
            last_error = e
            error_msg = str(e).lower()

            # Only retry on connection/timeout errors, not auth failures
            if any(keyword in error_msg for keyword in ['timeout', 'connection', 'unreachable', 'refused', 'max retries exceeded']):
                if attempt < max_retries:  # Don't sleep after the last attempt
                    sleep_time = retry_delay * (1.5 ** attempt)  # Exponential backoff
                    logging.warning(f"Connection attempt {attempt + 1} failed with timeout/connection error: {e}")
                    logging.info(f"Retrying in {sleep_time:.1f} seconds...")
                    time.sleep(sleep_time)
                else:
                    logging.error(f"All {max_retries + 1} connection attempts failed")
            else:
                # Don't retry auth failures or other non-connection errors
                logging.error(f"Connection failed with non-retryable error: {e}")
                break

        except Exception as e:
            # Catch any other unexpected errors
            last_error = e
            logging.error(f"Unexpected error during connection attempt {attempt + 1}: {e}")
            break

    # If we get here, all attempts failed
    raise ConnectionError(f"Failed to connect to SOLIDserver after {max_retries + 1} attempts. Last error: {last_error}")


# Convenience aliases because everyone has opinions about function names
def connect(env_file="/usr/local/bin/.env", enable_retries=True):
    # Simple alias for get_connection() with defaults
    return get_connection(env_file, enable_retries)


def get_sds(env_file="/usr/local/bin/.env", enable_retries=True):
    # Another alias because naming is hard
    return get_connection(env_file, enable_retries)

