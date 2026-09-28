"""Web UI for RM Communication Validator."""

import os
import threading
import time
from flask import Flask, render_template, jsonify, request
from pathlib import Path

from protocol import Protocol
from decoder import Decoder
from validator import Validator
from demo_source import DemoSource
from replay_source import ReplaySource
from live_can_source import LiveCANSource
from live_serial_source import LiveSerialSource
from recorder import Recorder
from socketcan_utils import is_linux, get_available_socketcan_interfaces, interface_exists
from serial_utils import get_available_serial_ports, port_exists


app = Flask(__name__)

# Global state
class AppState:
    def __init__(self):
        self.protocol = None
        self.decoder = None
        self.validator = None

        self.mode = None  # 'demo', 'replay', 'live'
        self.source = None
        self.source_thread = None

        self.running = False
        self.error_injection = False

        # Live mode specific
        self.interface = None  # Current SocketCAN interface
        self.serial_port = None  # Current Serial port
        self.connection_status = None  # 'connected', 'disconnected', 'error'
        self.last_error = None

        # Logging
        self.log_mode = 'errors'  # 'none', 'errors', 'all'
        self.recorder = None
        self.recorded_frames = 0
        self.log_file = None

        # Statistics
        self.total_frames = 0
        self.valid_frames = 0
        self.invalid_frames = 0
        self.unknown_frames = 0

        # Latest messages by type
        self.latest_messages = {}  # message_name -> decoded + validation

        # Recent events
        self.recent_events = []  # Max 20 events

        # Frame rates
        self.frame_times = {}  # can_id -> list of timestamps

        self.start_time = None

state = AppState()

# Global configuration
config = {
    'default_interface': None,  # Set from CLI or YAML
    'available_interfaces': []
}


def load_protocol(protocol_path):
    """Load protocol and initialize components."""
    state.protocol = Protocol(protocol_path)
    state.decoder = Decoder(state.protocol)
    state.validator = Validator(state.protocol)


def handle_frame(can_id, raw_data, timestamp):
    """Process a CAN frame (from any source)."""
    state.total_frames += 1

    # Track frame times for rate calculation
    if can_id not in state.frame_times:
        state.frame_times[can_id] = []
    state.frame_times[can_id].append(timestamp)
    # Keep only recent times
    if len(state.frame_times[can_id]) > 50:
        state.frame_times[can_id].pop(0)

    # Decode
    decoded = state.decoder.decode(can_id, raw_data, timestamp)

    if decoded is None:
        # Unknown CAN ID
        state.unknown_frames += 1
        event = f"{time.strftime('%H:%M:%S')} Unknown CAN ID: 0x{can_id:X}"
        add_event(event)

        # Record unknown frame if logging errors or all
        if state.recorder and state.log_mode in ('errors', 'all'):
            state.recorder.record(
                None, None, can_id, len(raw_data), raw_data, timestamp,
                transport='can'
            )
            state.recorded_frames += 1

        return

    # Validate
    validation = state.validator.validate(decoded)

    # Check if valid
    all_passed = all(v.passed for v in validation)
    if all_passed:
        state.valid_frames += 1
    else:
        state.invalid_frames += 1
        # Log failed validations
        for v in validation:
            if not v.passed:
                event = f"{time.strftime('%H:%M:%S')} {decoded.message_name}: {v.check} failed"
                add_event(event)

    # Record frame based on log mode
    if state.recorder:
        should_record = False
        if state.log_mode == 'all':
            should_record = True
        elif state.log_mode == 'errors' and not all_passed:
            should_record = True

        if should_record:
            state.recorder.record(
                decoded, validation, can_id, len(raw_data), raw_data, timestamp,
                transport='can'
            )
            state.recorded_frames += 1

    # Store latest message by type
    state.latest_messages[decoded.message_name] = {
        'decoded': decoded,
        'validation': validation,
        'all_passed': all_passed
    }


def handle_serial_frame(raw_data, timestamp):
    """Process a Serial frame."""
    state.total_frames += 1

    # For serial, we need to determine which message this is
    # Assuming single RX message for now (Tongji gimbal_to_vision)
    message_name = None
    for msg in state.protocol.messages:
        if msg.direction == 'rx' and msg.frame_length == len(raw_data):
            message_name = msg.name
            break

    if message_name is None:
        # Unknown frame length
        state.unknown_frames += 1
        event = f"{time.strftime('%H:%M:%S')} Unknown Serial frame length: {len(raw_data)}"
        add_event(event)

        # Record unknown frame if logging errors or all
        if state.recorder and state.log_mode in ('errors', 'all'):
            state.recorder.record(
                None, None, None, None, raw_data, timestamp,
                transport='serial', port=state.serial_port
            )
            state.recorded_frames += 1

        return

    # Decode
    decoded = state.decoder.decode_message(message_name, raw_data, timestamp)

    if decoded is None:
        state.unknown_frames += 1
        return

    # Validate
    validation = state.validator.validate(decoded)

    # Check if valid
    all_passed = all(v.passed for v in validation)
    if all_passed:
        state.valid_frames += 1
    else:
        state.invalid_frames += 1
        # Log failed validations
        for v in validation:
            if not v.passed:
                event = f"{time.strftime('%H:%M:%S')} {decoded.message_name}: {v.check} failed"
                add_event(event)

    # Record frame based on log mode
    if state.recorder:
        should_record = False
        if state.log_mode == 'all':
            should_record = True
        elif state.log_mode == 'errors' and not all_passed:
            should_record = True

        if should_record:
            state.recorder.record(
                decoded, validation, None, None, raw_data, timestamp,
                transport='serial', port=state.serial_port
            )
            state.recorded_frames += 1

    # Store latest message by type
    state.latest_messages[decoded.message_name] = {
        'decoded': decoded,
        'validation': validation,
        'all_passed': all_passed
    }


def add_event(event):
    """Add event to recent events list."""
    state.recent_events.append(event)
    if len(state.recent_events) > 20:
        state.recent_events.pop(0)


def start_demo():
    """Start demo mode."""
    if state.running:
        return False

    state.mode = 'demo'
    state.source = DemoSource(state.protocol)
    state.source.enable_error_injection(state.error_injection)

    # Reset statistics
    reset_statistics()

    # Start recorder if needed
    start_recorder_if_needed('demo')

    # Start in background thread
    state.running = True
    state.source_thread = threading.Thread(target=state.source.start, args=(handle_frame,))
    state.source_thread.daemon = True
    state.source_thread.start()

    return True


def start_replay(jsonl_path):
    """Start replay mode."""
    if state.running:
        return False

    try:
        state.mode = 'replay'
        state.source = ReplaySource(jsonl_path)

        # Reset statistics
        reset_statistics()

        # Replay mode: don't record by default to avoid duplicate logs
        # Recorder remains None

        # Start in background thread
        state.running = True
        state.source_thread = threading.Thread(target=state.source.start, args=(handle_frame,))
        state.source_thread.daemon = True
        state.source_thread.start()

        return True
    except Exception as e:
        return str(e)


def start_live(interface):
    """Start live SocketCAN mode."""
    if state.running:
        return {'success': False, 'error': 'Another source is already running'}

    # Check platform
    if not is_linux():
        return {'success': False, 'error': 'Live SocketCAN mode requires Linux'}

    # Check interface exists
    if not interface_exists(interface):
        return {'success': False, 'error': f'SocketCAN interface "{interface}" not found'}

    try:
        state.mode = 'live'
        state.interface = interface
        state.source = LiveCANSource(interface)

        # Connect to SocketCAN
        state.source.connect()
        state.connection_status = 'connected'
        state.last_error = None

        # Reset statistics
        reset_statistics()

        # Start recorder if needed
        start_recorder_if_needed('live', interface)

        # Start receiving
        state.running = True
        state.source.start(handle_frame)

        return {'success': True}

    except Exception as e:
        state.connection_status = 'error'
        state.last_error = str(e)
        state.mode = None
        stop_recorder_if_active()  # Clean up recorder on failure
        return {'success': False, 'error': f'Failed to connect to {interface}: {str(e)}'}


def start_live_serial(port, baudrate):
    """Start live Serial mode."""
    if state.running:
        return {'success': False, 'error': 'Another source is already running'}

    try:
        # Get serial frame configuration from protocol
        rx_messages = [msg for msg in state.protocol.messages if msg.direction == 'rx']
        if not rx_messages:
            return {'success': False, 'error': 'No RX messages defined in protocol'}

        # Use first RX message for framing
        rx_msg = rx_messages[0]

        # Determine header from protocol fields
        # Assume header fields are named header_0, header_1, etc.
        header_bytes = []
        for field in rx_msg.fields:
            if field.name.startswith('header_'):
                # Header fields should be uint8
                # For Tongji: 0x53, 0x50 ('S', 'P')
                if field.name == 'header_0':
                    header_bytes.insert(0, 0x53)  # 'S'
                elif field.name == 'header_1':
                    header_bytes.insert(1, 0x50)  # 'P'

        if not header_bytes:
            # Default fallback
            header_bytes = [0x53, 0x50]

        header = bytes(header_bytes)
        frame_length = rx_msg.frame_length

        # Get transport config
        transport = state.protocol.transport

        state.mode = 'live'
        state.serial_port = port
        state.source = LiveSerialSource(
            port=port,
            baudrate=baudrate,
            header=header,
            frame_length=frame_length,
            bytesize=transport.bytesize or 8,
            parity=transport.parity or 'N',
            stopbits=transport.stopbits or 1,
            timeout_ms=transport.timeout_ms or 20
        )

        # Connect to Serial port
        state.source.connect()
        state.connection_status = 'connected'
        state.last_error = None

        # Reset statistics
        reset_statistics()

        # Start recorder if needed
        start_recorder_if_needed('live_serial', port)

        # Start receiving
        state.running = True
        state.source.start(handle_serial_frame)

        return {'success': True}

    except Exception as e:
        state.connection_status = 'error'
        state.last_error = str(e)
        state.mode = None
        state.serial_port = None
        stop_recorder_if_active()  # Clean up recorder on failure
        return {'success': False, 'error': f'Failed to connect to {port}: {str(e)}'}


def start_recorder_if_needed(mode, interface=None):
    """Start recorder based on log mode."""
    if state.log_mode == 'none':
        return

    try:
        state.recorder = Recorder()
        # Generate filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if mode == 'live' and interface:
            filename = f"{mode}_{interface}_{timestamp}.jsonl"
        else:
            filename = f"{mode}_{timestamp}.jsonl"

        state.recorder.start(filename)
        state.log_file = state.recorder.log_file
        state.recorded_frames = 0
    except Exception as e:
        print(f"Warning: Failed to start recorder: {e}")
        state.recorder = None
        state.log_file = None


def stop_recorder_if_active():
    """Stop recorder and clean up."""
    if state.recorder:
        try:
            state.recorder.stop()
        except Exception as e:
            print(f"Warning: Error stopping recorder: {e}")
        finally:
            state.recorder = None
            state.log_file = None


def stop_source():
    """Stop current source."""
    if state.source and state.running:
        state.running = False
        if hasattr(state.source, 'stop'):
            state.source.stop()
        if hasattr(state.source, 'disconnect'):
            state.source.disconnect()

    # Stop recorder
    stop_recorder_if_active()

    state.mode = None
    state.interface = None
    state.serial_port = None
    state.connection_status = 'disconnected'


def reset_statistics():
    """Reset all statistics."""
    state.total_frames = 0
    state.valid_frames = 0
    state.invalid_frames = 0
    state.unknown_frames = 0
    state.latest_messages = {}
    state.recent_events = []
    state.frame_times = {}
    state.start_time = time.time()


def calculate_rate(can_id):
    """Calculate frame rate for a CAN ID."""
    if can_id not in state.frame_times or len(state.frame_times[can_id]) < 2:
        return 0.0

    times = state.frame_times[can_id]
    elapsed = times[-1] - times[0]
    if elapsed == 0:
        return 0.0

    return len(times) / elapsed


@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """Get current status."""
    runtime = 0
    if state.start_time:
        runtime = int(time.time() - state.start_time)

    return jsonify({
        'protocol': state.protocol.filepath if state.protocol else None,
        'transport_type': state.protocol.transport.type if state.protocol else None,
        'mode': state.mode,
        'running': state.running,
        'error_injection': state.error_injection,
        'interface': state.interface,
        'serial_port': state.serial_port,
        'connection_status': state.connection_status,
        'last_error': state.last_error,
        'log_mode': state.log_mode,
        'recording': state.recorder is not None,
        'log_file': state.log_file,
        'recorded_frames': state.recorded_frames,
        'runtime': runtime,
        'statistics': {
            'total': state.total_frames,
            'valid': state.valid_frames,
            'invalid': state.invalid_frames,
            'unknown': state.unknown_frames
        }
    })


@app.route('/api/messages')
def api_messages():
    """Get latest messages."""
    messages = {}

    for msg_name, data in state.latest_messages.items():
        decoded = data['decoded']
        validation = data['validation']

        msg_info = {
            'raw': decoded.raw.hex(' ').upper(),
            'fields': decoded.fields,
            'validation': [
                {
                    'check': v.check,
                    'passed': v.passed,
                    'message': v.message
                }
                for v in validation
            ],
            'all_passed': data['all_passed']
        }

        # Add transport-specific fields
        if decoded.can_id is not None:
            msg_info['can_id'] = f"0x{decoded.can_id:X}"
            msg_info['dlc'] = decoded.dlc
        if decoded.frame_length is not None:
            msg_info['frame_length'] = decoded.frame_length

        messages[msg_name] = msg_info

    return jsonify(messages)


@app.route('/api/rates')
def api_rates():
    """Get frame rates."""
    rates = {}
    for can_id in state.frame_times:
        rates[f"0x{can_id:X}"] = round(calculate_rate(can_id), 1)

    return jsonify(rates)


@app.route('/api/events')
def api_events():
    """Get recent events."""
    return jsonify(state.recent_events[-10:])


@app.route('/api/start_demo', methods=['POST'])
def api_start_demo():
    """Start demo mode."""
    success = start_demo()
    return jsonify({'success': success})


@app.route('/api/start_replay', methods=['POST'])
def api_start_replay():
    """Start replay mode."""
    data = request.json
    jsonl_path = data.get('path')

    if not jsonl_path:
        return jsonify({'success': False, 'error': 'No path provided'})

    result = start_replay(jsonl_path)
    if result is True:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': result})


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """Stop current source."""
    stop_source()
    return jsonify({'success': True})


@app.route('/api/toggle_error_injection', methods=['POST'])
def api_toggle_error_injection():
    """Toggle error injection in demo mode."""
    state.error_injection = not state.error_injection
    if state.source and isinstance(state.source, DemoSource):
        state.source.enable_error_injection(state.error_injection)
    return jsonify({'enabled': state.error_injection})


@app.route('/api/list_logs')
def api_list_logs():
    """List available JSONL log files."""
    logs_dir = Path('logs')
    if not logs_dir.exists():
        return jsonify([])

    logs = []
    for log_file in logs_dir.glob('*.jsonl'):
        logs.append({
            'name': log_file.name,
            'path': str(log_file),
            'size': log_file.stat().st_size
        })

    return jsonify(sorted(logs, key=lambda x: x['name'], reverse=True))


@app.route('/api/start_live', methods=['POST'])
def api_start_live():
    """Start live SocketCAN mode."""
    data = request.json
    interface = data.get('interface')

    if not interface:
        return jsonify({'success': False, 'error': 'No interface provided'})

    result = start_live(interface)
    return jsonify(result)


@app.route('/api/socketcan_interfaces')
def api_socketcan_interfaces():
    """Get available SocketCAN interfaces."""
    return jsonify({
        'platform': 'linux' if is_linux() else 'other',
        'interfaces': config['available_interfaces'],
        'default': config['default_interface']
    })


@app.route('/api/serial_ports')
def api_serial_ports():
    """Get available serial ports."""
    ports = get_available_serial_ports()
    return jsonify({
        'ports': ports
    })


@app.route('/api/start_live_serial', methods=['POST'])
def api_start_live_serial():
    """Start live Serial mode."""
    data = request.json
    port = data.get('port')
    baudrate = data.get('baudrate', 9600)

    if not port:
        return jsonify({'success': False, 'error': 'No port provided'})

    result = start_live_serial(port, baudrate)
    return jsonify(result)


@app.route('/api/set_log_mode', methods=['POST'])
def api_set_log_mode():
    """Set logging mode."""
    if state.running:
        return jsonify({'success': False, 'error': 'Cannot change log mode while running. Stop first.'})

    data = request.json
    mode = data.get('mode')

    if mode not in ('none', 'errors', 'all'):
        return jsonify({'success': False, 'error': 'Invalid log mode'})

    state.log_mode = mode
    return jsonify({'success': True, 'mode': mode})


def run_web(protocol_path, host='127.0.0.1', port=5000, interface=None):
    """Run web server."""
    # Load protocol
    load_protocol(protocol_path)

    # Detect available SocketCAN interfaces
    config['available_interfaces'] = get_available_socketcan_interfaces()

    # Determine default interface
    if interface:
        # CLI argument takes precedence
        config['default_interface'] = interface
    elif state.protocol and state.protocol.messages:
        # Try to get from protocol YAML
        try:
            yaml_interface = state.protocol.config.get('transport', {}).get('interface', 'can0')
            config['default_interface'] = yaml_interface
        except:
            config['default_interface'] = 'can0'
    else:
        config['default_interface'] = 'can0'

    # Print startup banner
    print(f"\n=== RM Communication Validator Web UI ===")
    print(f"Protocol: {protocol_path}")
    print(f"Default interface: {config['default_interface']}")

    if is_linux():
        if config['available_interfaces']:
            print(f"Available SocketCAN interfaces: {', '.join(config['available_interfaces'])}")
        else:
            print("Available SocketCAN interfaces: none")
            print("Live mode unavailable until a CAN/vCAN interface is created.")
    else:
        print("Platform: Non-Linux (Live mode unavailable)")

    print(f"Server: http://{host}:{port}")
    print(f"\nLive interface can also be selected from the Web UI.")
    print("Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    import sys
    protocol_path = sys.argv[1] if len(sys.argv) > 1 else 'protocols/tongji_sentry.yaml'
    run_web(protocol_path)
