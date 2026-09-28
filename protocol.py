"""Protocol definition loader and manager."""

import yaml
from dataclasses import dataclass
from typing import Dict, List, Optional, Any


@dataclass
class Field:
    """Protocol field definition."""
    name: str
    offset: int
    type: str
    endian: str = "big"
    scale: float = 1.0
    enum: Optional[Dict[int, str]] = None


@dataclass
class Validator:
    """Message validator definition."""
    type: str
    fields: Optional[List[str]] = None
    tolerance: Optional[float] = None


@dataclass
class Message:
    """Message definition (CAN or Serial)."""
    name: str
    direction: str  # rx or tx
    description: str = ""
    # CAN-specific
    id: Optional[int] = None
    dlc: Optional[int] = None
    # Serial-specific
    frame_length: Optional[int] = None
    # Common
    fields: List[Field] = None
    validators: List[Validator] = None

    def __post_init__(self):
        if self.fields is None:
            self.fields = []
        if self.validators is None:
            self.validators = []


@dataclass
class Transport:
    """Transport configuration."""
    type: str  # 'socketcan' or 'serial'
    # CAN-specific
    interface: Optional[str] = None
    # Serial-specific
    port: Optional[str] = None
    baudrate: Optional[int] = None
    bytesize: Optional[int] = None
    parity: Optional[str] = None
    stopbits: Optional[int] = None
    timeout_ms: Optional[int] = None


class Protocol:
    """Protocol definition manager."""

    def __init__(self, filepath: str):
        """Load protocol from YAML file."""
        self.filepath = filepath
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Load transport
        transport_data = data.get('transport', {})
        transport_type = transport_data.get('type', 'socketcan')

        if transport_type == 'serial':
            self.transport = Transport(
                type='serial',
                port=transport_data.get('port'),
                baudrate=transport_data.get('baudrate', 9600),
                bytesize=transport_data.get('bytesize', 8),
                parity=transport_data.get('parity', 'none'),
                stopbits=transport_data.get('stopbits', 1),
                timeout_ms=transport_data.get('timeout_ms', 20)
            )
        else:
            # CAN transport
            self.transport = Transport(
                type='socketcan',
                interface=transport_data.get('interface', 'can0')
            )

        # Load messages
        self.messages: List[Message] = []
        self.messages_by_id: Dict[int, Message] = {}
        self.messages_by_name: Dict[str, Message] = {}

        for msg_data in data.get('messages', []):
            msg = self._load_message(msg_data, transport_type)
            self.messages.append(msg)
            if msg.id is not None:
                self.messages_by_id[msg.id] = msg
            self.messages_by_name[msg.name] = msg

    def _load_message(self, data: Dict[str, Any], transport_type: str) -> Message:
        """Load a single message definition."""
        # Load fields
        fields = []
        for field_data in data.get('fields', []):
            field = Field(
                name=field_data['name'],
                offset=field_data['offset'],
                type=field_data['type'],
                endian=field_data.get('endian', 'big'),
                scale=field_data.get('scale', 1.0),
                enum=field_data.get('enum')
            )
            fields.append(field)

        # Load validators
        validators = []
        for val_data in data.get('validators', []):
            validator = Validator(
                type=val_data['type'],
                fields=val_data.get('fields'),
                tolerance=val_data.get('tolerance')
            )
            validators.append(validator)

        # Parse based on transport type
        if transport_type == 'serial':
            # Serial message
            return Message(
                name=data['name'],
                direction=data['direction'],
                frame_length=data['frame_length'],
                description=data.get('description', ''),
                fields=fields,
                validators=validators
            )
        else:
            # CAN message
            # Parse CAN ID (support hex string)
            can_id_str = data['id']
            if isinstance(can_id_str, str):
                can_id = int(can_id_str, 16)
            else:
                can_id = can_id_str

            return Message(
                name=data['name'],
                direction=data['direction'],
                id=can_id,
                dlc=data['dlc'],
                description=data.get('description', ''),
                fields=fields,
                validators=validators
            )

    def get_message_by_id(self, can_id: int) -> Optional[Message]:
        """Get message definition by CAN ID."""
        return self.messages_by_id.get(can_id)

    def get_message_by_name(self, name: str) -> Optional[Message]:
        """Get message definition by name."""
        return self.messages_by_name.get(name)
