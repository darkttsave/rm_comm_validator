"""Demo data source for testing without hardware."""

import time
import math
import random
from typing import Optional, Callable
from decoder import Encoder
from protocol import Protocol


class DemoSource:
    """Generate simulated CAN messages for demo purposes."""

    def __init__(self, protocol: Protocol):
        """Initialize demo source with protocol."""
        self.protocol = protocol
        self.encoder = Encoder(protocol)
        self.running = False
        self.error_injection = False

        # Simulation state
        self.time_offset = 0.0
        self.frame_count = 0

    def enable_error_injection(self, enabled: bool):
        """Enable/disable error injection."""
        self.error_injection = enabled

    def generate_quaternion(self) -> tuple:
        """Generate a valid quaternion with smooth rotation."""
        # Simple rotation around Z axis
        angle = (self.time_offset * 0.5) % (2 * math.pi)

        # Quaternion for rotation around Z axis
        half_angle = angle / 2
        w = math.cos(half_angle)
        x = 0.0
        y = 0.0
        z = math.sin(half_angle)

        # Add small noise
        x += random.gauss(0, 0.001)
        y += random.gauss(0, 0.001)

        # Normalize
        norm = math.sqrt(w*w + x*x + y*y + z*z)
        w, x, y, z = w/norm, x/norm, y/norm, z/norm

        # Error injection
        if self.error_injection and random.random() < 0.05:
            # Break normalization
            w *= 0.5

        return 0x01, {
            'w': w,
            'x': x,
            'y': y,
            'z': z
        }

    def generate_robot_state(self) -> tuple:
        """Generate robot state message."""
        # Varying bullet speed
        bullet_speed = 28.0 + math.sin(self.time_offset * 0.3) * 2.0

        # Mode cycles
        mode_cycle = int(self.time_offset * 0.1) % 5
        modes = [0, 1, 1, 2, 3]  # idle, auto_aim, auto_aim, small_buff, big_buff
        mode = modes[mode_cycle]

        # Shoot mode
        shoot_mode = random.choice([0, 1, 2])

        # FT angle varies
        ft_angle = math.sin(self.time_offset * 0.2) * 0.5

        # Error injection
        if self.error_injection and random.random() < 0.05:
            mode = 7  # Invalid enum value

        return 0x110, {
            'bullet_speed': bullet_speed,
            'mode': mode,
            'shoot_mode': shoot_mode,
            'ft_angle': ft_angle
        }

    def generate_unknown_id(self) -> Optional[tuple]:
        """Occasionally generate unknown CAN ID."""
        if self.error_injection and random.random() < 0.02:
            return 0x123, None
        return None

    def start(self, callback: Callable):
        """Start generating demo data."""
        self.running = True
        self.time_offset = 0.0
        self.frame_count = 0

        while self.running:
            current_time = time.time()

            # Generate messages at different rates
            # Quaternion: ~100Hz
            # Robot State: ~20Hz

            # Quaternion
            if self.frame_count % 1 == 0:
                can_id, fields = self.generate_quaternion()
                if fields:
                    raw_data = self.encoder.encode('quaternion', fields)
                    if raw_data:
                        callback(can_id, raw_data, current_time)

            # Robot State
            if self.frame_count % 5 == 0:
                can_id, fields = self.generate_robot_state()
                if fields:
                    raw_data = self.encoder.encode('robot_state', fields)
                    if raw_data:
                        callback(can_id, raw_data, current_time)

            # Unknown ID (rare)
            unknown = self.generate_unknown_id()
            if unknown:
                can_id, _ = unknown
                raw_data = bytes([0x01, 0x02, 0x03, 0x04])
                callback(can_id, raw_data, current_time)

            self.frame_count += 1
            self.time_offset += 0.01

            # Simulate timing (~100Hz)
            time.sleep(0.01)

    def stop(self):
        """Stop generating data."""
        self.running = False
