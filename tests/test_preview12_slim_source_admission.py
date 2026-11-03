import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('slim', ROOT / 'scripts/recover_preview12_slim.py')
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class SourceAdmission(unittest.TestCase):
    def test_untracked_and_ignored_inputs_fail_and_only_generated_outputs_are_allowed_after_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'source'
            root.mkdir()
            def check(untracked=b'', ignored=b'', generated=False):
                with patch.object(subject.subprocess, 'check_output', side_effect=['f\n', '', untracked, ignored]):
                    subject.source_identity(root, 'f', allow_generated=generated)
            check()
            for bad in (b'Directory.Build.props\0', b'src/Ranvier.WebCore/rogue.fs\0'):
                with self.assertRaisesRegex(ValueError, 'untracked or ignored'):
                    check(untracked=bad)
                with self.assertRaisesRegex(ValueError, 'untracked or ignored'):
                    check(ignored=bad, generated=True)
            with self.assertRaisesRegex(ValueError, 'untracked or ignored'):
                check(ignored=b'packaging/obj/generated.props\0')
            check(ignored=b'packaging/obj/generated.props\0', generated=True)

    def test_ancestor_msbuild_import_rejected_case_insensitively(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            root = parent / 'source'
            root.mkdir()
            (parent / 'DIRECTORY.BUILD.PROPS').write_text('<Project/>')
            with patch.object(subject.subprocess, 'check_output', side_effect=['f\n', '', b'', b'']):
                with self.assertRaisesRegex(ValueError, 'ancestor MSBuild'):
                    subject.source_identity(root, 'f')

    def test_native_family_rejects_unknown_mixed_case_and_duplicate_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            product = Path(directory)
            assets = product / 'packaging/obj/project.assets.json'
            assets.parent.mkdir(parents=True)
            good = {f'Ranvier.WebCore.Native.{rid}/{subject.VERSION}': {} for rid in subject.RIDS}
            for extra in ('ranvier.webcore.native.unknown/1', 'RANVIER.WEBCORE.NATIVE.linux-x64/other',
                          f'ranvier.webcore.native.linux-x64/{subject.VERSION}'):
                assets.write_text(json.dumps({'libraries': dict(good, **{extra: {}})}))
                with self.assertRaisesRegex(ValueError, 'native graph'):
                    subject.verify_restore(product, product, product, {})


if __name__ == '__main__':
    unittest.main()
