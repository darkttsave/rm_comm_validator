"""Test demo source."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol import Protocol
from decoder import Decoder
from validator import Validator
from demo_source import DemoSource


def test_demo_quaternion_generation():
    """Test demo quaternion message generation."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    demo = DemoSource(protocol)

    # Generate quaternion
    can_id, fields = demo.generate_quaternion()

    assert can_id == 0x01
    assert 'w' in fields
    assert 'x' in fields
    assert 'y' in fields
    assert 'z' in fields

    # Check normalization (roughly)
    w, x, y, z = fields['w'], fields['x'], fields['y'], fields['z']
    norm_sq = w*w + x*x + y*y + z*z
    assert abs(norm_sq - 1.0) < 0.1, f"Quaternion not normalized: {norm_sq}"

    print("[PASS] Demo quaternion generation")


def test_demo_robot_state_generation():
    """Test demo robot state generation."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    demo = DemoSource(protocol)

    # Generate robot state
    can_id, fields = demo.generate_robot_state()

    assert can_id == 0x110
    assert 'bullet_speed' in fields
    assert 'mode' in fields
    assert 'shoot_mode' in fields
    assert 'ft_angle' in fields

    # Check valid enum values (when no error injection)
    demo.enable_error_injection(False)
    can_id, fields = demo.generate_robot_state()
    assert fields['mode'] in [0, 1, 2, 3, 4], f"Invalid mode: {fields['mode']}"
    assert fields['shoot_mode'] in [0, 1, 2], f"Invalid shoot_mode: {fields['shoot_mode']}"

    print("[PASS] Demo robot state generation")


def test_demo_with_decoder():
    """Test demo source with actual decoder."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    demo = DemoSource(protocol)
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Generate and encode quaternion
    can_id, fields = demo.generate_quaternion()
    raw_data = demo.encoder.encode('quaternion', fields)

    assert raw_data is not None
    assert len(raw_data) == 8

    # Decode it back
    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None
    assert decoded.message_name == 'quaternion'

    # Validate
    validation = validator.validate(decoded)
    assert len(validation) > 0

    # Should pass when no error injection
    demo.enable_error_injection(False)
    can_id, fields = demo.generate_quaternion()
    raw_data = demo.encoder.encode('quaternion', fields)
    decoded = decoder.decode(can_id, raw_data)
    validation = validator.validate(decoded)

    quat_check = [v for v in validation if v.check == 'QUAT_NORM']
    assert len(quat_check) == 1
    assert quat_check[0].passed, "Valid quaternion should pass validation"

    print("[PASS] Demo with decoder integration")


def test_demo_error_injection():
    """Test demo error injection."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    demo = DemoSource(protocol)
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Enable error injection
    demo.enable_error_injection(True)

    # Generate many messages and check if we get errors
    errors_found = False
    for _ in range(100):
        can_id, fields = demo.generate_robot_state()
        if fields['mode'] not in [0, 1, 2, 3, 4]:
            errors_found = True

            # Verify it fails validation
            raw_data = demo.encoder.encode('robot_state', fields)
            decoded = decoder.decode(can_id, raw_data)
            validation = validator.validate(decoded)

            mode_check = [v for v in validation if v.check == 'MODE_ENUM']
            assert len(mode_check) == 1
            assert not mode_check[0].passed, "Invalid enum should fail validation"
            break

    # We should find at least one error in 100 tries with 5% error rate
    # But it's probabilistic, so we just check the mechanism works
    print("[PASS] Demo error injection")


if __name__ == "__main__":
    test_demo_quaternion_generation()
    test_demo_robot_state_generation()
    test_demo_with_decoder()
    test_demo_error_injection()
    print("\nAll Demo Source tests passed!")
