"""Decoder tests."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from protocol import Protocol
from decoder import Decoder, Encoder


def test_decoder_basic():
    """Test basic decoder functionality."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)

    # Test quaternion
    can_id = 0x01
    raw_data = bytes.fromhex("00 00 00 00 00 00 27 10")

    decoded = decoder.decode(can_id, raw_data)

    assert decoded is not None
    assert decoded.message_name == "quaternion"
    assert decoded.can_id == 0x01
    assert len(decoded.fields) == 4

    print("[PASS] Basic decoder test: PASS")


def test_encoder_decoder_roundtrip():
    """Test encode-decode roundtrip."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    encoder = Encoder(protocol)
    decoder = Decoder(protocol)

    # Original fields
    original_fields = {
        "control": 1,
        "shoot": 0,
        "yaw": 1.5,
        "pitch": -0.3,
        "horizon_distance": 3.2
    }

    # Encode
    encoded = encoder.encode("command", original_fields)
    assert encoded is not None

    # Decode
    decoded = decoder.decode(0xFF, encoded)
    assert decoded is not None

    # Verify fields match (within precision limits)
    for key in original_fields:
        assert abs(decoded.fields[key] - original_fields[key]) < 0.001

    print("[PASS] Encoder-decoder roundtrip test: PASS")


def test_big_endian_decoding():
    """Test big-endian int16 decoding."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)

    # Test specific big-endian value
    # 0x0B22 = 2850 → 28.50 with scale 0.01
    can_id = 0x110
    raw_data = bytes.fromhex("0B 22 00 00 00 00 00 00")

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None
    assert abs(decoded.fields["bullet_speed"] - 28.50) < 0.01

    print("[PASS] Big-endian decoding test: PASS")


def test_negative_values():
    """Test negative value decoding."""
    protocol = Protocol("protocols/tongji_sentry.yaml")
    decoder = Decoder(protocol)

    # Test negative pitch
    # -0.5 / 0.0001 = -5000 = 0xEC78 (two's complement int16)
    can_id = 0xFF
    raw_data = bytes.fromhex("00 00 00 00 EC 78 00 00")

    decoded = decoder.decode(can_id, raw_data)
    assert decoded is not None
    assert abs(decoded.fields["pitch"] - (-0.5)) < 0.0001

    print("[PASS] Negative value decoding test: PASS")


if __name__ == "__main__":
    test_decoder_basic()
    test_encoder_decoder_roundtrip()
    test_big_endian_decoding()
    test_negative_values()
    print("\nAll Decoder tests passed!")
