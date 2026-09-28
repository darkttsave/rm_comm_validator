"""CAN message decoder and encoder."""

import struct
from dataclasses import dataclass
from typing import Dict, Any, Optional
from protocol import Protocol, Message, Field


@dataclass
class DecodedMessage:
    """Decoded message with all fields."""
    message_name: str
    raw: bytes
    fields: Dict[str, Any]
    timestamp: Optional[float] = None
    # CAN-specific (optional)
    can_id: Optional[int] = None
    dlc: Optional[int] = None
    # Serial-specific (optional)
    frame_length: Optional[int] = None


class Decoder:
    """CAN message decoder."""

    def __init__(self, protocol: Protocol):
        """Initialize decoder with protocol definition."""
        self.protocol = protocol

    def decode(self, can_id: int, data: bytes, timestamp: Optional[float] = None) -> Optional[DecodedMessage]:
        """
        Decode a CAN frame.

        Args:
            can_id: CAN ID
            data: Raw payload bytes
            timestamp: Optional timestamp

        Returns:
            DecodedMessage or None if unknown CAN ID
        """
        message_def = self.protocol.get_message_by_id(can_id)
        if message_def is None:
            return None

        fields = {}
        for field in message_def.fields:
            value = self._decode_field(data, field)
            fields[field.name] = value

        return DecodedMessage(
            message_name=message_def.name,
            can_id=can_id,
            dlc=len(data),
            raw=data,
            fields=fields,
            timestamp=timestamp
        )

    def decode_message(self, message_name: str, data: bytes, timestamp: Optional[float] = None) -> Optional[DecodedMessage]:
        """
        Decode a message by name (for Serial).

        Args:
            message_name: Message name from protocol
            data: Raw frame bytes
            timestamp: Optional timestamp

        Returns:
            DecodedMessage or None if unknown message name
        """
        message_def = self.protocol.get_message_by_name(message_name)
        if message_def is None:
            return None

        fields = {}
        for field in message_def.fields:
            value = self._decode_field(data, field)
            fields[field.name] = value

        return DecodedMessage(
            message_name=message_def.name,
            frame_length=len(data),
            raw=data,
            fields=fields,
            timestamp=timestamp
        )

    def _decode_field(self, data: bytes, field: Field) -> Any:
        """Decode a single field from raw data."""
        offset = field.offset
        field_type = field.type
        endian = '>' if field.endian == 'big' else '<'

        # Type mapping
        type_map = {
            'uint8': ('B', 1),
            'int8': ('b', 1),
            'uint16': ('H', 2),
            'int16': ('h', 2),
            'uint32': ('I', 4),
            'int32': ('i', 4),
            'float32': ('f', 4),
        }

        if field_type not in type_map:
            raise ValueError(f"Unsupported type: {field_type}")

        fmt_char, size = type_map[field_type]

        # For single-byte types, endianness doesn't matter
        if size == 1:
            endian = ''

        fmt = f"{endian}{fmt_char}"
        raw_value = struct.unpack(fmt, data[offset:offset + size])[0]

        # Apply scale
        decoded_value = raw_value * field.scale

        return decoded_value


class Encoder:
    """CAN message encoder."""

    def __init__(self, protocol: Protocol):
        """Initialize encoder with protocol definition."""
        self.protocol = protocol

    def encode(self, message_name: str, fields: Dict[str, Any]) -> Optional[bytes]:
        """
        Encode fields into CAN payload.

        Args:
            message_name: Message name from protocol
            fields: Dictionary of field values

        Returns:
            Raw bytes or None if message not found
        """
        # Find message by name
        message_def = None
        for msg in self.protocol.messages:
            if msg.name == message_name:
                message_def = msg
                break

        if message_def is None:
            return None

        # Create buffer
        data = bytearray(message_def.dlc)

        # Encode each field
        for field in message_def.fields:
            if field.name not in fields:
                continue

            value = fields[field.name]
            encoded = self._encode_field(value, field)
            offset = field.offset
            data[offset:offset + len(encoded)] = encoded

        return bytes(data)

    def _encode_field(self, value: Any, field: Field) -> bytes:
        """Encode a single field value to bytes."""
        endian = '>' if field.endian == 'big' else '<'

        # Reverse scale
        raw_value = value / field.scale

        # Type mapping
        type_map = {
            'uint8': ('B', 1),
            'int8': ('b', 1),
            'uint16': ('H', 2),
            'int16': ('h', 2),
            'uint32': ('I', 4),
            'int32': ('i', 4),
            'float32': ('f', 4),
        }

        if field.type not in type_map:
            raise ValueError(f"Unsupported type: {field.type}")

        fmt_char, size = type_map[field.type]

        # For single-byte types, endianness doesn't matter
        if size == 1:
            endian = ''

        fmt = f"{endian}{fmt_char}"

        # Convert to integer for integer types
        if field.type != 'float32':
            raw_value = int(round(raw_value))

        return struct.pack(fmt, raw_value)
