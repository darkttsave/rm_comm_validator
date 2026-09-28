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


def build_unified_can_endpoints(physical_interfaces, virtual_status):
    """
    Merge the Validator-managed virtual CAN endpoint with discovered physical interfaces.

    Args:
        physical_interfaces: list of interface names from get_available_socketcan_interfaces()
        virtual_status: dict from CANSimulator.get_status()

    Returns:
        list of endpoint dicts: {interface, label, kind, available, running}
    """
    endpoints = []

    # Managed virtual endpoint always comes first.
    endpoints.append({
        'interface': virtual_status['interface'],
        'label': virtual_status['label'],
        'kind': 'virtual',
        'available': virtual_status['vcan_available'] and virtual_status['mock_built'],
        'running': virtual_status['running'],
    })

    # Discovered physical endpoints (exclude common non-CAN interfaces).
    non_can = {'lo', 'eth0', 'eth1', 'wlan0', 'wlan1', 'docker0', 'br-'}
    for iface in physical_interfaces:
        # Skip the virtual one if it appears in physical list
        if iface == virtual_status['interface']:
            continue
        # Skip obvious non-CAN interfaces
        if iface in non_can or any(iface.startswith(prefix) for prefix in ['eth', 'wlan', 'en', 'wl', 'br-', 'docker']):
            continue

        endpoints.append({
            'interface': iface,
            'label': iface,
            'kind': 'physical',
            'available': True,
            'running': False,
        })

    return endpoints
