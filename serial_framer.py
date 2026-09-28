"""Serial frame extraction from byte stream."""

from typing import Optional, List


class SerialFramer:
    """
    Extract fixed-length frames from serial byte stream.

    Handles:
    - Partial frames (header or payload split across reads)
    - Multiple frames in one read
    - Noise before valid header
    - Header spanning two reads
    """

    def __init__(self, header: bytes, frame_length: int):
        """
        Initialize framer.

        Args:
            header: Frame header bytes (e.g., b'SP')
            frame_length: Total frame length including header
        """
        if len(header) == 0:
            raise ValueError("Header cannot be empty")
        if frame_length < len(header):
            raise ValueError("Frame length must be >= header length")

        self.header = header
        self.header_len = len(header)
        self.frame_length = frame_length
        self.buffer = bytearray()

    def feed(self, data: bytes) -> List[bytes]:
        """
        Feed new data to framer.

        Args:
            data: New bytes from serial port

        Returns:
            List of complete frames extracted (may be empty)
        """
        if not data:
            return []

        # Append to internal buffer
        self.buffer.extend(data)

        frames = []

        while True:
            # Need at least header_len bytes to search for header
            if len(self.buffer) < self.header_len:
                break

            # Find header
            header_pos = self.buffer.find(self.header)

            if header_pos == -1:
                # No header found
                # Keep last (header_len - 1) bytes in case header is split
                if len(self.buffer) >= self.header_len:
                    self.buffer = self.buffer[-(self.header_len - 1):]
                break

            # Discard bytes before header
            if header_pos > 0:
                self.buffer = self.buffer[header_pos:]

            # Check if we have a complete frame
            if len(self.buffer) < self.frame_length:
                # Incomplete frame, wait for more data
                break

            # Extract complete frame
            frame = bytes(self.buffer[:self.frame_length])
            frames.append(frame)

            # Remove frame from buffer
            self.buffer = self.buffer[self.frame_length:]

        return frames

    def reset(self):
        """Clear internal buffer."""
        self.buffer.clear()
