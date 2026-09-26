"""SocketCAN transport layer."""

import time
from typing import Optional, Callable
from dataclasses import dataclass


@dataclass
class CANFrame:
    """Raw CAN frame."""
    can_id: int
    dlc: int
    data: bytes
    timestamp: float


class CANTransport:
    """SocketCAN transport interface."""

    def __init__(self, interface: str = "can0"):
        """Initialize CAN transport."""
        self.interface = interface
        self.bus = None
        self._running = False

    def connect(self):
        """Connect to CAN interface."""
        try:
            import can
            self.bus = can.interface.Bus(
                channel=self.interface,
                bustype='socketcan'
            )
            print(f"Connected to {self.interface}")
        except Exception as e:
            raise RuntimeError(f"Failed to connect to {self.interface}: {e}")

    def disconnect(self):
        """Disconnect from CAN interface."""
        self._running = False
        if self.bus:
            self.bus.shutdown()
            self.bus = None

    def receive(self, timeout: Optional[float] = 1.0) -> Optional[CANFrame]:
        """
        Receive a single CAN frame.

        Args:
            timeout: Receive timeout in seconds

        Returns:
            CANFrame or None on timeout
        """
        if not self.bus:
            raise RuntimeError("Not connected")

        msg = self.bus.recv(timeout=timeout)
        if msg is None:
            return None

        return CANFrame(
            can_id=msg.arbitration_id,
            dlc=msg.dlc,
            data=bytes(msg.data),
            timestamp=msg.timestamp if msg.timestamp else time.time()
        )

    def send(self, can_id: int, data: bytes):
        """
        Send a CAN frame.

        Args:
            can_id: CAN ID
            data: Payload data
        """
        if not self.bus:
            raise RuntimeError("Not connected")

        import can
        msg = can.Message(
            arbitration_id=can_id,
            data=data,
            is_extended_id=False
        )
        self.bus.send(msg)

    def start_monitoring(self, callback: Callable[[CANFrame], None]):
        """
        Start continuous monitoring.

        Args:
            callback: Function called for each received frame
        """
        self._running = True
        while self._running:
            try:
                frame = self.receive(timeout=0.1)
                if frame:
                    callback(frame)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error receiving frame: {e}")

    def stop_monitoring(self):
        """Stop monitoring."""
        self._running = False
