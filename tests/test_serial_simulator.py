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
# Flask API endpoints removed - simulator auto-starts with virtual endpoints
# The unified UX implementation auto-starts/stops simulators when selecting
# virtual endpoints, so explicit /api/simulator/* endpoints are obsolete.
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Error injection modes
# --------------------------------------------------------------------------

def test_error_injection_mode_normal(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start(mode='normal')

    assert result['success'] is True
    assert sim.current_mode == 'normal'
    assert '--mode' in procs[1].args
    assert 'normal' in procs[1].args


def test_error_injection_mode_invalid_mode(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start(mode='invalid_mode')

    assert result['success'] is True
    assert sim.current_mode == 'invalid_mode'
    assert '--mode' in procs[1].args
    assert 'invalid_mode' in procs[1].args


def test_error_injection_mode_invalid_quaternion(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start(mode='invalid_quaternion')

    assert result['success'] is True
    assert sim.current_mode == 'invalid_quaternion'
    assert '--mode' in procs[1].args
    assert 'invalid_quaternion' in procs[1].args


def test_error_injection_mode_bad_crc(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start(mode='bad_crc')

    assert result['success'] is True
    assert sim.current_mode == 'bad_crc'
    assert '--mode' in procs[1].args
    assert 'bad_crc' in procs[1].args


def test_error_injection_invalid_mode_rejected(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start(mode='arbitrary_string')

    assert result['success'] is False
    assert 'Invalid error injection mode' in result['error']
    assert sim.status == 'error'
    assert len(procs) == 0  # No processes spawned


def test_error_injection_mode_default_is_normal(monkeypatch, tmp_path):
    sim = SerialSimulator(repo_root=tmp_path)
    procs = []
    _install(monkeypatch, sim, procs)

    result = sim.start()  # No mode argument

    assert result['success'] is True
    assert sim.current_mode == 'normal'
    assert '--mode' in procs[1].args
    assert 'normal' in procs[1].args
