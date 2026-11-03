import base64
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
RELS = base64.b64decode(
    'PD94bWwgdmVyc2lvbj0iMS4wIiBlbmNvZGluZz0idXRmLTgiPz4KPFJlbGF0aW9uc2hpcHMgeG1sbnM9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wYWNrYWdlLzIwMDYvcmVsYXRpb25zaGlwcyI+CiAgPFJlbGF0aW9uc2hpcCBUeXBlPSJodHRwOi8vc2NoZW1hcy5taWNyb3NvZnQuY29tL3BhY2thZ2luZy8yMDEwLzA3L21hbmlmZXN0IiBUYXJnZXQ9Ii9SYW52aWVyLldlYkNvcmUuTmF0aXZlLm9zeC1hcm02NC5udXNwZWMiIElkPSJSMjIzMTZFMjM0MzYyNTU4OCIgLz4KICA8UmVsYXRpb25zaGlwIFR5cGU9Imh0dHA6Ly9zY2hlbWFzLm9wZW54bWxmb3JtYXRzLm9yZy9wYWNrYWdlLzIwMDYvcmVsYXRpb25zaGlwcy9tZXRhZGF0YS9jb3JlLXByb3BlcnRpZXMiIFRhcmdldD0iL3BhY2thZ2Uvc2VydmljZXMvbWV0YWRhdGEvY29yZS1wcm9wZXJ0aWVzL251Z2V0LnBzbWRjcCIgSWQ9IlJCMzg1ODE3NzgzQjVEOUYwIiAvPgo8L1JlbGF0aW9uc2hpcHM+')


def zipped(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return stream.getvalue()


class CompletionTransport(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('slim_transport', ROOT / 'scripts/recover_preview12_slim.py')
        self.subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.subject)
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.package = Path(self.temporary.name) / 'native.nupkg'
        self.package.write_bytes(zipped({'_rels/.rels': RELS}))
        self.source = f'package/Ranvier.WebCore.Native.osx-arm64.{self.subject.VERSION}.nupkg'
        self.files = {'helper-completion.json': b'{}', self.source: self.package.read_bytes(), 'timer/helper.dylib': b'helper'}
        self.receipt = dict(originalRun=41733425197, members={name: hashlib.sha256(data).hexdigest()
            for name, data in self.files.items() if name != 'helper-completion.json'})
        self.receipt['members']['stage/_rels/.rels'] = hashlib.sha256(RELS).hexdigest()

    def check(self):
        with zipfile.ZipFile(io.BytesIO(zipped(self.files))) as archive:
            return self.subject.verify_completion_members(archive, self.receipt, self.package)

    def test_single_metadata_omission_is_explicit_package_backed_alias(self):
        result = self.check()
        self.assertEqual(result['missingMember'], 'stage/_rels/.rels')
        self.assertEqual(result['sourcePackageMember'], self.source)
        self.assertEqual(result['sha256'], 'ffdb43dc427c61c172c7c6fa4dc013990649998e9b53fba3193774ce122140d7')

    def test_byte_complete_inventory_has_no_alias(self):
        self.files['stage/_rels/.rels'] = RELS
        self.assertIsNone(self.check())

    def test_missing_helper_is_never_package_backed(self):
        del self.files['timer/helper.dylib']
        with self.assertRaisesRegex(ValueError, 'Unqualified missing'):
            self.check()

    def test_other_run_cannot_inherit_known_transport_exception(self):
        self.receipt['originalRun'] += 1
        with self.assertRaisesRegex(ValueError, 'Unqualified missing'):
            self.check()

    def test_altered_package_cannot_supply_alias_even_with_rehashed_inventory(self):
        self.files[self.source] = zipped({'_rels/.rels': b'changed'})
        self.receipt['members'][self.source] = hashlib.sha256(self.files[self.source]).hexdigest()
        with self.assertRaisesRegex(ValueError, 'Unqualified missing'):
            self.check()

    def test_altered_inner_metadata_rejects_even_if_package_argument_matches(self):
        self.package.write_bytes(zipped({'_rels/.rels': b'changed'}))
        self.files[self.source] = self.package.read_bytes()
        self.receipt['members'][self.source] = self.subject.sha(self.package)
        with self.assertRaisesRegex(ValueError, 'Package metadata alias differs'):
            self.check()

    def test_added_or_changed_direct_member_rejects(self):
        self.files['unrecorded'] = b'extra'
        with self.assertRaisesRegex(ValueError, 'Unexpected completion'):
            self.check()
        del self.files['unrecorded']
        self.files['timer/helper.dylib'] = b'changed'
        with self.assertRaisesRegex(ValueError, 'Completion artifact member differs'):
            self.check()


if __name__ == '__main__':
    unittest.main()
