import importlib.util
import os
from pathlib import Path
import tempfile
import signal
import subprocess
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class PublicReplayBundle(unittest.TestCase):
    def test_default_reference_cannot_be_labeled_as_vector_qualification(self):
        spec = importlib.util.spec_from_file_location('public_cocoa_replay', ROOT / 'tests/controls/public_cocoa_replay.py')
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        self.assertTrue(hasattr(subject, 'default_reference'), 'The default appearance reference must be checked separately')
        report = dict(assertions=59, failures=[], rows=[dict(label=str(i), vectorProfile=False, sha256='a' * 64) for i in range(6)])
        self.assertEqual(len(subject.default_reference(report)['images']), 6)
        report['rows'][0]['vectorProfile'] = True
        with self.assertRaisesRegex(ValueError, 'legacy'):
            subject.default_reference(report)

    @unittest.skipIf(os.name == 'nt', 'The macOS runner uses POSIX process groups')
    def test_controller_exit_reaps_a_reparented_separate_process_group(self):
        spec = importlib.util.spec_from_file_location('public_cocoa_replay', ROOT / 'tests/controls/public_cocoa_replay.py')
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pid_file = root / 'child.pid'
            worker = root / 'worker.py'
            worker.write_text('import subprocess, sys, time\nfrom pathlib import Path\n'
                              'child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)\n'
                              'Path(sys.argv[1]).write_text(str(child.pid))\ntime.sleep(0.6)\n')
            try:
                with (root / 'run.log').open('wb') as stream:
                    self.assertEqual(subject.run_controller([sys.executable, '-I', str(worker), str(pid_file)],
                                                           stream, dict(os.environ)), 0)
                pid = int(pid_file.read_text())
                status = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True).stdout.strip()
                self.assertTrue(not status or status.startswith('Z'), 'The reparented helper remained running')
            finally:
                if pid_file.exists():
                    try:
                        os.killpg(int(pid_file.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_parent_traversal_in_reviewed_artifact_is_still_rejected(self):
        path = ROOT / 'tests/controls/public_cocoa_replay.py'
        self.assertTrue(path.exists(), 'The public replay needs safe artifact extraction')
        spec = importlib.util.spec_from_file_location('public_cocoa_replay', path)
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'artifact.zip'
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr('../escaped', b'outside')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                subject.extract_artifact(archive, root / 'output')
            self.assertFalse((root / 'escaped').exists())


if __name__ == '__main__':
    unittest.main()
