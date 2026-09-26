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

        # Start in background thread
        state.running = True
        state.source_thread = threading.Thread(target=state.source.start, args=(handle_frame,))
        state.source_thread.daemon = True
        state.source_thread.start()

        return True
    except Exception as e:
        return str(e)


def stop_source():
    """Stop current source."""
    if state.source and state.running:
        state.running = False
        if hasattr(state.source, 'stop'):
            state.source.stop()
    state.mode = None


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
        'mode': state.mode,
        'running': state.running,
        'error_injection': state.error_injection,
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

        messages[msg_name] = {
            'can_id': f"0x{decoded.can_id:X}",
            'dlc': decoded.dlc,
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


def run_web(protocol_path, host='127.0.0.1', port=5000):
    """Run web server."""
    # Load protocol
    load_protocol(protocol_path)

    print(f"\n=== RM Communication Validator Web UI ===")
    print(f"Protocol: {protocol_path}")
    print(f"Server: http://{host}:{port}")
    print(f"\nOpen your browser to start monitoring.")
    print("Press Ctrl+C to stop.\n")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    import sys
    protocol_path = sys.argv[1] if len(sys.argv) > 1 else 'protocols/tongji_sentry.yaml'
    run_web(protocol_path)
