import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class NativePackages(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('slim', ROOT / 'scripts/recover_preview12_slim.py')
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / 'fixture.nupkg'
        self.binary = bytearray(20)
        self.binary[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HH', self.binary, 16, 3, 62)
        self.payload = bytes(self.binary)
        self.manifest = dict(rid='linux-x64', flavor='slim', version=self.subject.VERSION, abi=64, webkit=self.subject.WEBKIT,
                             source=dict(commit=self.subject.PRODUCT, dirty=False, builder='ci'),
                             files=[dict(name='libRanvierWebCoreHost.so', bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest())],
                             total_bytes=len(self.payload))
        self.extra = False

    def tearDown(self):
        self.temporary.cleanup()

    def check(self):
        with zipfile.ZipFile(self.path, 'w') as archive:
            archive.writestr('fixture.nuspec', '<package><metadata><id>Ranvier.WebCore.Native.linux-x64</id><version>' + self.subject.VERSION + '</version></metadata></package>')
            archive.writestr('manifest.json', json.dumps(self.manifest))
            archive.writestr('runtimes/linux-x64/native/libRanvierWebCoreHost.so', self.payload)
            if self.extra:
                archive.writestr('runtimes/linux-x64/native/unrecorded.dat', b'unrecorded')
        return self.subject.verify_native(self.path, 'linux-x64', self.subject.sha(self.path))

    def test_complete_matching_native_metadata_passes(self):
        self.assertEqual(self.check(), self.manifest)

    def test_payload_change_rejects_even_when_outer_package_digest_is_updated(self):
        self.payload += b'tampered'
        with self.assertRaisesRegex(ValueError, 'payload'):
            self.check()

    def test_unknown_native_payload_rejects(self):
        self.extra = True
        with self.assertRaisesRegex(ValueError, 'payload'):
            self.check()

    def test_wrong_elf_machine_rejects_even_with_correct_hash_and_manifest(self):
        struct.pack_into('<H', self.binary, 18, 183)
        self.payload = bytes(self.binary)
        self.manifest['files'][0]['sha256'] = hashlib.sha256(self.payload).hexdigest()
        with self.assertRaisesRegex(ValueError, 'architecture'):
            self.check()

    def test_wrong_abi_source_and_flavor_reject(self):
        for name, value in [('abi', 63), ('abi', True), ('flavor', 'gpu'), ('source', dict(commit='a' * 40, dirty=False, builder='ci'))]:
            original = self.manifest[name]
            self.manifest[name] = value
            with self.assertRaisesRegex(ValueError, 'cohort'):
                self.check()
            self.manifest[name] = original


if __name__ == '__main__':
    unittest.main()
