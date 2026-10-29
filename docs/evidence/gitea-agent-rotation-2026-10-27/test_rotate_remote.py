"""Regression checks for systemd Type=simple environment readiness."""

import runpy
import unittest
from pathlib import Path
from unittest.mock import patch

HELPER = Path(__file__).with_name('rotate_remote.py')
READY = runpy.run_path(str(HELPER), run_name='rotation_test')['loaded_git_settings']
GLOBALS = READY.__globals__


class EnvironmentReadinessTests(unittest.TestCase):
    def setUp(self):
        self.pid = '123'
        self.url = 'http://localhost:3000/alexar76/aicom.git'
        settings = {**GLOBALS['GIT_SETTINGS'], 'SKOPOS_AGENT_REPO_URL': self.url}
        self.environ = b'\0'.join(key.encode() + b'=' + value.encode() for key, value in settings.items())
        self.state = {'ActiveState': 'active', 'MainPID': self.pid}

    def test_waits_for_exec_environment(self):
        with (patch.dict(GLOBALS, unit_state=lambda: self.state),
              patch.object(Path, 'read_bytes', side_effect=[b'', self.environ]),
              patch.object(GLOBALS['time'], 'sleep') as sleep):
            READY(self.pid, self.url)
        sleep.assert_called_once_with(0.1)

    def test_missing_environment_times_out_without_values(self):
        with (patch.dict(GLOBALS, unit_state=lambda: self.state),
              patch.object(Path, 'read_bytes', return_value=b''),
              patch.object(GLOBALS['time'], 'sleep') as sleep,
              self.assertRaisesRegex(RuntimeError, '^Agent environment readiness timed out; values withheld$')):
            READY(self.pid, self.url)
        self.assertEqual(sleep.call_count, 50)

    def test_replaced_process_is_rejected(self):
        with (patch.dict(GLOBALS, unit_state=lambda: {**self.state, 'MainPID': '456'}),
              patch.object(Path, 'read_bytes') as read, self.assertRaises(AssertionError)):
            READY(self.pid, self.url)
        read.assert_not_called()


if __name__ == '__main__':
    unittest.main()
