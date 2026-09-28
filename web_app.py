"""Web UI for RM Communication Validator.

Runtime modes:
- Normal: ./start_web.sh - only physical devices, no virtual endpoints
- Simulation: ./start_sim.sh --simulation - enables virtual endpoints
"""

import atexit
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
from socketcan_utils import is_linux, get_available_socketcan_interfaces, interface_exists, build_unified_can_endpoints
from serial_utils import get_available_serial_ports, build_unified_endpoints
from serial_simulator import SerialSimulator
from can_simulator import CANSimulator
from protocol_registry import ProtocolRegistry


app = Flask(__name__)

# Runtime mode
RUNTIME_MODE = 'normal'  # 'normal' or 'simulation'


# Global state
class AppState:
    def __init__(self):
        self.protocol = None
        self.decoder = None
        self.validator = None
        self.current_protocol_id = None
        self.current_transport = None  # 'socketcan' or 'serial'

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

        # Session state (unified workflow)
        self.session_status = 'idle'  # idle | connecting | running | error
        self.endpoint_label = None  # display label of current endpoint
        self.endpoint_kind = None  # 'virtual' or 'physical'
        self.serial_baudrate = None  # current serial baudrate

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

# Protocol registry
protocol_registry = ProtocolRegistry(Path(__file__).parent / 'protocols')

# Virtual simulators (owned by this web process)
serial_simulator = SerialSimulator(Path(__file__).parent)
can_simulator = CANSimulator(Path(__file__).parent)


def _cleanup_on_exit():
    """Cleanup simulators on exit."""
    serial_simulator.cleanup()
    can_simulator.cleanup()


atexit.register(_cleanup_on_exit)


# Friendly context for serial open failures.
SERIAL_ERROR_CAUSES = [
    '设备当前不可用',
    '设备被其他程序占用',
    '当前设备节点不是可用的物理/虚拟串口',
    '当前用户没有访问权限',
]


def friendly_serial_error(port, exc):
    """Build a user-understandable serial error while keeping the raw detail."""
    print(f"[Serial error] failed to open {port}: {exc}")
    return {
        'success': False,
        'error': f'无法打开 {port}',
        'detail': str(exc),
        'causes': SERIAL_ERROR_CAUSES,
    }


def load_protocol(protocol_id_or_path):
    """Load protocol and initialize components."""
    # If it's a protocol ID from registry, resolve to path
    if '/' not in protocol_id_or_path and '\\' not in protocol_id_or_path:
        path = protocol_registry.get_path(protocol_id_or_path)
        if path is None:
            raise ValueError(f"Unknown protocol ID: {protocol_id_or_path}")
        protocol_id = protocol_id_or_path
    else:
        # Legacy: direct path
        path = protocol_id_or_path
        protocol_id = Path(path).stem

    state.protocol = Protocol(path)
    state.decoder = Decoder(state.protocol)
    state.validator = Validator(state.protocol)
    state.current_protocol_id = protocol_id
    state.current_transport = state.protocol.transport.type


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
    state.endpoint_label = 'Demo'
    state.endpoint_kind = None
    state.interface = None
    state.serial_port = None
    state.serial_baudrate = None
    state.connection_status = None
    state.last_error = None
    state.session_status = 'running'
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
        state.endpoint_label = 'Replay'
        state.endpoint_kind = None
        state.interface = None
        state.serial_port = None
        state.serial_baudrate = None
        state.connection_status = None
        state.last_error = None
        state.session_status = 'running'
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


def start_live(interface, label=None, kind='physical'):
    """Start live SocketCAN mode."""
    if state.running:
        return {'success': False, 'error': 'Another source is already running'}

    # Check platform
    if not is_linux():
        return {'success': False, 'error': 'Live SocketCAN mode requires Linux'}

    # Virtual endpoint requires a running simulator
    if kind == 'virtual' and interface == can_simulator.INTERFACE:
        if not can_simulator.get_status()['running']:
            # Auto-start the simulator
            print(f"[Auto-start] Starting CAN simulator for {interface}...")
            result = can_simulator.start()
            if not result['success']:
                return result

    # Check interface exists
    if not interface_exists(interface):
        return {'success': False, 'error': f'SocketCAN interface "{interface}" not found'}

    state.session_status = 'connecting'
    state.connection_status = 'connecting'
    state.last_error = None

    try:
        state.mode = 'live'
        state.interface = interface
        state.endpoint_label = label or interface
        state.endpoint_kind = kind
        state.serial_port = None
        state.serial_baudrate = None
        state.source = LiveCANSource(interface)

        # Connect to SocketCAN
        state.source.connect()
        state.connection_status = 'connected'
        state.session_status = 'running'
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
        state.session_status = 'error'
        state.last_error = str(e)
        state.mode = None
        stop_recorder_if_active()  # Clean up recorder on failure
        return {'success': False, 'error': f'Failed to connect to {interface}: {str(e)}'}


def start_live_serial(port, baudrate, label=None, kind='physical', error_mode='normal'):
    """Start live Serial mode."""
    if state.running:
        return {'success': False, 'error': 'Another source is already running'}

    # Virtual endpoint requires a running simulator
    if kind == 'virtual' and port == serial_simulator.VALIDATOR_DEVICE:
        if not serial_simulator.get_status()['running']:
            # Auto-start the simulator with specified error mode
            print(f"[Auto-start] Starting Serial simulator for {port} with mode={error_mode}...")
            result = serial_simulator.start(mode=error_mode)
            if not result['success']:
                return result

    state.session_status = 'connecting'
    state.connection_status = 'connecting'
    state.last_error = None

    try:
        # Get serial frame configuration from protocol
        rx_messages = [msg for msg in state.protocol.messages if msg.direction == 'rx']
        if not rx_messages:
            state.session_status = 'error'
            return {'success': False, 'error': 'No RX messages defined in protocol'}

        # Use first RX message for framing
        rx_msg = rx_messages[0]

        # Frame header comes from protocol transport config (generic, not hardcoded)
        header = state.protocol.transport.header
        if header is None:
            state.session_status = 'error'
            return {'success': False, 'error': 'Protocol does not define a frame header'}

        frame_length = rx_msg.frame_length

        # Get transport config
        transport = state.protocol.transport

        state.mode = 'live'
        state.serial_port = port
        state.serial_baudrate = baudrate
        state.endpoint_label = label or port
        state.endpoint_kind = kind
        state.interface = None
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
        state.session_status = 'running'
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
        state.session_status = 'error'
        state.last_error = f'无法打开 {port}'
        state.mode = None
        state.serial_port = None
        stop_recorder_if_active()  # Clean up recorder on failure
        return friendly_serial_error(port, e)


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
    endpoint_was_virtual = state.endpoint_kind == 'virtual'
    transport_was_serial = state.current_transport == 'serial'
    transport_was_can = state.current_transport == 'socketcan'

    if state.source and state.running:
        state.running = False
        if hasattr(state.source, 'stop'):
            state.source.stop()
        if hasattr(state.source, 'disconnect'):
            state.source.disconnect()

    # Stop recorder
    stop_recorder_if_active()

    # Auto-stop virtual simulator if it was a virtual endpoint
    if endpoint_was_virtual:
        if transport_was_serial:
            print("[Auto-stop] Stopping Serial simulator...")
            serial_simulator.stop()
        elif transport_was_can:
            print("[Auto-stop] Stopping CAN simulator...")
            can_simulator.stop()

    state.mode = None
    state.interface = None
    state.serial_port = None
    state.endpoint_label = None
    state.endpoint_kind = None
    state.serial_baudrate = None
    state.connection_status = 'disconnected'
    state.session_status = 'idle'
    state.last_error = None


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


# ============================================================================
# Flask Routes
# ============================================================================

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/api/runtime')
def api_runtime():
    """Get runtime mode."""
    return jsonify({
        'mode': RUNTIME_MODE,
        'simulation_enabled': RUNTIME_MODE == 'simulation'
    })


@app.route('/api/status')
def api_status():
    """Get current status."""
    runtime = 0
    if state.start_time:
        runtime = int(time.time() - state.start_time)

    return jsonify({
        'protocol': state.protocol.filepath if state.protocol else None,
        'protocol_id': state.current_protocol_id,
        'transport_type': state.current_transport,
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
        'session': {
            'status': state.session_status,
            'mode': state.mode,
            'transport': state.current_transport,
            'protocol': state.current_protocol_id,
            'endpoint': state.serial_port or state.interface,
            'endpoint_label': state.endpoint_label,
            'endpoint_kind': state.endpoint_kind,
            'baudrate': state.serial_baudrate,
            'interface': state.interface,
            'connection_status': state.connection_status,
            'last_error': state.last_error,
        },
        'serial_simulator': serial_simulator.get_status(),
        'can_simulator': can_simulator.get_status(),
        'statistics': {
            'total': state.total_frames,
            'valid': state.valid_frames,
            'invalid': state.invalid_frames,
            'unknown': state.unknown_frames
        }
    })


@app.route('/api/protocols')
def api_protocols():
    """Get available protocols."""
    return jsonify({
        'protocols': protocol_registry.get_all()
    })


@app.route('/api/protocols/<transport>')
def api_protocols_by_transport(transport):
    """Get protocols filtered by transport type."""
    return jsonify({
        'protocols': protocol_registry.get_by_transport(transport)
    })


@app.route('/api/load_protocol', methods=['POST'])
def api_load_protocol():
    """Load a new protocol (only when idle)."""
    if state.running:
        return jsonify({'success': False, 'error': 'Cannot change protocol while running'})

    data = request.json
    protocol_id = data.get('protocol_id')

    if not protocol_id:
        return jsonify({'success': False, 'error': 'No protocol_id provided'})

    try:
        load_protocol(protocol_id)
        return jsonify({
            'success': True,
            'protocol_id': state.current_protocol_id,
            'transport': state.current_transport
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


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
    label = data.get('label')
    kind = data.get('kind', 'physical')

    if not interface:
        return jsonify({'success': False, 'error': 'No interface provided'})

    result = start_live(interface, label=label, kind=kind)
    return jsonify(result)


@app.route('/api/can_endpoints')
def api_can_endpoints():
    """Get unified CAN endpoints (managed virtual + discovered physical)."""
    virtual_status = can_simulator.get_status()
    physical = get_available_socketcan_interfaces()
    endpoints = build_unified_can_endpoints(physical, virtual_status)

    # Filter out virtual endpoint in Normal Runtime
    if RUNTIME_MODE == 'normal':
        endpoints = [e for e in endpoints if e['kind'] != 'virtual']

    return jsonify({
        'endpoints': endpoints,
        'virtual': virtual_status,
    })


@app.route('/api/serial_endpoints')
def api_serial_endpoints():
    """Get unified serial endpoints (managed virtual + discovered physical)."""
    virtual_status = serial_simulator.get_status()
    physical = get_available_serial_ports()
    endpoints = build_unified_endpoints(physical, virtual_status)

    # Filter out virtual endpoint in Normal Runtime
    if RUNTIME_MODE == 'normal':
        endpoints = [e for e in endpoints if e['kind'] != 'virtual']

    return jsonify({
        'endpoints': endpoints,
        'virtual': virtual_status,
    })


@app.route('/api/start_live_serial', methods=['POST'])
def api_start_live_serial():
    """Start live Serial mode."""
    data = request.json
    port = data.get('port')
    baudrate = data.get('baudrate', 9600)
    label = data.get('label')
    kind = data.get('kind', 'physical')
    error_mode = data.get('error_mode', 'normal')

    if not port:
        return jsonify({'success': False, 'error': 'No port provided'})

    result = start_live_serial(port, baudrate, label=label, kind=kind, error_mode=error_mode)
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


def run_web(protocol_id=None, host='127.0.0.1', port=5000, simulation=False):
    """Run web server."""
    global RUNTIME_MODE
    RUNTIME_MODE = 'simulation' if simulation else 'normal'

    # Load a default protocol if provided, otherwise the first available
    if protocol_id:
        load_protocol(protocol_id)
    else:
        protocols = protocol_registry.get_all()
        if protocols:
            load_protocol(protocols[0]['id'])
        else:
            print("Warning: No protocols found in protocols/ directory")

    # Print startup banner
    print(f"\n=== RM Communication Validator Web UI ===")
    print(f"Runtime mode: {RUNTIME_MODE.upper()}")
    if state.protocol:
        print(f"Default protocol: {state.current_protocol_id} ({state.current_transport})")
    print(f"Server: http://{host}:{port}")
    print(f"\nAll protocols can be switched from the Web UI.")
    if RUNTIME_MODE == 'simulation':
        print(f"Virtual endpoints enabled (RM Virtual CAN / RM Virtual Serial)")
    else:
        print(f"Normal runtime (physical devices only)")
    print(f"\nPress Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    import sys
    protocol_id = sys.argv[1] if len(sys.argv) > 1 else None
    run_web(protocol_id)
