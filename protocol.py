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
    """CAN message definition."""
    name: str
    direction: str  # rx or tx
    id: int
    dlc: int
    description: str = ""
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
    type: str
    interface: str


class Protocol:
    """Protocol definition manager."""

    def __init__(self, filepath: str):
        """Load protocol from YAML file."""
        self.filepath = filepath
        with open(filepath, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Load transport
        transport_data = data.get('transport', {})
        self.transport = Transport(
            type=transport_data.get('type', 'socketcan'),
            interface=transport_data.get('interface', 'can0')
        )

        # Load messages
        self.messages: List[Message] = []
        self.messages_by_id: Dict[int, Message] = {}

        for msg_data in data.get('messages', []):
            msg = self._load_message(msg_data)
            self.messages.append(msg)
            self.messages_by_id[msg.id] = msg

    def _load_message(self, data: Dict[str, Any]) -> Message:
        """Load a single message definition."""
        # Parse CAN ID (support hex string)
        can_id_str = data['id']
        if isinstance(can_id_str, str):
            can_id = int(can_id_str, 16)
        else:
            can_id = can_id_str

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
