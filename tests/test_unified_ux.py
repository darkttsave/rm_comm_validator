"""Tests for Unified Validator UX Closeout.

Covers:
- Runtime mode (normal vs simulation)
- Protocol registry and switching
- Transport switching and protocol filtering
- Auto-start/stop for virtual endpoints
- CAN simulator lifecycle
"""

import sys
import pytest
from pathlib import Path

from protocol_registry import ProtocolRegistry
from can_simulator import CANSimulator
from serial_simulator import SerialSimulator


# --------------------------------------------------------------------------
# Protocol Registry
# --------------------------------------------------------------------------

def test_protocol_registry_loads_protocols(tmp_path):
    """Test that protocol registry scans and loads protocols."""
    # Create test protocols directory
    protocols_dir = tmp_path / 'protocols'
    protocols_dir.mkdir()

    # Create a CAN protocol
    can_yaml = protocols_dir / 'test_can.yaml'
    can_yaml.write_text("""
transport:
  type: socketcan
  interface: can0
messages:
  - name: test_msg
    id: 0x100
""")

    # Create a Serial protocol
    serial_yaml = protocols_dir / 'test_serial.yaml'
    serial_yaml.write_text("""
transport:
  type: serial
  port: /dev/ttyUSB0
messages:
  - name: test_msg
    direction: rx
""")

    registry = ProtocolRegistry(protocols_dir)
    protocols = registry.get_all()

    assert len(protocols) == 2
    assert any(p['id'] == 'test_can' and p['transport'] == 'socketcan' for p in protocols)
    assert any(p['id'] == 'test_serial' and p['transport'] == 'serial' for p in protocols)


def test_protocol_registry_filters_by_transport(tmp_path):
    """Test protocol filtering by transport type."""
    protocols_dir = tmp_path / 'protocols'
    protocols_dir.mkdir()

    (protocols_dir / 'can1.yaml').write_text('transport:\n  type: socketcan\nmessages: []')
    (protocols_dir / 'can2.yaml').write_text('transport:\n  type: socketcan\nmessages: []')
    (protocols_dir / 'serial1.yaml').write_text('transport:\n  type: serial\nmessages: []')

    registry = ProtocolRegistry(protocols_dir)
    can_protocols = registry.get_by_transport('socketcan')
    serial_protocols = registry.get_by_transport('serial')

    assert len(can_protocols) == 2
    assert len(serial_protocols) == 1


def test_protocol_registry_get_path_is_safe(tmp_path):
    """Test that get_path only returns whitelisted paths."""
    protocols_dir = tmp_path / 'protocols'
    protocols_dir.mkdir()
    (protocols_dir / 'safe.yaml').write_text('transport:\n  type: socketcan\nmessages: []')

    registry = ProtocolRegistry(protocols_dir)

    # Valid ID returns path
    path = registry.get_path('safe')
    assert path is not None
    assert 'safe.yaml' in path

    # Invalid ID returns None (prevents path injection)
    assert registry.get_path('../etc/passwd') is None
    assert registry.get_path('nonexistent') is None


# --------------------------------------------------------------------------
# Runtime Mode
# --------------------------------------------------------------------------

def test_normal_runtime_filters_virtual_endpoints(monkeypatch):
    """Test that Normal Runtime hides virtual endpoints."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'normal')

    # Mock simulators
    class FakeSerialSim:
        def get_status(self):
            return {
                'status': 'idle', 'running': False,
                'socat_installed': True, 'error': None,
                'device': '/tmp/rmcv_validator', 'label': 'RM Virtual Serial',
            }

    class FakeCANSim:
        def get_status(self):
            return {
                'status': 'idle', 'running': False,
                'vcan_available': True, 'mock_built': True, 'error': None,
                'interface': 'vcan0', 'label': 'RM Virtual CAN',
            }

    monkeypatch.setattr(web_app, 'serial_simulator', FakeSerialSim())
    monkeypatch.setattr(web_app, 'can_simulator', FakeCANSim())
    monkeypatch.setattr(web_app, 'get_available_serial_ports', lambda: [
        {'device': '/dev/ttyUSB0', 'description': 'CH340', 'hwid': ''},
    ])
    monkeypatch.setattr(web_app, 'get_available_socketcan_interfaces', lambda: ['can0'])

    client = web_app.app.test_client()

    # Serial endpoints should NOT include virtual in Normal Runtime
    data = client.get('/api/serial_endpoints').get_json()
    assert all(e['kind'] != 'virtual' for e in data['endpoints'])

    # CAN endpoints should NOT include virtual in Normal Runtime
    data = client.get('/api/can_endpoints').get_json()
    assert all(e['kind'] != 'virtual' for e in data['endpoints'])


def test_simulation_runtime_shows_virtual_endpoints(monkeypatch):
    """Test that Simulation Runtime shows virtual endpoints."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'simulation')

    class FakeSerialSim:
        def get_status(self):
            return {
                'status': 'idle', 'running': False,
                'socat_installed': True, 'error': None,
                'device': '/tmp/rmcv_validator', 'label': 'RM Virtual Serial',
            }

    class FakeCANSim:
        def get_status(self):
            return {
                'status': 'idle', 'running': False,
                'vcan_available': True, 'mock_built': True, 'error': None,
                'interface': 'vcan0', 'label': 'RM Virtual CAN',
            }

    monkeypatch.setattr(web_app, 'serial_simulator', FakeSerialSim())
    monkeypatch.setattr(web_app, 'can_simulator', FakeCANSim())
    monkeypatch.setattr(web_app, 'get_available_serial_ports', lambda: [])
    monkeypatch.setattr(web_app, 'get_available_socketcan_interfaces', lambda: [])

    client = web_app.app.test_client()

    # Serial endpoints SHOULD include virtual in Simulation Runtime
    data = client.get('/api/serial_endpoints').get_json()
    assert any(e['kind'] == 'virtual' for e in data['endpoints'])

    # CAN endpoints SHOULD include virtual in Simulation Runtime
    data = client.get('/api/can_endpoints').get_json()
    assert any(e['kind'] == 'virtual' for e in data['endpoints'])


# --------------------------------------------------------------------------
# Protocol Switching
# --------------------------------------------------------------------------

def test_protocol_switching_only_when_idle(monkeypatch):
    """Test that protocol can only be switched when idle."""
    import web_app

    # Load a default protocol
    web_app.load_protocol('protocols/tongji_sentry.yaml')

    client = web_app.app.test_client()

    # Should succeed when idle
    r = client.post('/api/load_protocol', json={'protocol_id': 'tongji_sentry'}).get_json()
    assert r['success'] is True

    # Start demo to make it running
    client.post('/api/start_demo')
    time_module = __import__('time')
    time_module.sleep(0.1)

    # Should fail when running
    r = client.post('/api/load_protocol', json={'protocol_id': 'tongji_sentry'}).get_json()
    assert r['success'] is False
    assert 'running' in r['error'].lower()

    # Stop
    client.post('/api/stop')


def test_transport_protocol_endpoint_locked_when_running(monkeypatch):
    """Test that Transport/Protocol/Endpoint are locked when running (frontend contract)."""
    import web_app

    web_app.load_protocol('protocols/tongji_sentry.yaml')
    client = web_app.app.test_client()

    # Start demo
    client.post('/api/start_demo')
    time_module = __import__('time')
    time_module.sleep(0.1)

    st = client.get('/api/status').get_json()
    assert st['running'] is True

    # Protocol switching should be rejected
    r = client.post('/api/load_protocol', json={'protocol_id': 'tongji_sentry'}).get_json()
    assert r['success'] is False

    client.post('/api/stop')


# --------------------------------------------------------------------------
# Auto-start/stop Virtual Endpoints
# --------------------------------------------------------------------------

def test_virtual_serial_auto_start(monkeypatch, tmp_path):
    """Test that selecting Virtual Serial auto-starts the simulator."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'simulation')

    started = []

    class FakeSerialSim:
        VALIDATOR_DEVICE = '/tmp/rmcv_validator'

        def get_status(self):
            return {
                'status': 'running' if started else 'idle',
                'running': bool(started),
                'socat_installed': True,
                'error': None,
                'device': self.VALIDATOR_DEVICE,
                'label': 'RM Virtual Serial',
            }

        def start(self, mode='normal'):
            started.append(True)
            return {'success': True, 'status': 'running'}

        def stop(self):
            started.clear()
            return {'success': True, 'status': 'stopped'}

        def cleanup(self):
            pass

    fake_sim = FakeSerialSim()
    monkeypatch.setattr(web_app, 'serial_simulator', fake_sim)

    # Mock LiveSerialSource
    class FakeLiveSerial:
        def __init__(self, **kwargs):
            pass
        def connect(self): pass
        def start(self, cb): pass
        def stop(self): pass
        def disconnect(self): pass

    monkeypatch.setattr(web_app, 'LiveSerialSource', FakeLiveSerial)

    # Load protocol
    web_app.load_protocol('protocols/tongji_gimbal_serial.yaml')

    # Start Live with virtual endpoint
    result = web_app.start_live_serial(
        port='/tmp/rmcv_validator',
        baudrate=9600,
        label='RM Virtual Serial',
        kind='virtual'
    )

    assert result['success'] is True
    assert len(started) == 1  # Simulator was auto-started


def test_virtual_serial_auto_stop(monkeypatch):
    """Test that stopping Virtual Serial auto-stops the simulator."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'simulation')

    sim_running = [True]

    class FakeSerialSim:
        VALIDATOR_DEVICE = '/tmp/rmcv_validator'

        def get_status(self):
            return {
                'status': 'running' if sim_running[0] else 'stopped',
                'running': sim_running[0],
                'socat_installed': True,
                'error': None,
                'device': self.VALIDATOR_DEVICE,
                'label': 'RM Virtual Serial',
            }

        def start(self):
            sim_running[0] = True
            return {'success': True}

        def stop(self):
            sim_running[0] = False
            return {'success': True}

        def cleanup(self): pass

    fake_sim = FakeSerialSim()
    monkeypatch.setattr(web_app, 'serial_simulator', fake_sim)

    # Simulate a running virtual serial session
    web_app.state.running = True
    web_app.state.endpoint_kind = 'virtual'
    web_app.state.current_transport = 'serial'
    web_app.state.source = type('obj', (object,), {'stop': lambda self: None, 'disconnect': lambda self: None})()

    # Stop
    web_app.stop_source()

    assert sim_running[0] is False  # Simulator was auto-stopped


def test_physical_serial_does_not_auto_start_simulator(monkeypatch):
    """Test that physical serial does NOT auto-start the simulator."""
    import web_app

    started = []

    class FakeSerialSim:
        def start(self):
            started.append(True)
            return {'success': True}

    monkeypatch.setattr(web_app, 'serial_simulator', FakeSerialSim())

    class FakeLiveSerial:
        def __init__(self, **kwargs): pass
        def connect(self): pass
        def start(self, cb): pass

    monkeypatch.setattr(web_app, 'LiveSerialSource', FakeLiveSerial)

    web_app.load_protocol('protocols/tongji_gimbal_serial.yaml')

    # Start Live with physical endpoint
    web_app.start_live_serial(
        port='/dev/ttyUSB0',
        baudrate=9600,
        label='/dev/ttyUSB0',
        kind='physical'
    )

    assert len(started) == 0  # Simulator was NOT started


def test_virtual_can_auto_start(monkeypatch):
    """Test that selecting Virtual CAN auto-starts the simulator."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'simulation')
    monkeypatch.setattr(web_app, 'is_linux', lambda: True)
    monkeypatch.setattr(web_app, 'interface_exists', lambda iface: True)

    started = []

    class FakeCANSim:
        INTERFACE = 'vcan0'

        def get_status(self):
            return {
                'status': 'running' if started else 'idle',
                'running': bool(started),
                'vcan_available': True,
                'mock_built': True,
                'error': None,
                'interface': self.INTERFACE,
                'label': 'RM Virtual CAN',
            }

        def start(self, mode='normal'):
            started.append(True)
            return {'success': True, 'status': 'running'}

        def stop(self):
            started.clear()
            return {'success': True}

        def cleanup(self):
            pass

    fake_sim = FakeCANSim()
    monkeypatch.setattr(web_app, 'can_simulator', fake_sim)

    class FakeLiveCAN:
        def __init__(self, iface): pass
        def connect(self): pass
        def start(self, cb): pass

    monkeypatch.setattr(web_app, 'LiveCANSource', FakeLiveCAN)

    web_app.load_protocol('protocols/tongji_sentry.yaml')

    # Start Live with virtual CAN endpoint
    result = web_app.start_live(
        interface='vcan0',
        label='RM Virtual CAN',
        kind='virtual'
    )

    assert result['success'] is True
    assert len(started) == 1  # CAN simulator was auto-started


def test_virtual_can_auto_stop(monkeypatch):
    """Test that stopping Virtual CAN auto-stops the simulator."""
    import web_app

    monkeypatch.setattr(web_app, 'RUNTIME_MODE', 'simulation')

    sim_running = [True]

    class FakeCANSim:
        INTERFACE = 'vcan0'

        def get_status(self):
            return {'running': sim_running[0]}

        def stop(self):
            sim_running[0] = False
            return {'success': True}

        def cleanup(self): pass

    monkeypatch.setattr(web_app, 'can_simulator', FakeCANSim())

    # Simulate a running virtual CAN session
    web_app.state.running = True
    web_app.state.endpoint_kind = 'virtual'
    web_app.state.current_transport = 'socketcan'
    web_app.state.source = type('obj', (object,), {'stop': lambda self: None, 'disconnect': lambda self: None})()

    # Stop
    web_app.stop_source()

    assert sim_running[0] is False  # CAN simulator was auto-stopped


def test_physical_can_does_not_auto_start_simulator(monkeypatch):
    """Test that physical CAN does NOT auto-start the simulator."""
    import web_app

    monkeypatch.setattr(web_app, 'is_linux', lambda: True)
    monkeypatch.setattr(web_app, 'interface_exists', lambda iface: True)

    started = []

    class FakeCANSim:
        def start(self):
            started.append(True)
            return {'success': True}

    monkeypatch.setattr(web_app, 'can_simulator', FakeCANSim())

    class FakeLiveCAN:
        def __init__(self, iface): pass
        def connect(self): pass
        def start(self, cb): pass

    monkeypatch.setattr(web_app, 'LiveCANSource', FakeLiveCAN)

    web_app.load_protocol('protocols/tongji_sentry.yaml')

    # Start Live with physical CAN endpoint
    web_app.start_live(
        interface='can0',
        label='can0',
        kind='physical'
    )

    assert len(started) == 0  # CAN simulator was NOT started


# --------------------------------------------------------------------------
# CAN Simulator Lifecycle
# --------------------------------------------------------------------------

def test_can_simulator_checks_vcan_available(monkeypatch, tmp_path):
    """Test that CAN simulator checks vcan0 availability."""
    sim = CANSimulator(repo_root=tmp_path)

    # Mock Mock EC executable to exist
    mock_ec_path = tmp_path / 'tools' / 'mock_ec_node' / 'build' / 'mock_ec_node'
    mock_ec_path.parent.mkdir(parents=True, exist_ok=True)
    mock_ec_path.write_text('#!/bin/bash\necho mock')
    mock_ec_path.chmod(0o755)

    # Mock vcan check to return False
    monkeypatch.setattr(CANSimulator, 'vcan_available', property(lambda self: False))

    result = sim.start()

    assert result['success'] is False
    assert 'vcan0' in result['error']


def test_can_simulator_checks_mock_built(monkeypatch, tmp_path):
    """Test that CAN simulator checks if Mock EC is built."""
    sim = CANSimulator(repo_root=tmp_path)

    result = sim.start()

    assert result['success'] is False
    assert 'Mock EC' in result['error']
    assert 'build.sh' in result['error']


def test_can_simulator_lifecycle(monkeypatch, tmp_path):
    """Test CAN simulator start/stop lifecycle."""
    # Create fake mock executable
    mock_dir = tmp_path / 'tools' / 'mock_ec_node' / 'build'
    mock_dir.mkdir(parents=True)
    mock_exe = mock_dir / 'mock_ec_node'
    mock_exe.write_text('#!/bin/bash\necho mock')
    mock_exe.chmod(0o755)

    sim = CANSimulator(repo_root=tmp_path)

    # Mock vcan as available
    monkeypatch.setattr(CANSimulator, 'vcan_available', property(lambda self: True))

    procs = []

    def fake_popen(args, **kwargs):
        p = type('obj', (object,), {
            'pid': len(procs) + 100,
            'poll': lambda self: None,
            'terminate': lambda self: None,
            'wait': lambda self, timeout=None: None,
            'kill': lambda self: None,
        })()
        procs.append(p)
        return p

    monkeypatch.setattr('subprocess.Popen', fake_popen)
    monkeypatch.setattr('time.sleep', lambda s: None)

    # Start
    result = sim.start()
    assert result['success'] is True
    assert sim.status == 'running'
    assert len(procs) == 1

    # Stop
    sim.stop()
    assert sim.status == 'stopped'
