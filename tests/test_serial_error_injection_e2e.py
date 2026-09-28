"""End-to-end protocol-level tests for Serial error injection modes.

Tests the complete flow: Mock frame → Decoder → Validator → Validation results.
Not just "Mock can start" but actual protocol semantics.
"""

import struct
import pytest
from pathlib import Path

# Import components for E2E testing
from serial_framer import SerialFramer
from decoder import Decoder
from validator import Validator


def tongji_crc16(data: bytes) -> int:
    """Tongji CRC16 implementation (same as mock_gimbal.py)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc = crc >> 1
    return crc & 0xFFFF


def build_mock_frame(mode, q_w, q_x, q_y, q_z, corrupt_crc=False):
    """Build a Tongji Gimbal frame matching mock_gimbal.py."""
    frame = bytearray([0x53, 0x50])  # Header: 'S' 'P'
    frame.append(mode)

    # Quaternion (4x float32, little-endian)
    frame.extend(struct.pack('<f', q_w))
    frame.extend(struct.pack('<f', q_x))
    frame.extend(struct.pack('<f', q_y))
    frame.extend(struct.pack('<f', q_z))

    # Gimbal angles and velocities
    frame.extend(struct.pack('<f', 0.1))    # yaw
    frame.extend(struct.pack('<f', 0.2))    # yaw_vel
    frame.extend(struct.pack('<f', -0.05))  # pitch
    frame.extend(struct.pack('<f', 0.03))   # pitch_vel

    # Shooter state
    frame.extend(struct.pack('<f', 28.5))   # bullet_speed
    frame.extend(struct.pack('<H', 123))    # bullet_count

    # CRC16
    crc = tongji_crc16(bytes(frame))
    if corrupt_crc:
        crc = 0xFFFF  # Corrupt CRC
    frame.extend(struct.pack('<H', crc))

    return bytes(frame)


@pytest.fixture
def protocol():
    """Load Tongji Gimbal Serial protocol."""
    import yaml
    protocol_path = Path(__file__).parent.parent / 'protocols' / 'tongji_gimbal_serial.yaml'
    with open(protocol_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


@pytest.fixture
def decoder(protocol):
    """Create decoder with Tongji protocol."""
    return Decoder(protocol)


@pytest.fixture
def validator(protocol):
    """Create validator with Tongji protocol."""
    return Validator(protocol)


@pytest.fixture
def framer(protocol):
    """Create framer with Tongji protocol transport config."""
    # Extract header from transport
    header_hex = protocol['transport']['header']
    header = bytes.fromhex(header_hex)
    # Extract frame_length from first RX message
    rx_message = [msg for msg in protocol['messages'] if msg['direction'] == 'rx'][0]
    frame_length = rx_message['frame_length']
    return SerialFramer(header=header, frame_length=frame_length)


# --------------------------------------------------------------------------
# Normal mode: all validations PASS
# --------------------------------------------------------------------------

def test_normal_mode_all_pass(framer, decoder, validator):
    """Normal mode: FRAME_LENGTH PASS, MODE_ENUM PASS, QUAT_NORM PASS, CRC16 PASS."""
    frame = build_mock_frame(
        mode=1,  # Valid AUTO_AIM
        q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0  # Normalized quaternion
    )

    # Framer extracts frame
    frames = framer.feed(frame)
    assert len(frames) == 1

    # Decoder parses
    messages = decoder.decode_frame(frames[0])
    assert len(messages) == 1
    msg = messages[0]
    assert msg['name'] == 'gimbal_to_vision'

    # Validator checks
    results = validator.validate(msg)

    # Check all validations PASS
    validation_map = {v['check']: v['passed'] for v in results}
    assert validation_map['FRAME_LENGTH'] is True
    assert validation_map['MODE_ENUM'] is True
    assert validation_map['QUAT_NORM'] is True
    assert validation_map['CRC16'] is True


# --------------------------------------------------------------------------
# Invalid mode: MODE_ENUM FAIL, others PASS
# --------------------------------------------------------------------------

def test_invalid_mode_enum_fail(framer, decoder, validator):
    """Invalid mode: MODE_ENUM FAIL, QUAT_NORM PASS, CRC16 PASS."""
    frame = build_mock_frame(
        mode=99,  # Invalid mode (valid range: 0-3)
        q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0
    )

    frames = framer.feed(frame)
    assert len(frames) == 1

    messages = decoder.decode_frame(frames[0])
    assert len(messages) == 1
    msg = messages[0]

    results = validator.validate(msg)
    validation_map = {v['check']: v['passed'] for v in results}

    # MODE_ENUM should FAIL
    assert validation_map['MODE_ENUM'] is False

    # Others should PASS
    assert validation_map['FRAME_LENGTH'] is True
    assert validation_map['QUAT_NORM'] is True
    assert validation_map['CRC16'] is True


# --------------------------------------------------------------------------
# Invalid quaternion: QUAT_NORM FAIL, others PASS
# --------------------------------------------------------------------------

def test_invalid_quaternion_norm_fail(framer, decoder, validator):
    """Invalid quaternion: QUAT_NORM FAIL, MODE_ENUM PASS, CRC16 PASS."""
    frame = build_mock_frame(
        mode=1,
        q_w=0.5, q_x=0.0, q_y=0.0, q_z=0.0  # norm^2 = 0.25, NOT 1.0
    )

    frames = framer.feed(frame)
    assert len(frames) == 1

    messages = decoder.decode_frame(frames[0])
    assert len(messages) == 1
    msg = messages[0]

    results = validator.validate(msg)
    validation_map = {v['check']: v['passed'] for v in results}

    # QUAT_NORM should FAIL
    assert validation_map['QUAT_NORM'] is False

    # Others should PASS
    assert validation_map['FRAME_LENGTH'] is True
    assert validation_map['MODE_ENUM'] is True
    assert validation_map['CRC16'] is True


# --------------------------------------------------------------------------
# Bad CRC: CRC16 FAIL, others PASS
# --------------------------------------------------------------------------

def test_bad_crc_fail(framer, decoder, validator):
    """Bad CRC: CRC16 FAIL, MODE_ENUM PASS, QUAT_NORM PASS."""
    frame = build_mock_frame(
        mode=1,
        q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0,
        corrupt_crc=True
    )

    frames = framer.feed(frame)
    assert len(frames) == 1

    messages = decoder.decode_frame(frames[0])
    assert len(messages) == 1
    msg = messages[0]

    results = validator.validate(msg)
    validation_map = {v['check']: v['passed'] for v in results}

    # CRC16 should FAIL
    assert validation_map['CRC16'] is False

    # Others should PASS (mode and quaternion are valid)
    assert validation_map['FRAME_LENGTH'] is True
    assert validation_map['MODE_ENUM'] is True
    assert validation_map['QUAT_NORM'] is True


# --------------------------------------------------------------------------
# Verify single-variable error injection principle
# --------------------------------------------------------------------------

def test_single_variable_error_injection():
    """Verify that error injection only affects one validation at a time."""
    protocol_path = Path(__file__).parent.parent / 'protocols' / 'tongji_gimbal_serial.yaml'
    import yaml
    with open(protocol_path, 'r', encoding='utf-8') as f:
        protocol = yaml.safe_load(f)

    header_hex = protocol['transport']['header']
    header = bytes.fromhex(header_hex)
    rx_message = [msg for msg in protocol['messages'] if msg['direction'] == 'rx'][0]
    frame_length = rx_message['frame_length']

    framer = SerialFramer(header=header, frame_length=frame_length)
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Test each error mode
    test_cases = [
        {
            'name': 'invalid_mode',
            'frame': build_mock_frame(mode=99, q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0),
            'expected_fail': 'MODE_ENUM'
        },
        {
            'name': 'invalid_quaternion',
            'frame': build_mock_frame(mode=1, q_w=0.5, q_x=0.0, q_y=0.0, q_z=0.0),
            'expected_fail': 'QUAT_NORM'
        },
        {
            'name': 'bad_crc',
            'frame': build_mock_frame(mode=1, q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0, corrupt_crc=True),
            'expected_fail': 'CRC16'
        }
    ]

    for case in test_cases:
        frames = framer.feed(case['frame'])
        messages = decoder.decode_frame(frames[0])
        results = validator.validate(messages[0])

        validation_map = {v['check']: v['passed'] for v in results}

        # Count failures
        failures = [check for check, passed in validation_map.items() if not passed]

        # Should have exactly ONE failure
        assert len(failures) == 1, f"{case['name']}: expected 1 failure, got {len(failures)}: {failures}"
        assert failures[0] == case['expected_fail'], f"{case['name']}: expected {case['expected_fail']} to fail"
