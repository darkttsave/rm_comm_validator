"""Live Serial data source for Web UI."""

import threading
import time
from typing import Callable, Optional
from serial_transport import SerialTransport
from serial_framer import SerialFramer


class LiveSerialSource:
    """Live Serial data source."""

    def __init__(
        self,
        port: str,
        baudrate: int,
        header: bytes,
        frame_length: int,
        bytesize: int = 8,
        parity: str = 'N',
        stopbits: int = 1,
        timeout_ms: int = 20
    ):
        """
        Initialize Live Serial source.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0', 'COM3')
            baudrate: Baud rate
            header: Frame header bytes
            frame_length: Total frame length
            bytesize: Data bits
            parity: Parity
            stopbits: Stop bits
            timeout_ms: Read timeout in milliseconds
        """
        self.port = port
        self.transport = SerialTransport(
            port=port,
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout_ms=timeout_ms
        )
        self.framer = SerialFramer(header=header, frame_length=frame_length)
        self.running = False
        self._thread = None
        self._callback = None

    def connect(self):
        """Connect to serial port."""
        self.transport.connect()

    def disconnect(self):
        """Disconnect from serial port."""
        self.running = False
        self.transport.disconnect()

    def start(self, callback: Callable[[bytes, float], None]):
        """
        Start receiving serial frames in background thread.

        Args:
            callback: Function called for each complete frame (raw_data, timestamp)
        """
        if self.running:
            return

        self._callback = callback
        self.running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop receiving serial frames."""
        self.running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _receive_loop(self):
        """Internal receive loop running in background thread."""
        while self.running:
            try:
                # Read available bytes
                chunk = self.transport.read_available()

                if not chunk:
                    # No data available, small sleep to avoid busy loop
                    time.sleep(0.001)
                    continue

                # Feed to framer
                frames = self.framer.feed(chunk)

                # Process complete frames
                timestamp = time.time()
                for frame in frames:
                    if self._callback:
                        self._callback(frame, timestamp)

            except Exception as e:
                # Don't crash on individual errors
                print(f"Live Serial receive error: {e}")
                if not self.running:
                    break
