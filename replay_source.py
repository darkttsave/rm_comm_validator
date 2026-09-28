"""Replay data source from JSONL logs."""

import json
import time
from typing import Callable, Optional


class ReplaySource:
    """Replay CAN and Serial messages from JSONL log files."""

    def __init__(self, jsonl_path: str):
        """Initialize replay source with log file."""
        self.jsonl_path = jsonl_path
        self.running = False
        self.paused = False
        self.speed = 1.0
        self.records = []
        self.current_index = 0

        # Load records
        self._load_records()

    def _load_records(self):
        """Load all records from JSONL file."""
        self.records = []
        try:
            with open(self.jsonl_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        record = json.loads(line)
                        self.records.append(record)
        except FileNotFoundError:
            raise ValueError(f"Log file not found: {self.jsonl_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in log file: {e}")

    def start(self, callback: Callable):
        """Start replaying data."""
        if not self.records:
            return

        self.running = True
        self.current_index = 0

        # Get first timestamp as base
        base_timestamp = self.records[0]['timestamp']
        start_time = time.time()

        while self.running and self.current_index < len(self.records):
            if self.paused:
                time.sleep(0.1)
                continue

            record = self.records[self.current_index]

            # Calculate when this frame should be played
            record_offset = record['timestamp'] - base_timestamp
            target_time = start_time + (record_offset / self.speed)

            # Wait until target time
            now = time.time()
            sleep_time = target_time - now
            if sleep_time > 0:
                time.sleep(sleep_time)

            # Extract raw data
            raw_hex = record['raw'].replace(' ', '')
            raw_data = bytes.fromhex(raw_hex)

            # Determine transport type (backward compatibility)
            transport = record.get('transport', 'can')  # Default to CAN for old logs

            if transport == 'can' or 'can_id' in record:
                # CAN message
                can_id = int(record['can_id'], 16)
                callback(can_id, raw_data, record['timestamp'])
            else:
                # Serial message - callback expects (message_name, raw_data, timestamp)
                # For serial replay, we need the message name from the log
                message_name = record.get('message', 'unknown')
                callback(message_name, raw_data, record['timestamp'])

            self.current_index += 1

        self.running = False

    def stop(self):
        """Stop replay."""
        self.running = False

    def pause(self):
        """Pause replay."""
        self.paused = True

    def resume(self):
        """Resume replay."""
        self.paused = False

    def set_speed(self, speed: float):
        """Set playback speed (1.0 = normal, 2.0 = 2x)."""
        self.speed = max(0.1, min(speed, 10.0))

    def get_progress(self) -> dict:
        """Get current replay progress."""
        if not self.records:
            return {
                'current': 0,
                'total': 0,
                'percentage': 0.0
            }

        return {
            'current': self.current_index,
            'total': len(self.records),
            'percentage': (self.current_index / len(self.records)) * 100 if self.records else 0.0
        }
