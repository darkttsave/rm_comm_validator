"""Serial port utilities."""

from typing import List, Dict


def get_available_serial_ports() -> List[Dict[str, str]]:
    """
    Get list of available serial ports.

    Returns:
        List of dicts with 'device', 'description', 'hwid' keys
    """
    try:
        import serial.tools.list_ports
        ports = serial.tools.list_ports.comports()

        result = []
        for port in ports:
            result.append({
                'device': port.device,
                'description': port.description or '',
                'hwid': port.hwid or ''
            })

        return result
    except Exception as e:
        print(f"Error listing serial ports: {e}")
        return []


def port_exists(port: str) -> bool:
    """
    Check if a serial port exists.

    Args:
        port: Port path (e.g., '/dev/ttyUSB0', 'COM3')

    Returns:
        True if port exists
    """
    ports = get_available_serial_ports()
    return any(p['device'] == port for p in ports)


def build_unified_endpoints(physical_ports, virtual_status):
    """
    Merge the Validator-managed virtual endpoint with discovered physical ports.

    Args:
        physical_ports: list of dicts from get_available_serial_ports()
        virtual_status: dict from SerialSimulator.get_status()

    Returns:
        list of endpoint dicts: {device, label, kind, available, running}
    """
    endpoints = []

    # Managed virtual endpoint always comes first.
    endpoints.append({
        'device': virtual_status['device'],
        'label': virtual_status['label'],
        'kind': 'virtual',
        'available': virtual_status['socat_installed'],
        'running': virtual_status['running'],
    })

    # Discovered physical endpoints.
    for port in physical_ports:
        description = port.get('description', '')
        label = "{} - {}".format(port['device'], description) if description else port['device']
        endpoints.append({
            'device': port['device'],
            'label': label,
            'kind': 'physical',
            'available': True,
            'running': False,
        })

    return endpoints
