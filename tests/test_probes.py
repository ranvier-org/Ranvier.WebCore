"""Check scripts/probes.py: every probe runs past failures, and the workflow states no probe of its own."""

from pathlib import Path
import importlib.util
import io
import os
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
    def test_probe_environment_reaches_the_child_without_changing_the_parent(self):
        entry = probes.probe('environment', 'python -c "import os; print(os.environ.get(\'RANVIER_PROBE_ENV_TEST\'))"')
        entry['env'] = {'RANVIER_PROBE_ENV_TEST': 'isolated-child'}
        before = os.environ.get('RANVIER_PROBE_ENV_TEST')
        code, _, logs = run([entry])
        self.assertEqual(code, 0)
        self.assertIn('isolated-child', next(logs.glob('01-*.log')).read_text())
        self.assertEqual(os.environ.get('RANVIER_PROBE_ENV_TEST'), before)

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
    def test_c_abi_layout_probe_runs_for_every_native_flavor(self):
        layouts = [entry for entry in probes.PROBES if 'tests/abi/abi_layouts.py' in ' '.join(entry['commands'])]
        self.assertEqual(len(layouts), 1)
        self.assertEqual(layouts[0]['flavor'], None)
        self.assertIsNone(layouts[0]['rid'])
        for flavor in ['slim', 'gpu', 'lean']:
            for rid in ['win-x64', 'linux-x64', 'osx-arm64']:
                self.assertTrue(probes.applies(layouts[0], rid, flavor), (rid, flavor))

    def test_windows_gpu_selects_real_transition_snapshot_pixels(self):
        selected = [entry for entry in probes.PROBES if probes.applies(entry, 'win-x64', 'gpu')]
        pixels = [entry for entry in selected if any('windows_view_transition_pixels.py' in command for command in entry['commands'])]
        self.assertEqual(len(pixels), 1)
        self.assertIn('--native-directory ' + probes.NATIVE, pixels[0]['commands'][0])
        self.assertIn('--output {work}/gpu-transition-readback', pixels[0]['commands'][0])
        self.assertFalse(probes.applies(pixels[0], 'win-x64', 'slim'))
        self.assertFalse(probes.applies(pixels[0], 'linux-x64', 'gpu'))

    def test_common_contracts_run_on_slim_and_gpu_without_broadening_explicit_flavors(self):
        common = probes.probe('common', 'python common.py')
        slim = probes.probe('slim only', 'python slim.py', flavor='slim')
        gpu = probes.probe('gpu only', 'python gpu.py', flavor='gpu')
        every = probes.probe('every', 'python every.py', flavor=None)
        for flavor in ['slim', 'gpu']:
            self.assertTrue(probes.applies(common, 'linux-x64', flavor), flavor)
            self.assertTrue(probes.applies(every, 'linux-x64', flavor), flavor)
        self.assertFalse(probes.applies(common, 'linux-x64', 'lean'))
        self.assertFalse(probes.applies(slim, 'linux-x64', 'gpu'))
        self.assertFalse(probes.applies(gpu, 'linux-x64', 'slim'))
        self.assertTrue(probes.applies(every, 'linux-x64', 'lean'))

    def test_linux_gpu_runs_the_complete_reviewed_common_and_gpu_catalogue(self):
        for rid in ['linux-x64', 'linux-arm64']:
            selected = [entry for entry in probes.PROBES if probes.applies(entry, rid, 'gpu')]
            commands = '\n'.join(command for entry in selected for command in entry['commands'])
            for script in ['coordinate_spaces.py', 'web_animations.py', 'data_transfer.py',
                           'linux_view_transition_pixels.py', 'compositor_reattach.py']:
                self.assertIn(script, commands, rid)
            for entry in selected:
                if entry['rid'] is not None:
                    self.assertEqual(entry['rid'], rid)
    def test_linux_gpu_selects_real_transition_snapshot_pixels_for_both_linux_rids(self):
        for rid in ['linux-x64', 'linux-arm64']:
            selected = [entry for entry in probes.PROBES if probes.applies(entry, rid, 'gpu')]
            pixels = [entry for entry in selected if any('tests/gpu/linux_view_transition_pixels.py' in command for command in entry['commands'])]
            self.assertEqual(len(pixels), 1, rid)
            self.assertEqual(pixels[0]['commands'], [
                'python -I tests/gpu/linux_view_transition_pixels.py --native-directory ' + probes.NATIVE])
            self.assertEqual(pixels[0]['env'], {'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'})
            self.assertFalse(probes.applies(pixels[0], rid, 'slim'))

    def test_linux_gpu_selects_the_egl_image_probe_for_both_linux_rids(self):
        for rid in ['linux-x64', 'linux-arm64']:
            selected = [entry for entry in probes.PROBES if probes.applies(entry, rid, 'gpu')]
            frames = [entry for entry in selected if any('tests/gpu/linux_egl.py' in command for command in entry['commands'])]
            self.assertEqual(len(frames), 1, rid)
            self.assertEqual(len(frames[0]['commands']), 2, rid)
            self.assertIn(probes.NATIVE + '/libRanvierWebCoreHost.so', frames[0]['commands'][0])
            self.assertNotIn('--context-lifecycle', frames[0]['commands'][0])
            self.assertEqual(frames[0]['commands'][1], frames[0]['commands'][0] + ' --context-lifecycle')
            self.assertEqual(frames[0]['env'], {'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'})
            self.assertFalse(probes.applies(frames[0], rid, 'slim'))
            self.assertFalse(probes.applies(frames[0], 'win-x64', 'gpu'))

    def test_windows_gpu_runs_actual_shared_frame_and_lifetime_acceptance(self):
        selected = [entry for entry in probes.PROBES if probes.applies(entry, 'win-x64', 'gpu')]
        frames = [entry for entry in selected if any('tests/gpu/run.py' in command for command in entry['commands'])]
        self.assertEqual(len(frames), 1)
        commands = frames[0]['commands']
        self.assertIn('scripts/sdl_runtime.py', commands[0])
        self.assertIn('--native ' + probes.NATIVE, commands[1])
        self.assertIn('--teardown all', commands[1])
        self.assertFalse(probes.applies(frames[0], 'win-x64', 'slim'))
        self.assertFalse(probes.applies(frames[0], 'linux-x64', 'gpu'))

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
