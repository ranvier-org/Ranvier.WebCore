import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


class StageNativeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='atspi-artifact-')
        self.root = Path(self.temporary.name)
        self.artifact = self.root / 'artifact'
        self.artifact.mkdir()
        self.output = self.root / 'native'
        self.member = 'runtimes/linux-x64/native/libRanvierWebCoreHost.so'
        self.content = b'isolated exact native payload'

    def tearDown(self):
        self.temporary.cleanup()

    def package(self, name='native.nupkg', members=None):
        with zipfile.ZipFile(self.artifact / name, 'w') as archive:
            for member, content in members or [(self.member, self.content)]:
                archive.writestr(member, content)

    def stage(self, digest=None):
        return subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('stage_native.py')),
            '--artifacts', str(self.artifact), '--rid', 'linux-x64',
            '--expected-sha256', digest or hashlib.sha256(self.content).hexdigest(),
            '--output', str(self.output)], capture_output=True)

    def test_exact_payload_only(self):
        self.package(members=[(self.member, self.content), ('../../must-not-extract', b'unsafe member')])
        result = self.stage()
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual((self.output / 'libRanvierWebCoreHost.so').read_bytes(), self.content)
        self.assertFalse((self.root / 'must-not-extract').exists())

    def test_bad_checksum_creates_no_output(self):
        self.package()
        self.assertNotEqual(self.stage('0' * 64).returncode, 0)
        self.assertFalse(self.output.exists())

    def test_multiple_matching_packages_reject(self):
        self.package('first.nupkg')
        self.package('second.nupkg')
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_wrong_rid_rejects(self):
        self.package(members=[('runtimes/linux-arm64/native/libRanvierWebCoreHost.so', self.content)])
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_existing_stage_not_overwritten(self):
        self.package()
        self.output.mkdir()
        (self.output / 'sentinel').write_bytes(b'keep')
        self.assertNotEqual(self.stage().returncode, 0)
        self.assertEqual((self.output / 'sentinel').read_bytes(), b'keep')


if __name__ == '__main__':
    unittest.main()
