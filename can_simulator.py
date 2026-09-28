"""CAN simulator lifecycle manager.

Manages the virtual CAN endpoint used by Live mode:

    vcan0 (must exist)  ◀──read by Validator
       ▲
       │
    Mock EC writes here

The Web backend is the sole owner of the Mock EC child process.
vcan0 preparation (modprobe, ip link) must be done by start_sim.sh
before the Web starts — Flask never runs sudo or arbitrary shell commands.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


class CANSimulator:
    """Manages the virtual CAN endpoint (Mock EC on vcan0)."""

    LABEL = "RM Virtual CAN"
    INTERFACE = "vcan0"

    STATUS_IDLE = 'idle'
    STATUS_STARTING = 'starting'
    STATUS_RUNNING = 'running'
    STATUS_STOPPED = 'stopped'
    STATUS_ERROR = 'error'

    MOCK_START_GRACE = 0.3

    # Valid error injection modes (whitelist)
    VALID_MODES = ['normal', 'invalid_enum', 'invalid_quaternion', 'unknown_id']

    def __init__(self, repo_root=None):
        if repo_root is None:
            repo_root = Path(__file__).parent
        self.repo_root = Path(repo_root)
        self.mock_proc = None
        self._mock_log = None
        self.status = self.STATUS_IDLE
        self.error = None
        self.current_mode = 'normal'  # Track current error injection mode
        self._lock = threading.Lock()

    # ---- helpers ---------------------------------------------------------

    def _mock_executable(self):
        return self.repo_root / 'tools' / 'mock_ec_node' / 'build' / 'mock_ec_node'

    def _open_log(self, name):
        log_dir = self.repo_root / 'logs'
        log_dir.mkdir(parents=True, exist_ok=True)
        return open(log_dir / name, 'w', encoding='utf-8')

    @staticmethod
    def _close_log(handle):
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

    @staticmethod
    def _stop_process(proc):
        if proc is None:
            return
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=2.0)
                except Exception:
                    pass
            except Exception:
                pass

    def _cleanup_processes(self):
        """Kill our own child process (no status change)."""
        self._stop_process(self.mock_proc)
        self.mock_proc = None
        self._close_log(self._mock_log)
        self._mock_log = None

    @property
    def vcan_available(self):
        """Check if vcan0 exists (must be created by start_sim.sh, not by us)."""
        try:
            result = subprocess.run(
                ['ip', 'link', 'show', self.INTERFACE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2.0
            )
            return result.returncode == 0
        except Exception:
            return False

    @property
    def mock_built(self):
        """Check if Mock EC node is built."""
        return self._mock_executable().exists()

    # ---- public lifecycle -------------------------------------------------

    def start(self, mode='normal'):
        """Start the CAN simulator with specified error injection mode.

        Args:
            mode: Error injection mode from VALID_MODES whitelist
        """
        with self._lock:
            return self._start_locked(mode)

    def stop(self):
        with self._lock:
            return self._stop_locked()

    def cleanup(self):
        """Idempotent shutdown for process exit (atexit)."""
        self.stop()

    def _start_locked(self, mode='normal'):
        # Validate mode against whitelist
        if mode not in self.VALID_MODES:
            self.status = self.STATUS_ERROR
            self.error = f'Invalid error injection mode: {mode}. Valid modes: {", ".join(self.VALID_MODES)}'
            return {'success': False, 'error': self.error}

        if not self.mock_built:
            self.status = self.STATUS_ERROR
            self.error = 'Mock EC node not built. Run: cd tools/mock_ec_node && ./build.sh'
            return {'success': False, 'error': self.error}

        if not self.vcan_available:
            self.status = self.STATUS_ERROR
            self.error = f'{self.INTERFACE} not available. Run start_sim.sh (it sets up vcan0).'
            return {'success': False, 'error': self.error}

        if self.status in (self.STATUS_RUNNING, self.STATUS_STARTING):
            return {'success': False, 'error': 'Simulator is already running'}

        # Clean slate: stop any leftover own process.
        self._cleanup_processes()
        self.status = self.STATUS_STARTING
        self.error = None
        self.current_mode = mode

        # Start Mock EC node with positional mode argument (NOT --mode)
        try:
            self._mock_log = self._open_log('can_simulator_mock.log')
            self.mock_proc = subprocess.Popen(
                [str(self._mock_executable()), self.INTERFACE, mode],  # Fixed: positional mode
                stdout=self._mock_log,
                stderr=self._mock_log,
                shell=False  # Explicit: no shell injection
            )
        except Exception as e:
            self.status = self.STATUS_ERROR
            self.error = f'Mock EC start failed: {e}'
            self._cleanup_processes()
            return {'success': False, 'error': self.error}

        # Give the mock a moment, then confirm it did not immediately exit.
        time.sleep(self.MOCK_START_GRACE)
        if self.mock_proc.poll() is not None:
            self.status = self.STATUS_ERROR
            self.error = 'Mock EC exited unexpectedly (see logs/can_simulator_mock.log)'
            self._cleanup_processes()
            return {'success': False, 'error': self.error}

        self.status = self.STATUS_RUNNING
        return {'success': True, 'status': self.status}

    def _stop_locked(self):
        self._cleanup_processes()
        self.status = self.STATUS_STOPPED
        self.error = None
        return {'success': True, 'status': self.status}

    def get_status(self):
        """Return current status, refreshing liveness of dead process."""
        with self._lock:
            if self.status == self.STATUS_RUNNING:
                mock_alive = self.mock_proc is not None and self.mock_proc.poll() is None
                if not mock_alive:
                    self.status = self.STATUS_ERROR
                    self.error = 'Mock EC process exited unexpectedly'

            return {
                'status': self.status,
                'running': self.status == self.STATUS_RUNNING,
                'vcan_available': self.vcan_available,
                'mock_built': self.mock_built,
                'error': self.error,
                'interface': self.INTERFACE,
                'label': self.LABEL,
                'current_mode': self.current_mode,  # Include current error injection mode
            }
