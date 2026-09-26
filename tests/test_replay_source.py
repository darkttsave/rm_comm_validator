"""Test replay source."""

import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from replay_source import ReplaySource


def create_test_jsonl():
    """Create a temporary JSONL file for testing."""
    # Create test data
    records = [
        {
            "timestamp": 1695707823.0,
            "direction": "rx",
            "can_id": "0x01",
            "dlc": 8,
            "raw": "00 00 00 00 00 00 27 10",
            "message": "quaternion",
            "valid": True
        },
        {
            "timestamp": 1695707823.1,
            "direction": "rx",
            "can_id": "0x110",
            "dlc": 8,
            "raw": "0B 22 01 02 04 E2 00 00",
            "message": "robot_state",
            "valid": True
        },
        {
            "timestamp": 1695707823.2,
            "direction": "rx",
            "can_id": "0x01",
            "dlc": 8,
            "raw": "00 05 FF FB 00 03 27 0F",
            "message": "quaternion",
            "valid": True
        }
    ]

    # Write to temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        for record in records:
            f.write(json.dumps(record) + '\n')
        return f.name


def test_replay_load():
    """Test loading JSONL file."""
    jsonl_path = create_test_jsonl()

    try:
        replay = ReplaySource(jsonl_path)

        assert len(replay.records) == 3
        assert replay.records[0]['can_id'] == '0x01'
        assert replay.records[1]['can_id'] == '0x110'

        print("[PASS] Replay load")
    finally:
        os.unlink(jsonl_path)


def test_replay_progress():
    """Test replay progress tracking."""
    jsonl_path = create_test_jsonl()

    try:
        replay = ReplaySource(jsonl_path)

        progress = replay.get_progress()
        assert progress['current'] == 0
        assert progress['total'] == 3
        assert progress['percentage'] == 0.0

        print("[PASS] Replay progress")
    finally:
        os.unlink(jsonl_path)


def test_replay_playback():
    """Test replay playback."""
    jsonl_path = create_test_jsonl()

    try:
        replay = ReplaySource(jsonl_path)

        frames_received = []

        def callback(can_id, raw_data, timestamp):
            frames_received.append({
                'can_id': can_id,
                'raw_data': raw_data,
                'timestamp': timestamp
            })

            # Stop after receiving all frames
            if len(frames_received) >= 3:
                replay.stop()

        # Start replay
        replay.start(callback)

        # Check we received all frames
        assert len(frames_received) == 3
        assert frames_received[0]['can_id'] == 0x01
        assert frames_received[1]['can_id'] == 0x110
        assert frames_received[2]['can_id'] == 0x01

        # Check data is correct
        assert frames_received[0]['raw_data'] == bytes.fromhex('00 00 00 00 00 00 27 10')
        assert frames_received[1]['raw_data'] == bytes.fromhex('0B 22 01 02 04 E2 00 00')

        print("[PASS] Replay playback")
    finally:
        os.unlink(jsonl_path)


def test_replay_no_modify_original():
    """Test that replay doesn't modify original file."""
    jsonl_path = create_test_jsonl()

    try:
        # Read original content
        with open(jsonl_path, 'r') as f:
            original_content = f.read()

        # Run replay
        replay = ReplaySource(jsonl_path)

        frames_received = []
        def callback(can_id, raw_data, timestamp):
            frames_received.append(can_id)
            if len(frames_received) >= 3:
                replay.stop()

        replay.start(callback)

        # Check original file unchanged
        with open(jsonl_path, 'r') as f:
            new_content = f.read()

        assert original_content == new_content, "Original file was modified!"

        print("[PASS] Replay doesn't modify original")
    finally:
        os.unlink(jsonl_path)


if __name__ == "__main__":
    test_replay_load()
    test_replay_progress()
    test_replay_playback()
    test_replay_no_modify_original()
    print("\nAll Replay Source tests passed!")
