"""Tests for Serial infrastructure."""

import pytest
import struct
from serial_framer import SerialFramer
from crc_algorithms import tongji_crc16
from protocol import Protocol
from decoder import Decoder
from validator import Validator


class TestSerialFramer:
    """Test SerialFramer."""

    def test_complete_frame(self):
        """Test extracting a complete frame."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        # Create a complete frame
        data = b'SP' + b'\x00' * 41

        frames = framer.feed(data)
        assert len(frames) == 1
        assert frames[0] == data

    def test_split_header(self):
        """Test frame with header split across two reads."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        # First read: partial header
        frames = framer.feed(b'S')
        assert len(frames) == 0

        # Second read: rest of frame
        frames = framer.feed(b'P' + b'\x00' * 41)
        assert len(frames) == 1
        assert frames[0] == b'SP' + b'\x00' * 41

    def test_split_payload(self):
        """Test frame with payload split across reads."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        # First read: header + partial payload
        frames = framer.feed(b'SP' + b'\x00' * 20)
        assert len(frames) == 0

        # Second read: rest of payload
        frames = framer.feed(b'\x00' * 21)
        assert len(frames) == 1
        assert frames[0] == b'SP' + b'\x00' * 41

    def test_two_frames_in_one_read(self):
        """Test two complete frames in one read."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        frame1 = b'SP' + b'\x01' * 41
        frame2 = b'SP' + b'\x02' * 41

        frames = framer.feed(frame1 + frame2)
        assert len(frames) == 2
        assert frames[0] == frame1
        assert frames[1] == frame2

    def test_noise_before_header(self):
        """Test discarding noise before valid header."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        noise = b'\xFF\xFF\xFF'
        valid_frame = b'SP' + b'\x00' * 41

        frames = framer.feed(noise + valid_frame)
        assert len(frames) == 1
        assert frames[0] == valid_frame

    def test_consecutive_frames(self):
        """Test multiple consecutive frames."""
        framer = SerialFramer(header=b'SP', frame_length=43)

        frame1 = b'SP' + b'\x01' * 41
        frame2 = b'SP' + b'\x02' * 41
        frame3 = b'SP' + b'\x03' * 41

        frames1 = framer.feed(frame1)
        assert len(frames1) == 1

        frames2 = framer.feed(frame2 + frame3)
        assert len(frames2) == 2


class TestTongjiCRC16:
    """Test Tongji CRC16 algorithm."""

    def test_golden_vector(self):
        """Test against known golden vector."""
        # Golden vector from task specification
        data = bytearray()
        data.extend(b'SP')  # Header
        data.append(1)  # mode = 1

        # Quaternion: w=1, x=0, y=0, z=0
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))

        # Angles and velocities
        data.extend(struct.pack('<f', 0.1))    # yaw
        data.extend(struct.pack('<f', 0.2))    # yaw_vel
        data.extend(struct.pack('<f', -0.05))  # pitch
        data.extend(struct.pack('<f', 0.03))   # pitch_vel

        # Shooter
        data.extend(struct.pack('<f', 28.5))   # bullet_speed
        data.extend(struct.pack('<H', 123))    # bullet_count

        # Calculate CRC
        crc = tongji_crc16(bytes(data))

        # Expected CRC from specification
        assert crc == 0x3A8A

    def test_empty_data(self):
        """Test CRC of empty data."""
        crc = tongji_crc16(b'')
        assert crc == 0xFFFF  # Initial value

    def test_single_byte(self):
        """Test CRC of single byte."""
        crc = tongji_crc16(b'\x00')
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFF


class TestSerialProtocol:
    """Test Serial protocol loading."""

    def test_load_serial_protocol(self):
        """Test loading Tongji serial protocol."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')

        assert protocol.transport.type == 'serial'
        assert protocol.transport.baudrate == 9600
        assert protocol.transport.bytesize == 8
        assert protocol.transport.parity == 'none'

        # Check messages
        assert len(protocol.messages) >= 1

        # Find RX message
        rx_msg = None
        for msg in protocol.messages:
            if msg.direction == 'rx':
                rx_msg = msg
                break

        assert rx_msg is not None
        assert rx_msg.frame_length == 43

    def test_can_protocol_still_works(self):
        """Test that existing CAN protocol loading still works."""
        protocol = Protocol('protocols/tongji_sentry.yaml')

        assert protocol.transport.type == 'socketcan'
        assert protocol.transport.interface == 'can0'

        # Should have CAN messages with IDs
        for msg in protocol.messages:
            assert msg.id is not None
            assert msg.dlc is not None


class TestSerialDecoder:
    """Test Serial message decoding."""

    def test_decode_tongji_frame(self):
        """Test decoding a valid Tongji frame."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')
        decoder = Decoder(protocol)

        # Build a valid frame
        data = bytearray()
        data.extend(b'SP')
        data.append(1)  # mode

        # Quaternion
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))

        # Angles
        data.extend(struct.pack('<f', 0.1))
        data.extend(struct.pack('<f', 0.2))
        data.extend(struct.pack('<f', -0.05))
        data.extend(struct.pack('<f', 0.03))

        # Shooter
        data.extend(struct.pack('<f', 28.5))
        data.extend(struct.pack('<H', 123))

        # CRC
        crc = tongji_crc16(bytes(data))
        data.extend(struct.pack('<H', crc))

        # Decode
        decoded = decoder.decode_message('gimbal_to_vision', bytes(data), 1234.5)

        assert decoded is not None
        assert decoded.message_name == 'gimbal_to_vision'
        assert decoded.frame_length == 43
        assert decoded.fields['mode'] == 1
        assert decoded.fields['q_w'] == pytest.approx(1.0)
        assert decoded.fields['yaw'] == pytest.approx(0.1)


class TestSerialValidator:
    """Test Serial message validation."""

    def test_valid_crc(self):
        """Test validating correct CRC."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')
        decoder = Decoder(protocol)
        validator = Validator(protocol)

        # Build valid frame
        data = bytearray()
        data.extend(b'SP')
        data.append(1)
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.1))
        data.extend(struct.pack('<f', 0.2))
        data.extend(struct.pack('<f', -0.05))
        data.extend(struct.pack('<f', 0.03))
        data.extend(struct.pack('<f', 28.5))
        data.extend(struct.pack('<H', 123))

        crc = tongji_crc16(bytes(data))
        data.extend(struct.pack('<H', crc))

        decoded = decoder.decode_message('gimbal_to_vision', bytes(data))
        validation = validator.validate(decoded)

        # Find CRC16 check
        crc_check = None
        for v in validation:
            if v.check == 'CRC16':
                crc_check = v
                break

        assert crc_check is not None
        assert crc_check.passed is True

    def test_bad_crc(self):
        """Test detecting invalid CRC."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')
        decoder = Decoder(protocol)
        validator = Validator(protocol)

        # Build frame with bad CRC
        data = bytearray()
        data.extend(b'SP')
        data.append(1)
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.1))
        data.extend(struct.pack('<f', 0.2))
        data.extend(struct.pack('<f', -0.05))
        data.extend(struct.pack('<f', 0.03))
        data.extend(struct.pack('<f', 28.5))
        data.extend(struct.pack('<H', 123))

        # Bad CRC
        data.extend(struct.pack('<H', 0xFFFF))

        decoded = decoder.decode_message('gimbal_to_vision', bytes(data))
        validation = validator.validate(decoded)

        # Find CRC16 check
        crc_check = None
        for v in validation:
            if v.check == 'CRC16':
                crc_check = v
                break

        assert crc_check is not None
        assert crc_check.passed is False

    def test_invalid_mode(self):
        """Test detecting invalid mode enum."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')
        decoder = Decoder(protocol)
        validator = Validator(protocol)

        # Build frame with invalid mode
        data = bytearray()
        data.extend(b'SP')
        data.append(99)  # Invalid mode
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.1))
        data.extend(struct.pack('<f', 0.2))
        data.extend(struct.pack('<f', -0.05))
        data.extend(struct.pack('<f', 0.03))
        data.extend(struct.pack('<f', 28.5))
        data.extend(struct.pack('<H', 123))

        crc = tongji_crc16(bytes(data))
        data.extend(struct.pack('<H', crc))

        decoded = decoder.decode_message('gimbal_to_vision', bytes(data))
        validation = validator.validate(decoded)

        # Find mode enum check
        mode_check = None
        for v in validation:
            if 'MODE' in v.check and 'ENUM' in v.check:
                mode_check = v
                break

        assert mode_check is not None
        assert mode_check.passed is False

    def test_invalid_quaternion(self):
        """Test detecting non-normalized quaternion."""
        protocol = Protocol('protocols/tongji_gimbal_serial.yaml')
        decoder = Decoder(protocol)
        validator = Validator(protocol)

        # Build frame with non-normalized quaternion
        # (1, 1, 0, 0) has norm² = 2.0, not 1.0
        data = bytearray()
        data.extend(b'SP')
        data.append(1)
        data.extend(struct.pack('<f', 1.0))  # Not normalized (norm² = 2.0)
        data.extend(struct.pack('<f', 1.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.0))
        data.extend(struct.pack('<f', 0.1))
        data.extend(struct.pack('<f', 0.2))
        data.extend(struct.pack('<f', -0.05))
        data.extend(struct.pack('<f', 0.03))
        data.extend(struct.pack('<f', 28.5))
        data.extend(struct.pack('<H', 123))

        crc = tongji_crc16(bytes(data))
        data.extend(struct.pack('<H', crc))

        decoded = decoder.decode_message('gimbal_to_vision', bytes(data))
        validation = validator.validate(decoded)

        # Find quaternion check
        quat_check = None
        for v in validation:
            if v.check == 'QUAT_NORM':
                quat_check = v
                break

        assert quat_check is not None
        assert quat_check.passed is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
