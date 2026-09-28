"""Tests for the Serial simulator lifecycle and unified endpoint API."""

import sys
import time
from pathlib import Path

import pytest

from serial_simulator import SerialSimulator
from serial_utils import build_unified_endpoints


class FakeProc:
    """Minimal stand-in for a subprocess.Popen object."""

    def __init__(self, pid):
        self.pid = pid
        self._alive = True
        self.args = None

    def poll(self):
        return None if self._alive else 1

    def terminate(self):
        self._alive = False

    def wait(self, timeout=None):
        return 1

    def kill(self):
        self._alive = False


def _install(monkeypatch, sim, procs, aliases_exist=True):
    """Wire the simulator with fake subprocess/os to exercise lifecycle logic."""
    monkeypatch.setattr('shutil.which', lambda _cmd: '/usr/bin/socat')

    def fake_popen(args, **kwargs):
        p = FakeProc(len(procs) + 100)
        p.args = args
        procs.append(p)
        return p

    monkeypatch.setattr('subprocess.Popen', fake_popen)
    monkeypatch.setattr('os.path.exists', lambda _p: aliases_exist)
    monkeypatch.setattr('os.path.islink', lambda _p: False)
    monkeypatch.setattr('time.sleep', lambda _s: None)
    return sim


# --------------------------------------------------------------------------
# Pure function: unified endpoint list
# --------------------------------------------------------------------------

def test_unified_endpoints_merge_virtual_and_physical():
    virtual = {
        'device': '/tmp/rmcv_validator',
        'label': 'RM Virtual Serial',
        'socat_installed': True,
        'running': False,
    }
    physical = [{'device': '/dev/ttyUSB0', 'description': 'CH340'}]

    eps = build_unified_endpoints(physical, virtual)

    assert len(eps) == 2
    assert eps[0]['kind'] == 'virtual'
    assert eps[0]['label'] == 'RM Virtual Serial'
    assert eps[0]['available'] is True
    assert eps[1]['kind'] == 'physical'
    assert eps[1]['device'] == '/dev/ttyUSB0'
    assert 'CH340' in eps[1]['label']


def test_unified_endpoints_virtual_unavailable_without_socat():
    virtual = {
        'device': '/tmp/rmcv_validator',
        'label': 'RM Virtual Serial',
        'socat_installed': False,
        'running': False,
    }
    eps = build_unified_endpoints([], virtual)

    assert eps[0]['kind'] == 'virtual'
    assert eps[0]['available'] is False


# --------------------------------------------------------------------------
# Simulator lifecycle
# --------------------------------------------------------------------------

def test_start_missing_socat_fails_gracefully(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    monkeypatch.setattr('shutil.which', lambda _cmd: None)

    result = sim.start()

    assert result['success'] is False
    assert 'socat' in result['error'].lower()
    assert sim.status == 'error'


def test_start_success_spawns_socat_and_mock(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start()

    assert result['success'] is True
    assert sim.status == 'running'
    assert len(procs) == 2
    assert procs[0].args[0] == 'socat'
    assert procs[1].args[0] == sys.executable
    assert 'mock_gimbal.py' in procs[1].args[1]


def test_repeated_start_does_not_duplicate(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    assert sim.start()['success'] is True
    count = len(procs)

    result = sim.start()
    assert result['success'] is False
    assert 'already running' in result['error']
    assert len(procs) == count


def test_stop_then_restart(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    sim.start()
    sim.stop()
    assert sim.status == 'stopped'

    sim.start()
    assert sim.status == 'running'
    # New processes were spawned for the second start.
    assert len(procs) == 4


def test_stop_terminates_own_processes_only(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    sim.start()
    assert all(p.poll() is None for p in procs)

    sim.stop()
    assert all(p.poll() is not None for p in procs)
    # No broad process kill was used — we only touched our own Popen objects.
    assert sim.socat_proc is None
    assert sim.mock_proc is None


def test_status_detects_dead_process(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    sim.start()
    assert sim.get_status()['running'] is True

    # Simulate both child processes dying unexpectedly.
    for p in procs:
        p._alive = False

    status = sim.get_status()
    assert status['running'] is False
    assert status['status'] == 'error'


def test_alias_timeout_fails_gracefully(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    # Aliases never appear -> should time out and clean up.
    _install(monkeypatch, sim, procs, aliases_exist=False)

    result = sim.start()

    assert result['success'] is False
    assert sim.status == 'error'


# --------------------------------------------------------------------------
# Flask API endpoints (mock simulator / physical ports)
# --------------------------------------------------------------------------

def test_serial_endpoints_api(monkeypatch):
    import web_app

    monkeypatch.setattr(web_app, 'get_available_serial_ports', lambda: [
        {'device': '/dev/ttyUSB0', 'description': 'CH340', 'hwid': ''},
    ])

    class FakeSimulator:
        def get_status(self):
            return {
                'status': 'idle', 'running': False,
                'socat_installed': True, 'error': None,
                'device': '/tmp/rmcv_validator', 'label': 'RM Virtual Serial',
            }

    monkeypatch.setattr(web_app, 'simulator', FakeSimulator())

    client = web_app.app.test_client()
    data = client.get('/api/serial_endpoints').get_json()

    assert len(data['endpoints']) == 2
    assert data['endpoints'][0]['kind'] == 'virtual'
    assert data['endpoints'][1]['kind'] == 'physical'
    assert data['virtual']['socat_installed'] is True


def test_simulator_api_lifecycle(monkeypatch):
    import web_app

    state = {'running': False}

    class FakeSimulator:
        def start(self):
            state['running'] = True
            return {'success': True, 'status': 'running'}

        def stop(self):
            state['running'] = False
            return {'success': True, 'status': 'stopped'}

        def get_status(self):
            return {'status': 'running' if state['running'] else 'stopped',
                    'running': state['running']}

    monkeypatch.setattr(web_app, 'simulator', FakeSimulator())

    client = web_app.app.test_client()

    r = client.post('/api/simulator/start').get_json()
    assert r['success'] is True
    assert state['running'] is True

    s = client.get('/api/simulator/status').get_json()
    assert s['running'] is True

    r = client.post('/api/simulator/stop').get_json()
    assert r['success'] is True
    assert state['running'] is False


def test_simulator_start_rejects_duplicate(monkeypatch):
    import web_app

    calls = []

    class FakeSimulator:
        def start(self):
            calls.append('start')
            if len(calls) > 1:
                return {'success': False, 'error': 'Simulator is already running'}
            return {'success': True, 'status': 'running'}

        def stop(self):
            return {'success': True, 'status': 'stopped'}

    monkeypatch.setattr(web_app, 'simulator', FakeSimulator())

    client = web_app.app.test_client()
    assert client.post('/api/simulator/start').get_json()['success'] is True
    assert client.post('/api/simulator/start').get_json()['success'] is False
