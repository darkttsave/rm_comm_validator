"""Serial transport layer."""

import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class SerialFrame:
    """Raw serial frame."""
    data: bytes
    timestamp: float


class SerialTransport:
    """Serial transport interface."""

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = 'N',
        stopbits: int = 1,
        timeout_ms: int = 20
    ):
        """
        Initialize Serial transport.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0', 'COM3')
            baudrate: Baud rate (default: 9600)
            bytesize: Data bits (default: 8)
            parity: Parity ('N', 'E', 'O', 'M', 'S')
            stopbits: Stop bits (default: 1)
            timeout_ms: Read timeout in milliseconds
        """
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout_ms = timeout_ms
        self.serial = None
        self._running = False

    def connect(self):
        """Connect to serial port."""
        try:
            import serial

            # Map parity string to pyserial constant
            parity_map = {
                'N': serial.PARITY_NONE,
                'none': serial.PARITY_NONE,
                'E': serial.PARITY_EVEN,
                'even': serial.PARITY_EVEN,
                'O': serial.PARITY_ODD,
                'odd': serial.PARITY_ODD,
                'M': serial.PARITY_MARK,
                'mark': serial.PARITY_MARK,
                'S': serial.PARITY_SPACE,
                'space': serial.PARITY_SPACE,
            }

            parity_value = parity_map.get(self.parity, serial.PARITY_NONE)

            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=parity_value,
                stopbits=self.stopbits,
                timeout=self.timeout_ms / 1000.0  # Convert to seconds
            )
            print(f"Connected to {self.port} at {self.baudrate} baud")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to {self.port}: {e}")

    def disconnect(self):
        """Disconnect from serial port."""
        self._running = False
        if self.serial:
            self.serial.close()
            self.serial = None

    def read(self, size: int = 1) -> Optional[bytes]:
        """
        Read bytes from serial port.

        Args:
            size: Number of bytes to read

        Returns:
            bytes or None on timeout
        """
        if not self.serial:
            raise RuntimeError("Not connected")

        try:
            data = self.serial.read(size)
            if len(data) > 0:
                return data
            return None
        except Exception as e:
            raise RuntimeError(f"Serial read error: {e}")

    def read_available(self) -> bytes:
        """
        Read all immediately available bytes.

        Returns:
            bytes (may be empty if nothing available)
        """
        if not self.serial:
            raise RuntimeError("Not connected")

        try:
            in_waiting = self.serial.in_waiting
            if in_waiting > 0:
                return self.serial.read(in_waiting)
            return b''
        except Exception as e:
            raise RuntimeError(f"Serial read error: {e}")

    def write(self, data: bytes):
        """
        Write bytes to serial port.

        Args:
            data: Bytes to write
        """
        if not self.serial:
            raise RuntimeError("Not connected")

        try:
            self.serial.write(data)
        except Exception as e:
            raise RuntimeError(f"Serial write error: {e}")
