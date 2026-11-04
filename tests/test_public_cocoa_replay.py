import importlib.util
import json
import os
from pathlib import Path
import tempfile
import signal
import subprocess
import sys
import unittest
from unittest import mock
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

    def test_symlink_member_in_reviewed_artifact_is_rejected(self):
        subject = load_subject()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / 'artifact.zip'
            member = zipfile.ZipInfo('helper')
            member.external_attr = (0o120777 << 16)
            with zipfile.ZipFile(archive, 'w') as stream:
                stream.writestr(member, '/etc/passwd')
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                subject.extract_artifact(archive, root / 'output')

    def test_acceptance_requires_every_gate_and_a_main_branch_run(self):
        subject = load_subject()
        main = dict(repository='ranvier-org/Ranvier.WebCore', ref='refs/heads/main', sha='b' * 40, run_id='1')
        passing = dict(accepted=True)
        references = dict(acceptedAsReferences=True)
        self.assertTrue(subject.final_acceptance(0, passing, references, main))
        self.assertFalse(subject.final_acceptance(1, passing, references, main))
        self.assertFalse(subject.final_acceptance(0, dict(accepted=False), references, main))
        self.assertFalse(subject.final_acceptance(0, dict(accepted='true'), references, main))
        self.assertFalse(subject.final_acceptance(0, passing, dict(acceptedAsReferences=1), main))
        self.assertFalse(subject.final_acceptance(0, passing, {}, main))
        self.assertFalse(subject.final_acceptance(0, passing, references, dict(main, ref='refs/heads/feature')))
        self.assertFalse(subject.final_acceptance(0, passing, references, dict(main, repository='fork/Ranvier.WebCore')))

    def test_unarmed_inputs_are_refused_before_any_output(self):
        subject = load_subject()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            inputs = root / 'inputs.json'
            inputs.write_text(json.dumps(dict(armed=False, policy=None)))
            with self.assertRaisesRegex(ValueError, 'unarmed'):
                run_main(subject, inputs, root, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_controller_source_other_than_policy_is_refused(self):
        subject = load_subject()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_source(root)
            inputs = root / 'inputs.json'
            inputs.write_text(json.dumps(dict(armed=True, policy=dict(controllerSource='0' * 40))))
            with self.assertRaisesRegex(ValueError, 'Immutable controller source'):
                run_main(subject, inputs, source, root / 'out')
            self.assertFalse((root / 'out').exists())

    def test_producer_artifact_digest_mismatch_leaves_an_unaccepted_receipt(self):
        subject = load_subject()
        real_run = subprocess.run

        def fake_run(command, *args, **kwargs):
            if command[0] == 'gh':
                kwargs['stdout'].write(b'not the reviewed artifact')
                return subprocess.CompletedProcess(command, 0)
            return real_run(command, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = make_source(root)
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
            inputs = root / 'inputs.json'
            inputs.write_text(json.dumps(dict(armed=True, artifact=dict(id=7, sha256='a' * 64),
                                              policy=dict(controllerSource=head))))
            with (mock.patch.object(subject.subprocess, 'run', fake_run),
                  self.assertRaisesRegex(ValueError, 'Producer artifact bytes differ')):
                run_main(subject, inputs, source, root / 'out')
            receipt = json.loads((root / 'out/replay-receipt.json').read_text())
            self.assertIs(receipt['accepted'], False)
            self.assertIn('Producer artifact', receipt['failure'])
            self.assertEqual(receipt['controllerSource'], head)
            self.assertEqual(set(receipt['run']), {'repository', 'ref', 'sha', 'run_id', 'run_attempt'})
            self.assertFalse((root / 'out/sidecars').exists())


def load_subject():
    spec = importlib.util.spec_from_file_location('public_cocoa_replay', ROOT / 'tests/controls/public_cocoa_replay.py')
    subject = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(subject)
    return subject


def make_source(root):
    source = root / 'source'
    source.mkdir()
    git = ['git', '-c', 'user.name=test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false']
    subprocess.run(['git', 'init', '-q'], cwd=source, check=True)
    (source / 'README').write_text('controller')
    subprocess.run(['git', 'add', 'README'], cwd=source, check=True)
    subprocess.run([*git, 'commit', '-q', '-m', 'controller'], cwd=source, check=True)
    return source


def run_main(subject, inputs, source, output):
    argv = ['public_cocoa_replay.py', '--inputs', str(inputs), '--source', str(source), '--output', str(output)]
    with mock.patch.object(sys, 'argv', argv):
        return subject.main()

if __name__ == '__main__':
    unittest.main()
