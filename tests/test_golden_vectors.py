"""Golden vector tests for decoder and encoder."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol import Protocol
from decoder import Decoder, Encoder


def test_golden_vector_a_quaternion():
    """Test Golden Vector A - Quaternion decoding."""
    # Load protocol
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)

    # Input raw data
    can_id = 0x01
    raw_data = bytes.fromhex("00 00 00 00 00 00 27 10")

    # Decode
    decoded = decoder.decode(can_id, raw_data)

    # Verify
    assert decoded is not None
    assert decoded.message_name == "quaternion"
    assert decoded.can_id == 0x01
    assert decoded.dlc == 8

    # Check fields
    assert decoded.fields["x"] == 0.0
    assert decoded.fields["y"] == 0.0
    assert decoded.fields["z"] == 0.0
    assert abs(decoded.fields["w"] - 1.0) < 0.0001

    print("[PASS] Golden Vector A (Quaternion)")


def test_golden_vector_b_robot_state():
    """Test Golden Vector B - Robot State decoding."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)

    # Input raw data
    can_id = 0x110
    raw_data = bytes.fromhex("0B 22 01 02 04 E2 00 00")

    # Decode
    decoded = decoder.decode(can_id, raw_data)

    # Verify
    assert decoded is not None
    assert decoded.message_name == "robot_state"
    assert decoded.can_id == 0x110
    assert decoded.dlc == 8

    # Check fields
    assert abs(decoded.fields["bullet_speed"] - 28.50) < 0.01
    assert decoded.fields["mode"] == 1
    assert decoded.fields["shoot_mode"] == 2
    assert abs(decoded.fields["ft_angle"] - 0.125) < 0.0001

    print("[PASS] Golden Vector B (Robot State): PASS")


def test_golden_vector_c_command_encoding():
    """Test Golden Vector C - Command encoding."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    encoder = Encoder(protocol)

    # Input fields
    fields = {
        "control": 1,
        "shoot": 0,
        "yaw": 1.0,
        "pitch": -0.5,
        "horizon_distance": 2.0
    }

    # Encode
    encoded = encoder.encode("command", fields)

    # Expected raw
    expected = bytes.fromhex("01 00 27 10 EC 78 4E 20")

    # Verify
    assert encoded is not None
    assert encoded == expected

    print("[PASS] Golden Vector C (Command Encode): PASS")


if __name__ == "__main__":
    test_golden_vector_a_quaternion()
    test_golden_vector_b_robot_state()
    test_golden_vector_c_command_encoding()
    print("\nAll Golden Vector tests passed!")
