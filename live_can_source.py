"""Live SocketCAN data source for Web UI."""

import threading
import time
from typing import Callable, Optional
from can_transport import CANTransport, CANFrame


class LiveCANSource:
    """Live SocketCAN data source."""

    def __init__(self, interface: str):
        """
        Initialize Live CAN source.

        Args:
            interface: SocketCAN interface name (e.g., 'can0', 'vcan0')
        """
        self.interface = interface
        self.transport = CANTransport(interface)
        self.running = False
        self._thread = None
        self._callback = None

    def connect(self):
        """Connect to SocketCAN interface."""
        self.transport.connect()

    def disconnect(self):
        """Disconnect from SocketCAN interface."""
        self.running = False
        self.transport.disconnect()

    def start(self, callback: Callable[[int, bytes, float], None]):
        """
        Start receiving CAN frames in background thread.

        Args:
            callback: Function called for each frame (can_id, raw_data, timestamp)
        """
        if self.running:
            return

        self._callback = callback
        self.running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop receiving CAN frames."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _receive_loop(self):
        """Internal receive loop running in background thread."""
        while self.running:
            try:
                frame = self.transport.receive(timeout=0.1)
                if frame and self._callback:
                    # Call callback with same signature as Demo/Replay
                    self._callback(frame.can_id, frame.data, frame.timestamp)
            except Exception as e:
                # Don't crash on individual frame errors
                print(f"Live CAN receive error: {e}")
                if not self.running:
                    break
