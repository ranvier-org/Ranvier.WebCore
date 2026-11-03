import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class ProducerSidecarAdmission(unittest.TestCase):
    def test_package_with_matching_manifest_and_changed_payload_is_rejected(self):
        spec = importlib.util.spec_from_file_location('producer_sidecars', ROOT / 'tests/controls/build_cocoa_sidecars.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = root / 'native'
            original.write_bytes(b'original')
            manifest = dict(files=[dict(name='library', sha256=module.sha(original))])
            package = root / 'fixture.nupkg'
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('runtimes/osx-arm64/native/library', b'changed')
            self.assertFalse(module.package_matches(package, manifest))
            with zipfile.ZipFile(package, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
                archive.writestr('runtimes/osx-arm64/native/library', b'original')
            self.assertTrue(module.package_matches(package, manifest))
            with warnings.catch_warnings(), zipfile.ZipFile(package, 'a') as archive:
                warnings.simplefilter('ignore', UserWarning)
                archive.writestr('runtimes/osx-arm64/native/library', b'original')
            self.assertFalse(module.package_matches(package, manifest))

    def test_complete_staged_payload_is_required_before_helper_compilation(self):
        path = ROOT / 'tests/controls/build_cocoa_sidecars.py'
        self.assertTrue(path.is_file(), 'The producer must capture its matching helper closure')
        spec = importlib.util.spec_from_file_location('producer_sidecars', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory)
            native = stage / 'runtimes/osx-arm64/native'
            native.mkdir(parents=True)
            files = []
            for name in ['libRanvierWebCoreHost.dylib', 'libWebCore.dylib', 'libJavaScriptCore.dylib', 'libWebGPU.dylib']:
                path = native / name
                path.write_bytes(b'metadata fixture, never loaded')
                files.append(dict(name=name, sha256=module.sha(path)))
            manifest = dict(rid='osx-arm64', flavor='slim', abi=64,
                            source=dict(commit='a' * 40, dirty=False), files=files)
            (stage / 'manifest.json').write_text(json.dumps(manifest))
            _, selected, hashes = module.admit_stage(stage)
            self.assertEqual(selected, native.resolve())
            self.assertEqual(len(hashes), 4)
            (native / 'unrecorded.resource').write_bytes(b'extra')
            with self.assertRaisesRegex(ValueError, 'payload'):
                module.admit_stage(stage)
            (native / 'unrecorded.resource').unlink()
            (native / files[0]['name']).write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'payload'):
                module.admit_stage(stage)


if __name__ == '__main__':
    unittest.main()
