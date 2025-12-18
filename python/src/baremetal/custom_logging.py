#!/usr/bin/env python3
"""Custom logging module for dual console/syslog output with sensitive data filtering."""

import logging
import logging.handlers
import sys
import re


class SensitiveDataFilter(logging.Filter):
    """Filter to redact sensitive information from log messages."""

    def filter(self, record):
        try:
            message = record.getMessage()
        except:
            message = str(record.msg) if hasattr(record, 'msg') else ""

        if message:
            message = re.sub(r"'X-IPM-Password':\s*b'[^']*'", "'X-IPM-Password': b'***REDACTED***'", message)
            message = re.sub(r"X-IPM-Password':\s*b'[^']*'", "X-IPM-Password': b'***REDACTED***'", message)
            message = re.sub(r"(password|pwd|pass)[\s]*[:=][\s]*['\"]?[^'\"\s,}]+",
                           r"\1: ***REDACTED***", message, flags=re.IGNORECASE)
            record.msg = message
            record.args = ()

        return True


def setup_logging(script_name, verbose=False, syslog_facility=None, suppress_noisy_libraries=True):
    """Set up dual logging (console + syslog) with sensitive data filtering."""
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    console_formatter = logging.Formatter('[%(filename)s:%(lineno)d] %(levelname)s: %(message)s')
    syslog_formatter = logging.Formatter(f'{script_name}[%(process)d]: [%(filename)s:%(lineno)d] %(levelname)s: %(message)s')

    sensitive_filter = SensitiveDataFilter()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addFilter(sensitive_filter)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    root_logger.addHandler(console_handler)

    try:
        if syslog_facility is None:
            syslog_facility = logging.handlers.SysLogHandler.LOG_USER

        syslog_handler = logging.handlers.SysLogHandler(
            address='/dev/log',
            facility=syslog_facility
        )
        syslog_handler.setFormatter(syslog_formatter)
        syslog_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(syslog_handler)
    except Exception as e:
        print(f"Warning: Could not connect to syslog: {e}", file=sys.stderr)

    if suppress_noisy_libraries:
        noisy_loggers = [
            'SOLIDserverRest',
            'urllib3.connectionpool',
            'requests.packages.urllib3.connectionpool',
            'paramiko.transport',
            'boto3.resources.action',
            'botocore.client'
        ]
        for logger_name in noisy_loggers:
            logging.getLogger(logger_name).setLevel(logging.INFO)

    return root_logger


def get_logger(name=None):
    """Get a logger instance."""
    return logging.getLogger(name)


def configure_logging(*args, **kwargs):
    """Alias for setup_logging() for backward compatibility."""
    return setup_logging(*args, **kwargs)
