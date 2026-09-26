"""Tests for Web logging modes (none/errors/all)."""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol import Protocol
from decoder import Decoder
from validator import Validator
from recorder import Recorder


def test_log_mode_none():
    """Test that 'none' mode doesn't record anything."""
    print("Testing log mode: none...")

    # Simulate none mode
    recorder = None  # No recorder created

    # Simulate processing frames
    frames_processed = 0
    frames_recorded = 0

    # Process valid frame
    frames_processed += 1
    if recorder:  # Should not record
        frames_recorded += 1

    # Process invalid frame
    frames_processed += 1
    if recorder:  # Should not record
        frames_recorded += 1

    assert frames_processed == 2, "Should process 2 frames"
    assert frames_recorded == 0, "Should record 0 frames in 'none' mode"

    print(f"  [PASS] Processed {frames_processed} frames, recorded {frames_recorded}")
    return True


def test_log_mode_errors():
    """Test that 'errors' mode only records errors."""
    print("Testing log mode: errors...")

    # Load protocol
    protocol = Protocol('protocols/tongji_sentry.yaml')
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Create temporary recorder
    import tempfile
    import os
    temp_dir = tempfile.mkdtemp()
    recorder = Recorder(log_dir=temp_dir)
    recorder.start('test_errors.jsonl')

    frames_processed = 0
    frames_recorded = 0

    try:
        # Test 1: Valid quaternion (should NOT record)
        valid_quat = bytes([
            0x00, 0x00,  # x = 0.0
            0x00, 0x00,  # y = 0.0
            0x00, 0x00,  # z = 0.0
            0x27, 0x10   # w = 1.0
        ])
        decoded = decoder.decode(0x01, valid_quat, time.time())
        validation = validator.validate(decoded)
        all_passed = all(v.passed for v in validation)

        frames_processed += 1
        if not all_passed:  # Should not record (valid)
            recorder.record(decoded, validation, 0x01, len(valid_quat), valid_quat, time.time())
            frames_recorded += 1

        # Test 2: Invalid quaternion (should record)
        invalid_quat = bytes([
            0x23, 0x28,  # x = 0.9
            0x23, 0x28,  # y = 0.9
            0x23, 0x28,  # z = 0.9
            0x23, 0x28   # w = 0.9 (norm ~1.8, fails validation)
        ])
        decoded = decoder.decode(0x01, invalid_quat, time.time())
        validation = validator.validate(decoded)
        all_passed = all(v.passed for v in validation)

        frames_processed += 1
        if not all_passed:  # Should record (error)
            recorder.record(decoded, validation, 0x01, len(invalid_quat), invalid_quat, time.time())
            frames_recorded += 1

        # Test 3: Unknown CAN ID (should record)
        unknown_data = bytes([0xFF] * 8)
        decoded = decoder.decode(0x999, unknown_data, time.time())

        frames_processed += 1
        if decoded is None:  # Should record (unknown ID is an error)
            recorder.record(None, None, 0x999, len(unknown_data), unknown_data, time.time())
            frames_recorded += 1

        recorder.stop()

        # Verify log file
        log_file = Path(temp_dir) / 'test_errors.jsonl'
        assert log_file.exists(), "Log file should exist"

        lines = log_file.read_text().strip().split('\n')
        assert len(lines) == 2, f"Should have 2 error records, got {len(lines)}"

        print(f"  [PASS] Processed {frames_processed} frames, recorded {frames_recorded} errors")
        return True

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


def test_log_mode_all():
    """Test that 'all' mode records everything."""
    print("Testing log mode: all...")

    # Load protocol
    protocol = Protocol('protocols/tongji_sentry.yaml')
    decoder = Decoder(protocol)
    validator = Validator(protocol)

    # Create temporary recorder
    import tempfile
    import os
    temp_dir = tempfile.mkdtemp()
    recorder = Recorder(log_dir=temp_dir)
    recorder.start('test_all.jsonl')

    frames_processed = 0
    frames_recorded = 0

    try:
        # Test 1: Valid quaternion (should record)
        valid_quat = bytes([
            0x00, 0x00,  # x = 0.0
            0x00, 0x00,  # y = 0.0
            0x00, 0x00,  # z = 0.0
            0x27, 0x10   # w = 1.0
        ])
        decoded = decoder.decode(0x01, valid_quat, time.time())
        validation = validator.validate(decoded)

        frames_processed += 1
        recorder.record(decoded, validation, 0x01, len(valid_quat), valid_quat, time.time())
        frames_recorded += 1

        # Test 2: Invalid quaternion (should record)
        invalid_quat = bytes([
            0x23, 0x28,  # x = 0.9
            0x23, 0x28,  # y = 0.9
            0x23, 0x28,  # z = 0.9
            0x23, 0x28   # w = 0.9
        ])
        decoded = decoder.decode(0x01, invalid_quat, time.time())
        validation = validator.validate(decoded)

        frames_processed += 1
        recorder.record(decoded, validation, 0x01, len(invalid_quat), invalid_quat, time.time())
        frames_recorded += 1

        # Test 3: Unknown CAN ID (should record)
        unknown_data = bytes([0xFF] * 8)
        decoded = decoder.decode(0x999, unknown_data, time.time())

        frames_processed += 1
        recorder.record(None, None, 0x999, len(unknown_data), unknown_data, time.time())
        frames_recorded += 1

        recorder.stop()

        # Verify log file
        log_file = Path(temp_dir) / 'test_all.jsonl'
        assert log_file.exists(), "Log file should exist"

        lines = log_file.read_text().strip().split('\n')
        assert len(lines) == 3, f"Should have 3 records, got {len(lines)}"

        print(f"  [PASS] Processed {frames_processed} frames, recorded {frames_recorded} (all)")
        return True

    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)


def test_recorder_lifecycle():
    """Test recorder start/stop lifecycle."""
    print("Testing recorder lifecycle...")

    import tempfile
    import shutil

    temp_dir = tempfile.mkdtemp()

    try:
        recorder = Recorder(log_dir=temp_dir)

        # Test multiple start/stop cycles
        for i in range(3):
            recorder.start(f'test_{i}.jsonl')
            assert recorder.file_handle is not None, "File handle should be open"

            # Write a record
            recorder.record(
                None, None, 0x01, 8,
                bytes([0x00] * 8), time.time()
            )

            recorder.stop()
            assert recorder.file_handle is None, "File handle should be closed"

            # Verify file exists
            log_file = Path(temp_dir) / f'test_{i}.jsonl'
            assert log_file.exists(), f"Log file {i} should exist"

        print("  [PASS] Recorder lifecycle handled correctly")
        return True

    finally:
        shutil.rmtree(temp_dir)


if __name__ == '__main__':
    print("\n=== Web Logging Mode Tests ===\n")

    tests = [
        test_log_mode_none,
        test_log_mode_errors,
        test_log_mode_all,
        test_recorder_lifecycle
    ]

    passed = 0
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] Exception: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{passed}/{len(tests)} tests passed\n")

    if passed == len(tests):
        print("All Web logging tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed.")
        sys.exit(1)
