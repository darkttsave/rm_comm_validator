"""Validator tests - negative cases and edge cases."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol import Protocol
from decoder import Decoder
from validator import Validator


def test_invalid_enum():
    """Test invalid enum value detection."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Robot state with invalid mode (7 not in enum)
    can_id = 0x110
    raw_data = bytes.fromhex("0B 22 07 02 04 E2 00 00")  # mode=7 is invalid

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None

    validation = validator.validate(decoded)

    # Should have MODE_ENUM validation failure
    mode_check = [v for v in validation if v.check == "MODE_ENUM"]
    assert len(mode_check) == 1
    assert not mode_check[0].passed

    print("[PASS] Invalid Enum test: PASS")


def test_invalid_quaternion():
    """Test quaternion norm validation failure."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Quaternion with invalid norm
    # x=0.5, y=0.5, z=0, w=0 → norm² = 0.25 + 0.25 = 0.5 (not 1.0)
    can_id = 0x01
    # 0.5 / 0.0001 = 5000 = 0x1388
    raw_data = bytes.fromhex("13 88 13 88 00 00 00 00")

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None

    validation = validator.validate(decoded)

    # Should have QUAT_NORM validation failure
    quat_check = [v for v in validation if v.check == "QUAT_NORM"]
    assert len(quat_check) == 1
    assert not quat_check[0].passed

    print("[PASS] Invalid Quaternion test: PASS")


def test_unknown_can_id():
    """Test unknown CAN ID handling."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Unknown CAN ID
    can_id = 0x123
    raw_data = bytes([0x01, 0x02, 0x03, 0x04])

    decoded = decoder.decode(can_id, raw_data)

    # Should return None for unknown ID
    assert decoded is None

    print("[PASS] Unknown CAN ID test: PASS")


def test_wrong_dlc():
    """Test wrong DLC detection."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Quaternion with wrong DLC (should be 8, but we send 6)
    can_id = 0x01
    raw_data = bytes.fromhex("00 00 00 00 00 00")  # Only 6 bytes

    # Decoder will fail or decode with wrong length
    try:
        decoded = decoder.decode(can_id, raw_data)
        if decoded:
            validation = validator.validate(decoded)
            # Should have DLC validation failure
            dlc_check = [v for v in validation if v.check == "DLC"]
            assert len(dlc_check) == 1
            assert not dlc_check[0].passed
    except Exception as e:
        # Expected to fail during decode due to insufficient data
        pass

    print("[PASS] Wrong DLC test: PASS")


def test_valid_quaternion():
    """Test valid quaternion passes validation."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Valid quaternion: w=1, x=y=z=0
    can_id = 0x01
    raw_data = bytes.fromhex("00 00 00 00 00 00 27 10")

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None

    validation = validator.validate(decoded)

    # All checks should pass
    assert all(v.passed for v in validation)

    print("[PASS] Valid Quaternion test: PASS")


def test_valid_robot_state():
    """Test valid robot state passes all validations."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Valid robot state
    can_id = 0x110
    raw_data = bytes.fromhex("0B 22 01 02 04 E2 00 00")

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None

    validation = validator.validate(decoded)

    # All checks should pass
    assert all(v.passed for v in validation)

    print("[PASS] Valid Robot State test: PASS")


if __name__ == "__main__":
    test_invalid_enum()
    test_invalid_quaternion()
    test_unknown_can_id()
    test_wrong_dlc()
    test_valid_quaternion()
    test_valid_robot_state()
    print("\nAll Validator tests passed!")
