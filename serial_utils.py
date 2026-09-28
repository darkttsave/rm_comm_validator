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
