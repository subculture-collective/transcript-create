"""Utility functions for PO token handling."""

import re
from typing import List


def redact_tokens_from_command(cmd: List[str]) -> str:
    """Redact PO token values from command for safe logging.

    Args:
        cmd: Command list

    Returns:
        Command string with tokens redacted
    """
    cmd_str = " ".join(cmd)
    # Redact po_token values: po_token=type:TOKEN -> po_token=type:***REDACTED***
    # Match po_token=type:VALUE where VALUE may be quoted or unquoted
    cmd_str = re.sub(
        r'(po_token=\w+:)(?:"([^"]*)"|\'([^\']*)\'|([^\s;"\']+))',
        r'\1***REDACTED***',
        cmd_str
    )
    return cmd_str
