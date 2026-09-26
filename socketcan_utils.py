"""Utility functions for SocketCAN interface detection."""

import platform
import os
from pathlib import Path
from typing import List


def is_linux() -> bool:
    """Check if running on Linux."""
    return platform.system() == 'Linux'


def get_available_socketcan_interfaces() -> List[str]:
    """
    Get list of available SocketCAN interfaces on Linux.

    Returns:
        List of interface names (e.g., ['can0', 'vcan0'])
    """
    if not is_linux():
        return []

    interfaces = []
    sys_class_net = Path('/sys/class/net')

    if not sys_class_net.exists():
        return []

    try:
        for iface_dir in sys_class_net.iterdir():
            if not iface_dir.is_dir():
                continue

            # Check if it's a CAN interface by looking for type file
            type_file = iface_dir / 'type'
            if type_file.exists():
                # CAN interfaces typically have type 280 (ARPHRD_CAN)
                try:
                    iface_type = type_file.read_text().strip()
                    if iface_type == '280':
                        interfaces.append(iface_dir.name)
                except:
                    pass
    except Exception:
        pass

    return sorted(interfaces)


def interface_exists(interface: str) -> bool:
    """
    Check if a specific SocketCAN interface exists.

    Args:
        interface: Interface name to check

    Returns:
        True if interface exists
    """
    if not is_linux():
        return False

    return interface in get_available_socketcan_interfaces()
