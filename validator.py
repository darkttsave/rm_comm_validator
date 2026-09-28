"""Message validator."""

import math
from dataclasses import dataclass
from typing import List, Dict, Any
from protocol import Protocol, Message
from decoder import DecodedMessage
from crc_algorithms import tongji_crc16


@dataclass
class ValidationResult:
    """Single validation check result."""
    check: str
    passed: bool
    message: str = ""


class Validator:
    """CAN message validator."""

    def __init__(self, protocol: Protocol):
        """Initialize validator with protocol definition."""
        self.protocol = protocol

    def validate(self, decoded: DecodedMessage) -> List[ValidationResult]:
        """
        Validate a decoded message.

        Returns:
            List of validation results
        """
        results = []

        # Get message definition by CAN ID or name
        if decoded.can_id is not None:
            message_def = self.protocol.get_message_by_id(decoded.can_id)
        else:
            message_def = self.protocol.get_message_by_name(decoded.message_name)

        if message_def is None:
            # Unknown message
            if decoded.can_id is not None:
                results.append(ValidationResult(
                    check="CAN_ID",
                    passed=False,
                    message=f"Unknown CAN ID: 0x{decoded.can_id:X}"
                ))
            else:
                results.append(ValidationResult(
                    check="MESSAGE",
                    passed=False,
                    message=f"Unknown message: {decoded.message_name}"
                ))
            return results

        # CAN-specific validations
        if decoded.can_id is not None:
            # CAN ID check
            results.append(ValidationResult(
                check="CAN_ID",
                passed=True,
                message=f"Known ID: {message_def.name}"
            ))

            # DLC check
            expected_dlc = message_def.dlc
            actual_dlc = decoded.dlc
            results.append(ValidationResult(
                check="DLC",
                passed=(actual_dlc == expected_dlc),
                message=f"Expected {expected_dlc}, got {actual_dlc}"
            ))

        # Serial-specific validations
        if decoded.frame_length is not None:
            # Frame length check
            expected_length = message_def.frame_length
            actual_length = decoded.frame_length
            results.append(ValidationResult(
                check="FRAME_LENGTH",
                passed=(actual_length == expected_length),
                message=f"Expected {expected_length}, got {actual_length}"
            ))

        # Enum checks
        for field in message_def.fields:
            if field.enum is not None:
                field_value = decoded.fields.get(field.name)
                if field_value is not None:
                    # Convert to int for enum check
                    field_value_int = int(field_value)
                    if field_value_int not in field.enum:
                        results.append(ValidationResult(
                            check=f"{field.name.upper()}_ENUM",
                            passed=False,
                            message=f"Invalid {field.name}: {field_value_int} not in enum"
                        ))
                    else:
                        results.append(ValidationResult(
                            check=f"{field.name.upper()}_ENUM",
                            passed=True,
                            message=f"{field.name}={field.enum[field_value_int]}"
                        ))

        # Custom validators
        for validator_def in message_def.validators:
            if validator_def.type == "quaternion_norm":
                result = self._validate_quaternion_norm(
                    decoded.fields,
                    validator_def.fields,
                    validator_def.tolerance or 0.01
                )
                results.append(result)
            elif validator_def.type == "crc16":
                result = self._validate_crc16(
                    decoded.raw,
                    validator_def.fields
                )
                results.append(result)

        return results

    def _validate_quaternion_norm(
        self,
        fields: Dict[str, Any],
        field_names: List[str],
        tolerance: float
    ) -> ValidationResult:
        """Validate quaternion norm."""
        try:
            # Extract quaternion components (w, x, y, z order in validator)
            w = fields.get(field_names[0], 0)
            x = fields.get(field_names[1], 0)
            y = fields.get(field_names[2], 0)
            z = fields.get(field_names[3], 0)

            # Calculate norm squared
            norm_sq = w*w + x*x + y*y + z*z
            error = abs(norm_sq - 1.0)

            passed = error <= tolerance

            return ValidationResult(
                check="QUAT_NORM",
                passed=passed,
                message=f"norm²={norm_sq:.6f}, error={error:.6f}"
            )
        except Exception as e:
            return ValidationResult(
                check="QUAT_NORM",
                passed=False,
                message=f"Error: {str(e)}"
            )

    def _validate_crc16(
        self,
        raw_data: bytes,
        field_names: List[str]
    ) -> ValidationResult:
        """
        Validate CRC16.

        Args:
            raw_data: Complete frame bytes
            field_names: List with algorithm name (e.g., ['tongji_crc16', 'offset:41'])
        """
        try:
            # Parse parameters
            algorithm = field_names[0] if len(field_names) > 0 else 'tongji_crc16'

            # Parse CRC offset if provided
            crc_offset = None
            if len(field_names) > 1 and field_names[1].startswith('offset:'):
                crc_offset = int(field_names[1].split(':')[1])

            # Default: CRC is last 2 bytes
            if crc_offset is None:
                crc_offset = len(raw_data) - 2

            # Extract received CRC (little-endian uint16)
            received_crc = int.from_bytes(
                raw_data[crc_offset:crc_offset + 2],
                byteorder='little'
            )

            # Calculate expected CRC over data before CRC field
            data_for_crc = raw_data[:crc_offset]

            if algorithm == 'tongji_crc16':
                expected_crc = tongji_crc16(data_for_crc)
            else:
                return ValidationResult(
                    check="CRC16",
                    passed=False,
                    message=f"Unknown CRC algorithm: {algorithm}"
                )

            passed = (received_crc == expected_crc)

            return ValidationResult(
                check="CRC16",
                passed=passed,
                message=f"Received: 0x{received_crc:04X}, Expected: 0x{expected_crc:04X}"
            )
        except Exception as e:
            return ValidationResult(
                check="CRC16",
                passed=False,
                message=f"Error: {str(e)}"
            )
