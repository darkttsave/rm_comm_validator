"""OpenMV Dart V1 UART profile: framing, signed offsets and semantic rules."""

import struct

import pytest

from protocol import Protocol
from decoder import Decoder
from serial_framer import SerialFramer
from validator import Validator


@pytest.fixture
def rig():
    protocol = Protocol("protocols/dart_openmv_v1.yaml")
    return protocol, Decoder(protocol), Validator(protocol)


def make_frame(state=2, valid=1, dx=15, dy=-10):
    return struct.pack(">2sBBhh", b"\\xff\\x01", state, valid, dx, dy)


def checks(rig, frame):
    _protocol, decoder, validator = rig
    decoded = decoder.decode_message("dart_visual_state", frame)
    return {r.check: r for r in validator.validate(decoded)}


def test_profile_has_expected_wire_contract(rig):
    protocol, decoder, _validator = rig
    assert protocol.transport.type == "serial"
    assert protocol.transport.baudrate == 115200
    assert protocol.transport.bytesize == 8
    assert protocol.transport.parity == "none"
    assert protocol.transport.stopbits == 1
    assert protocol.transport.header == b"\\xff\\x01"
    assert protocol.get_message_by_name("dart_visual_state").frame_length == 8
    data = make_frame()
    assert data == bytes.fromhex("FF 01 02 01 00 0F FF F6")
    decoded = decoder.decode_message("dart_visual_state", data)
    assert decoded.fields["state"] == 2
    assert decoded.fields["valid"] == 1
    assert decoded.fields["dx"] == 15
    assert decoded.fields["dy"] == -10
    assert all(v.passed for v in checks(rig, data).values())


@pytest.mark.parametrize(
    "state, valid, dx, dy",
    [
        (0, 0, 0, 0),
        (1, 0, 0, 0),
        (2, 0, 0, 0),
        (2, 1, -160, -120),
        (2, 1, 159, 119),
        (3, 0, 0, 0),
    ],
)
def test_valid_state_and_coordinate_boundaries(rig, state, valid, dx, dy):
    assert all(
        item.passed for item in checks(rig, make_frame(state, valid, dx, dy)).values()
    )


@pytest.mark.parametrize(
    "frame, failure",
    [
        (make_frame(4, 0, 0, 0), "STATE_ENUM"),
        (make_frame(2, 2, 0, 0), "VALID_ENUM"),
        (make_frame(0, 1, 0, 0), "VISION_OBSERVATION"),
        (make_frame(1, 1, 0, 0), "VISION_OBSERVATION"),
        (make_frame(3, 1, 0, 0), "VISION_OBSERVATION"),
        (make_frame(2, 0, 1, 0), "VISION_OBSERVATION"),
        (make_frame(2, 0, 0, -1), "VISION_OBSERVATION"),
        (make_frame(2, 1, 160, 0), "DX_RANGE"),
        (make_frame(2, 1, 0, -121), "DY_RANGE"),
        (bytes.fromhex("FF 02 02 01 00 00 00 00"), "MESSAGE_TYPE_ENUM"),
    ],
)
def test_rejects_illegal_observations(rig, frame, failure):
    assert not checks(rig, frame)[failure].passed


def test_ready_banner_and_split_frame_do_not_collide():
    framer = SerialFramer(header=b"\\xff\\x01", frame_length=8)
    # Original ready banner has a single 0xFF followed by ASCII RPDART.
    assert framer.feed(bytes.fromhex("FF 52 50 44 41 52 54")) == []
    frame = make_frame()
    assert framer.feed(b"\\xff") == []
    assert framer.feed(frame[1:4]) == []
    assert framer.feed(frame[4:]) == [frame]


def test_concatenated_and_noisy_stream():
    framer = SerialFramer(header=b"\\xff\\x01", frame_length=8)
    first = make_frame(0, 0, 0, 0)
    second = make_frame(2, 1, -12, 25)
    assert framer.feed(b"\\x99\\x55" + first + second) == [first, second]


def test_no_crc_cannot_reliably_detect_plausible_corruption(rig):
    # A one-bit change that still yields a legal coordinate passes all checks.
    original = make_frame(2, 1, 15, -10)
    modified = bytearray(original)
    modified[5] ^= 1
    assert modified != original
    assert all(v.passed for v in checks(rig, bytes(modified)).values())
