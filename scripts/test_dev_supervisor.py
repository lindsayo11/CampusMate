"""Fault injection for restart budget and group cleanup; no real servers."""
import unittest
from unittest.mock import patch
import dev_supervisor as supervisor


class SupervisorTests(unittest.TestCase):
    def test_crash_budget_stops_all_groups(self):
        processes = []
        class Process:
            def __init__(self, *args, **kwargs):
                self.pid = 1000 + len(processes)
                self.returncode = 1
                processes.append(self)
            def poll(self):
                return self.returncode
            def wait(self):
                return self.returncode
        with patch.object(supervisor.subprocess, 'Popen', Process), patch.object(supervisor.os, 'killpg') as kill, patch.object(supervisor.signal, 'signal'), patch.object(supervisor.time, 'sleep'):
            self.assertEqual(supervisor.main(), 1)
        self.assertEqual(len(processes), 12)  # initial + three restarts per service
        for p in processes[-3:]:
            self.assertIn(unittest.mock.call(p.pid, supervisor.signal.SIGTERM), kill.call_args_list)

    def test_interrupt_cleans_started_groups(self):
        p = unittest.mock.Mock(pid=999, returncode=0)
        p.poll.return_value = 0
        with patch.object(supervisor.subprocess, 'Popen', side_effect=[p, KeyboardInterrupt]), patch.object(supervisor.os, 'killpg') as kill, patch.object(supervisor.signal, 'signal'):
            self.assertEqual(supervisor.main(), 0)
        kill.assert_any_call(999, supervisor.signal.SIGTERM)
        p.wait.assert_called_once()


if __name__ == '__main__':
    unittest.main()
