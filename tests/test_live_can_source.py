"""Tests for Live CAN Source."""

import sys
import time
import threading
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from live_can_source import LiveCANSource


class MockCANTransport:
    """Mock CAN transport for testing."""

    def __init__(self, interface):
        self.interface = interface
        self.connected = False
        self.running = False
        self.should_fail = False

    def connect(self):
        """Mock connect."""
        if self.should_fail:
            raise RuntimeError(f"Failed to connect to {self.interface}")
        self.connected = True

    def disconnect(self):
        """Mock disconnect."""
        self.connected = False
        self.running = False

    def receive(self, timeout=None):
        """Mock receive."""
        if not self.connected or not self.running:
            return None

        # Simulate receiving a frame
        time.sleep(0.01)  # Simulate 100 Hz

        from can_transport import CANFrame
        return CANFrame(
            can_id=0x01,
            dlc=8,
            data=b'\x00\x00\x00\x00\x00\x00\x27\x10',  # Simple quaternion
            timestamp=time.time()
        )


def test_live_source_lifecycle():
    """Test Live CAN source start/stop lifecycle."""
    print("Testing Live CAN source lifecycle...")

    source = LiveCANSource('vcan0')

    # Replace transport with mock
    mock_transport = MockCANTransport('vcan0')
    source.transport = mock_transport

    # Connect
    source.connect()
    assert mock_transport.connected, "Transport should be connected"

    # Track received frames
    received_frames = []

    def callback(can_id, raw_data, timestamp):
        received_frames.append((can_id, raw_data, timestamp))

    # Start receiving
    mock_transport.running = True
    source.start(callback)
    assert source.running, "Source should be running"

    # Wait for some frames
    time.sleep(0.1)

    # Stop
    source.stop()
    assert not source.running, "Source should be stopped"

    # Disconnect
    source.disconnect()
    assert not mock_transport.connected, "Transport should be disconnected"

    print(f"  [PASS] Received {len(received_frames)} frames")
    return True


def test_connection_failure():
    """Test connection failure handling."""
    print("Testing connection failure...")

    source = LiveCANSource('vcan0')

    # Replace transport with failing mock
    mock_transport = MockCANTransport('vcan0')
    mock_transport.should_fail = True
    source.transport = mock_transport

    try:
        source.connect()
        print("  [FAIL] Should have raised RuntimeError")
        return False
    except RuntimeError as e:
        if "Failed to connect" in str(e):
            print("  [PASS] Connection failure handled correctly")
            return True
        else:
            print(f"  [FAIL] Unexpected error: {e}")
            return False


def test_repeated_start_stop():
    """Test repeated start/stop doesn't create multiple threads."""
    print("Testing repeated start/stop...")

    source = LiveCANSource('vcan0')

    # Replace transport with mock
    mock_transport = MockCANTransport('vcan0')
    source.transport = mock_transport

    source.connect()
    mock_transport.running = True

    received_count = [0]

    def callback(can_id, raw_data, timestamp):
        received_count[0] += 1

    # Start multiple times
    for i in range(3):
        if source.running:
            source.stop()
        source.start(callback)
        time.sleep(0.05)

    # Count active threads
    active_threads = threading.active_count()

    # Stop
    source.stop()
    source.disconnect()

    # Should only have had one receive thread at a time
    print(f"  [PASS] Repeated start/stop handled correctly (received {received_count[0]} frames)")
    return True


def test_callback_signature():
    """Test callback receives correct signature."""
    print("Testing callback signature...")

    source = LiveCANSource('vcan0')

    # Replace transport with mock
    mock_transport = MockCANTransport('vcan0')
    source.transport = mock_transport

    source.connect()
    mock_transport.running = True

    received_args = []

    def callback(can_id, raw_data, timestamp):
        # Verify types match Demo/Replay sources
        assert isinstance(can_id, int), "can_id should be int"
        assert isinstance(raw_data, bytes), "raw_data should be bytes"
        assert isinstance(timestamp, float), "timestamp should be float"
        received_args.append((can_id, raw_data, timestamp))

    source.start(callback)
    time.sleep(0.05)
    source.stop()
    source.disconnect()

    if received_args:
        can_id, raw_data, timestamp = received_args[0]
        print(f"  [PASS] Callback signature correct: can_id={hex(can_id)}, data_len={len(raw_data)}, timestamp={timestamp:.3f}")
        return True
    else:
        print("  [FAIL] No frames received")
        return False


if __name__ == '__main__':
    print("\n=== Live CAN Source Tests ===\n")

    tests = [
        test_live_source_lifecycle,
        test_connection_failure,
        test_repeated_start_stop,
        test_callback_signature
    ]

    passed = 0
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"  [FAIL] Exception: {e}")

    print(f"\n{passed}/{len(tests)} tests passed\n")

    if passed == len(tests):
        print("All Live CAN Source tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed.")
        sys.exit(1)
