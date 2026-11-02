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
            elif validator_def.type == "range":
                # Optional numeric range rule, enabled only by protocol YAML.
                # fields: [field_name, inclusive_min, inclusive_max]
                try:
                    name, low, high = validator_def.fields
                    value = decoded.fields[name]
                    low, high = float(low), float(high)
                    passed = low <= value <= high
                    results.append(ValidationResult(
                        check=f"{name.upper()}_RANGE",
                        passed=passed,
                        message=f"{name}={value}, allowed [{low:g}, {high:g}]"
                    ))
                except (KeyError, TypeError, ValueError) as exc:
                    results.append(ValidationResult(
                        check="RANGE",
                        passed=False,
                        message=f"Invalid range rule: {exc}"
                    ))
            elif validator_def.type == "vision_observation":
                # Protocol-specific semantic rule with configurable field names;
                # no effect on existing protocols unless explicitly requested.
                # fields: [state, valid, dx, dy, search_state_value]
                try:
                    state_key, valid_key, dx_key, dy_key, search_state = validator_def.fields
                    state_value = decoded.fields[state_key]
                    valid_value = decoded.fields[valid_key]
                    dx_value = decoded.fields[dx_key]
                    dy_value = decoded.fields[dy_key]
                    search_state = int(search_state)
                    passed = (
                        valid_value in (0, 1)
                        and (valid_value == 0 or state_value == search_state)
                        and (valid_value == 1 or (dx_value == 0 and dy_value == 0))
                    )
                    results.append(ValidationResult(
                        check="VISION_OBSERVATION",
                        passed=passed,
                        message=(
                            f"state={state_value}, valid={valid_value}, "
                            f"dx={dx_value}, dy={dy_value}; "
                            f"valid=1 requires state={search_state}, "
                            "valid=0 requires zero offsets"
                        )
                    ))
                except (KeyError, TypeError, ValueError) as exc:
                    results.append(ValidationResult(
                        check="VISION_OBSERVATION",
                        passed=False,
                        message=f"Invalid observation rule: {exc}"
                    ))

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
