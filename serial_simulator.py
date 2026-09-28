"""Serial simulator lifecycle manager.

Manages the virtual serial endpoint used by Live mode:

    mock_gimbal.py  ──writes──▶  /tmp/rmcv_mock
                                        │ (socat PTY bridge)
                                        ▼
                                 /tmp/rmcv_validator  ◀──read by Validator

The Web backend is the sole owner of these child processes. It only ever
stops the Popen objects it created itself — never a broad ``pkill``.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path


class SerialSimulator:
    """Manages the virtual serial endpoint (socat PTY pair + mock node)."""

    LABEL = "RM Virtual Serial"
    MOCK_DEVICE = "/tmp/rmcv_mock"           # mock node writes here
    VALIDATOR_DEVICE = "/tmp/rmcv_validator"  # validator reads here

    STATUS_IDLE = 'idle'
    STATUS_STARTING = 'starting'
    STATUS_RUNNING = 'running'
    STATUS_STOPPED = 'stopped'
    STATUS_ERROR = 'error'

    ALIAS_WAIT_TIMEOUT = 5.0
    MOCK_START_GRACE = 0.3

    # Whitelist of allowed error injection modes (matches mock_gimbal.py)
    VALID_MODES = ['normal', 'invalid_mode', 'invalid_quaternion', 'bad_crc']

    def __init__(self, repo_root=None):
        if repo_root is None:
            repo_root = Path(__file__).parent
        self.repo_root = Path(repo_root)
        self.socat_proc = None
        self.mock_proc = None
        self._socat_log = None
        self._mock_log = None
        self.status = self.STATUS_IDLE
        self.error = None
        self.current_mode = 'normal'
        self._lock = threading.Lock()

    # ---- helpers ---------------------------------------------------------

    @property
    def socat_installed(self):
        return shutil.which('socat') is not None

    def _mock_script(self):
        return self.repo_root / 'tools' / 'mock_serial_node' / 'mock_gimbal.py'

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

    def _clean_aliases(self):
        """Remove only our own /tmp/rmcv_* symlinks (never a broad pkill)."""
        for alias in (self.MOCK_DEVICE, self.VALIDATOR_DEVICE):
            try:
                if os.path.islink(alias) or os.path.exists(alias):
                    os.unlink(alias)
            except OSError:
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
        """Kill our own child processes and clean aliases (no status change)."""
        self._stop_process(self.mock_proc)
        self._stop_process(self.socat_proc)
        self.mock_proc = None
        self.socat_proc = None
        self._close_log(self._mock_log)
        self._close_log(self._socat_log)
        self._mock_log = None
        self._socat_log = None
        self._clean_aliases()

    # ---- public lifecycle -------------------------------------------------

    def start(self, mode='normal'):
        """
        Start the serial simulator with specified error injection mode.

        Args:
            mode: Error injection mode ('normal', 'invalid_mode', 'invalid_quaternion', 'bad_crc')
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

        if not self.socat_installed:
            self.status = self.STATUS_ERROR
            self.error = 'socat is not installed. Run: sudo apt install socat'
            return {'success': False, 'error': self.error}

        if self.status in (self.STATUS_RUNNING, self.STATUS_STARTING):
            return {'success': False, 'error': 'Simulator is already running'}

        # Clean slate: stop any leftover own processes/aliases.
        self._cleanup_processes()
        self.status = self.STATUS_STARTING
        self.error = None
        self.current_mode = mode

        # 1) Start the socat PTY bridge.
        try:
            self._socat_log = self._open_log('simulator_socat.log')
            self.socat_proc = subprocess.Popen(
                ['socat', '-d', '-d',
                 'pty,raw,echo=0,link={}'.format(self.MOCK_DEVICE),
                 'pty,raw,echo=0,link={}'.format(self.VALIDATOR_DEVICE)],
                stdout=self._socat_log,
                stderr=self._socat_log,
            )
        except Exception as e:
            self.status = self.STATUS_ERROR
            self.error = 'socat start failed: {}'.format(e)
            return {'success': False, 'error': self.error}

        # 2) Wait for the fixed aliases to appear.
        deadline = time.time() + self.ALIAS_WAIT_TIMEOUT
        ready = False
        while time.time() < deadline:
            if os.path.exists(self.MOCK_DEVICE) and os.path.exists(self.VALIDATOR_DEVICE):
                ready = True
                break
            if self.socat_proc.poll() is not None:
                break
            time.sleep(0.1)

        if not ready:
            self.status = self.STATUS_ERROR
            self.error = 'Virtual serial aliases did not appear (timeout or socat exited)'
            self._cleanup_processes()
            return {'success': False, 'error': self.error}

        # 3) Start the mock gimbal node with specified error mode.
        try:
            self._mock_log = self._open_log('simulator_mock.log')
            self.mock_proc = subprocess.Popen(
                [sys.executable, str(self._mock_script()),
                 self.MOCK_DEVICE, '--mode', mode, '--rate', '10'],
                stdout=self._mock_log,
                stderr=self._mock_log,
            )
        except Exception as e:
            self.status = self.STATUS_ERROR
            self.error = 'mock node start failed: {}'.format(e)
            self._cleanup_processes()
            return {'success': False, 'error': self.error}

        # Give the mock a moment, then confirm it did not immediately exit.
        time.sleep(self.MOCK_START_GRACE)
        if self.mock_proc.poll() is not None:
            self.status = self.STATUS_ERROR
            self.error = 'mock node exited unexpectedly (see logs/simulator_mock.log)'
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
        """Return current status, refreshing liveness of dead processes."""
        with self._lock:
            if self.status == self.STATUS_RUNNING:
                socat_alive = self.socat_proc is not None and self.socat_proc.poll() is None
                mock_alive = self.mock_proc is not None and self.mock_proc.poll() is None
                if not (socat_alive and mock_alive):
                    self.status = self.STATUS_ERROR
                    self.error = 'Simulator process exited unexpectedly'

            return {
                'status': self.status,
                'running': self.status == self.STATUS_RUNNING,
                'socat_installed': self.socat_installed,
                'error': self.error,
                'device': self.VALIDATOR_DEVICE,
                'label': self.LABEL,
            }
