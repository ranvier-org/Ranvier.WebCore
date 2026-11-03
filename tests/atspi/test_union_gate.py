import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('stage_native', Path(__file__).with_name('stage_native.py'))
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class FinalHostGateTests(unittest.TestCase):
    def setUp(self):
        self.revision = '1' * 40
        self.manifest = dict(rid='linux-arm64', abi=63, source=dict(commit=self.revision, dirty=False, builder='ci'))
        self.exports = {'rv_host_ime_surrounding', 'rv_host_ime_delete_surrounding', 'rv_ax_text_style_run'}

    def test_abi62_is_ineligible(self):
        self.manifest['abi'] = 62
        with self.assertRaisesRegex(ValueError, 'ABI63'):
            stage.validate_union_metadata(self.manifest, self.revision, 'linux-arm64', self.exports)

    def test_style_only_abi63_is_ineligible(self):
        with self.assertRaisesRegex(ValueError, 'union exports'):
            stage.validate_union_metadata(self.manifest, self.revision, 'linux-arm64', {'rv_ax_text_style_run'})

    def test_source_rid_dirty_and_empty_pin_are_ineligible(self):
        for key, value in [('rid', 'linux-x64'), ('source', dict(commit='2' * 40, dirty=False)),
                           ('source', dict(commit=self.revision, dirty=True))]:
            with self.subTest(key=key, value=value):
                candidate = dict(self.manifest, **{key: value})
                with self.assertRaises(ValueError):
                    stage.validate_union_metadata(candidate, self.revision, 'linux-arm64', self.exports)
        with self.assertRaises(ValueError):
            stage.validate_union_metadata(self.manifest, '', 'linux-arm64', self.exports)

    def test_exact_manifest_and_union_exports_pass_metadata_gate_only(self):
        stage.validate_union_metadata(self.manifest, self.revision, 'linux-arm64', self.exports)


if __name__ == '__main__':
    unittest.main()
