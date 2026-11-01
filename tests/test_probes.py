"""Check scripts/probes.py: every probe runs past failures, and the workflow states no probe of its own."""

from pathlib import Path
import importlib.util
import io
import contextlib
import tempfile
import time
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('probes', ROOT / 'scripts/probes.py')
probes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probes)


def run(entries, *options):
    """(exit code, summary lines, log directory) of a run over the entries in place of the probe list."""
    saved = probes.PROBES
    probes.PROBES = entries
    logs = Path(tempfile.mkdtemp())
    try:
        with contextlib.redirect_stdout(io.TextIOWrapper(io.BytesIO(), write_through=True)):
            code = probes.main(['run', '--rid', 'linux-x64', '--flavor', 'slim', '--work', str(logs),
                                '--logs', str(logs), *options])
    finally:
        probes.PROBES = saved
    return code, (logs / 'summary.txt').read_text().splitlines(), logs


class ProbeRunnerTests(unittest.TestCase):
    def test_a_failure_runs_the_later_probes_and_fails_the_run(self):
        code, summary, _ = run([probes.probe('fails', 'python -c "raise SystemExit(3)"'),
                                probes.probe('passes', 'python -c "print(1)"')])
        self.assertEqual(code, 1)
        self.assertEqual([line.split()[0] for line in summary], ['FAIL', 'PASS'])
        self.assertIn('exit code 3', summary[0])

    def test_a_probe_stops_at_its_first_failing_command(self):
        code, summary, logs = run([probes.probe('two', 'python -c "raise SystemExit(1)"', 'python -c "print(\'second\')"')])
        self.assertEqual(code, 1)
        self.assertNotIn('second', next(logs.glob('01-*.log')).read_text())

    def test_a_probe_past_its_timeout_is_killed(self):
        start = time.monotonic()
        code, summary, _ = run([probes.probe('sleeps', 'python -c "import time; time.sleep(60)"', timeout=1)])
        self.assertEqual(code, 1)
        self.assertIn('timed out', summary[0])
        self.assertLess(time.monotonic() - start, 30)

    def test_conditions_select_by_rid_and_flavor(self):
        code, summary, _ = run([probes.probe('windows', 'python -c "raise SystemExit(1)"', rid='win-x64'),
                                probes.probe('gpu', 'python -c "raise SystemExit(1)"', flavor='gpu'),
                                probes.probe('every', 'python -c "print(1)"', flavor=None)])
        self.assertEqual((code, len(summary)), (0, 1))

    def test_the_output_reaches_the_log(self):
        _, _, logs = run([probes.probe('prints', 'python -c "print(\'hello from the probe\')"')])
        self.assertIn('hello from the probe', next(logs.glob('01-*.log')).read_text())


    @unittest.skipUnless(sys.platform == 'linux', 'prctl is Linux only')
    def test_no_dump_runs_the_script_in_a_non_dumpable_interpreter(self):
        script = Path(tempfile.mkdtemp()) / 'dumpable.py'
        script.write_text("import ctypes, sys\nprint('dumpable', ctypes.CDLL(None).prctl(3), sys.argv[1:])\n")
        _, _, logs = run([probes.probe('dumpable', f'python -I {script.as_posix()} --flag x')], '--no-dump')
        self.assertIn("dumpable 0 ['--flag', 'x']", next(logs.glob('01-*.log')).read_text())


class WorkflowTests(unittest.TestCase):
    def test_the_native_job_runs_its_probes_through_the_runner(self):
        workflow = (ROOT / '.github/workflows/build.yml').read_text()
        native = workflow.split('\n  native:\n', 1)[1].split('\n  managed:\n', 1)[0]
        self.assertIn('python -I scripts/probes.py run', native)
        for script in ['tests/abi/', 'tests/uia/', 'tests/generator/native_types.py']:
            self.assertNotIn(script, native)

    def test_every_probe_script_exists(self):
        for entry in probes.PROBES:
            for command in entry['commands']:
                script = next(word for word in command.split() if word.endswith('.py'))
                self.assertTrue((ROOT / script).exists(), script)


if __name__ == '__main__':
    unittest.main()
