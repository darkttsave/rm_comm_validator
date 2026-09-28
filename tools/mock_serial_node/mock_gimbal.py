#!/usr/bin/env python3
"""Mock Tongji Gimbal Serial Node for testing."""

import time
import struct
import sys


def tongji_crc16(data: bytes) -> int:
    """
    Tongji CRC16 algorithm.

    Independent implementation for mock - NOT imported from validator.
    """
    crc = 0xFFFF

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc = crc >> 1

    return crc & 0xFFFF


def build_frame(mode, q_w, q_x, q_y, q_z, yaw, yaw_vel, pitch, pitch_vel, bullet_speed, bullet_count):
    """Build a Tongji Gimbal RX frame."""
    # Header: 'S' 'P'
    frame = bytearray([0x53, 0x50])

    # Mode (uint8)
    frame.append(mode)

    # Quaternion (4x float32, little-endian)
    frame.extend(struct.pack('<f', q_w))
    frame.extend(struct.pack('<f', q_x))
    frame.extend(struct.pack('<f', q_y))
    frame.extend(struct.pack('<f', q_z))

    # Gimbal angles and velocities (4x float32, little-endian)
    frame.extend(struct.pack('<f', yaw))
    frame.extend(struct.pack('<f', yaw_vel))
    frame.extend(struct.pack('<f', pitch))
    frame.extend(struct.pack('<f', pitch_vel))

    # Shooter state
    frame.extend(struct.pack('<f', bullet_speed))
    frame.extend(struct.pack('<H', bullet_count))

    # Calculate CRC16 over first 41 bytes
    crc = tongji_crc16(bytes(frame))

    # Append CRC16 (little-endian)
    frame.extend(struct.pack('<H', crc))

    return bytes(frame)


def run_mock(port, mode='normal', rate_hz=10):
    """Run mock gimbal node."""
    try:
        import serial
    except ImportError:
        print("Error: pyserial not installed. Run: pip install pyserial")
        sys.exit(1)

    try:
        ser = serial.Serial(port, baudrate=9600, timeout=1)
        print(f"Mock Gimbal connected to {port}")
        print(f"Mode: {mode}, Rate: {rate_hz} Hz")
        print("Press Ctrl+C to stop")

        frame_count = 0

        while True:
            if mode == 'normal':
                # Normal operation
                frame = build_frame(
                    mode=1,  # AUTO_AIM
                    q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0,
                    yaw=0.1 + frame_count * 0.01,
                    yaw_vel=0.2,
                    pitch=-0.05,
                    pitch_vel=0.03,
                    bullet_speed=28.5,
                    bullet_count=100 - frame_count % 100
                )

            elif mode == 'invalid_mode':
                # Invalid mode enum
                frame = build_frame(
                    mode=99,  # Invalid
                    q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0,
                    yaw=0.1, yaw_vel=0.2,
                    pitch=-0.05, pitch_vel=0.03,
                    bullet_speed=28.5, bullet_count=123
                )

            elif mode == 'invalid_quaternion':
                # Invalid quaternion (not normalized)
                frame = build_frame(
                    mode=1,
                    q_w=0.5, q_x=0.5, q_y=0.5, q_z=0.5,  # norm^2 = 1.0 but individual components wrong
                    yaw=0.1, yaw_vel=0.2,
                    pitch=-0.05, pitch_vel=0.03,
                    bullet_speed=28.5, bullet_count=123
                )

            elif mode == 'bad_crc':
                # Corrupted CRC
                frame = build_frame(
                    mode=1,
                    q_w=1.0, q_x=0.0, q_y=0.0, q_z=0.0,
                    yaw=0.1, yaw_vel=0.2,
                    pitch=-0.05, pitch_vel=0.03,
                    bullet_speed=28.5, bullet_count=123
                )
                # Corrupt last 2 bytes (CRC)
                frame = frame[:-2] + b'\xFF\xFF'

            else:
                print(f"Unknown mode: {mode}")
                sys.exit(1)

            ser.write(frame)
            frame_count += 1

            if frame_count % 10 == 0:
                print(f"Sent {frame_count} frames...")

            time.sleep(1.0 / rate_hz)

    except KeyboardInterrupt:
        print("\nStopping mock gimbal")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if 'ser' in locals():
            ser.close()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Mock Tongji Gimbal Serial Node')
    parser.add_argument('port', help='Serial port (e.g., /dev/pts/3, COM3)')
    parser.add_argument('--mode', choices=['normal', 'invalid_mode', 'invalid_quaternion', 'bad_crc'],
                        default='normal', help='Test mode')
    parser.add_argument('--rate', type=int, default=10, help='Frame rate in Hz')

    args = parser.parse_args()

    run_mock(args.port, mode=args.mode, rate_hz=args.rate)
