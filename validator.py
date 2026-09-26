"""Message validator."""

import math
from dataclasses import dataclass
from typing import List, Dict, Any
from protocol import Protocol, Message
from decoder import DecodedMessage


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

        # Get message definition
        message_def = self.protocol.get_message_by_id(decoded.can_id)

        if message_def is None:
            # Unknown CAN ID
            results.append(ValidationResult(
                check="CAN_ID",
                passed=False,
                message=f"Unknown CAN ID: 0x{decoded.can_id:X}"
            ))
            return results

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
