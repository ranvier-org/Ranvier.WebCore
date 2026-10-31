import pathlib
import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
RIDS = {'win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64'}
SPEC = importlib.util.spec_from_file_location('package_managed', ROOT / 'scripts/package_managed.py')
PACKAGING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGING)


class PackageContract(unittest.TestCase):
    def test_meta_depends_on_every_runtime_at_one_version(self):
        project = ET.parse(ROOT / 'packaging/Ranvier.WebCore.Native.Meta.csproj')
        references = project.findall('.//PackageReference')
        self.assertEqual({r.get('Include') for r in references},
                         {'Ranvier.WebCore.Native.' + rid for rid in RIDS})
        self.assertEqual({r.get('Version') for r in references}, {'[$(Version)]'})
        self.assertEqual(project.findtext('.//PackageId'), 'Ranvier.WebCore.Native')
        self.assertEqual(project.findtext('.//IncludeBuildOutput'), 'false')

    def test_managed_package_compiles_the_canonical_interop(self):
        path = ROOT / 'src/Ranvier.WebCore/Ranvier.WebCore.fsproj'
        project = ET.parse(path)
        sources = {(path.parent / item.get('Include')).resolve()
                   for item in project.findall('.//Compile')}
        self.assertEqual(sources, {(ROOT / 'tests/abi/Native.fs').resolve(),
                                   (ROOT / 'tests/abi/NativeDom.fs').resolve(),
                                   (ROOT / 'tests/abi/Traversal.fs').resolve()})
        references = project.findall('.//PackageReference')
        native = [r for r in references if r.get('Include') == 'Ranvier.WebCore.Native']
        self.assertEqual(native, [], 'managed interop must allow selecting the GPU native flavor')
        self.assertFalse(any('Fable' in r.get('Include', '') or 'Xantham' in r.get('Include', '')
                             for r in references))
        self.assertEqual(project.findtext('.//IsAotCompatible'), 'true')

    def test_transitive_resources_are_selected_by_runtime(self):
        project = ET.parse(ROOT / 'packaging/buildTransitive.targets')
        groups = [group for group in project.findall('ItemGroup') if group.find('None') is not None]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].get('Condition'), "'$(RuntimeIdentifier)' == '@RID@'")

    def test_aggregate_rejects_incomplete_or_mixed_native_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            packages = pathlib.Path(temporary)
            with self.assertRaises(FileNotFoundError):
                PACKAGING.validate_runtimes(packages, '0.1.0-preview.6', (21, 'pinned', 'same'))
            for rid in RIDS:
                path = packages / f'Ranvier.WebCore.Native.{rid}.0.1.0-preview.6.nupkg'
                manifest = dict(rid=rid, version='0.1.0-preview.6', flavor='slim', abi=21,
                                webkit='pinned', source=dict(commit='same', dirty=False))
                with zipfile.ZipFile(path, 'w') as archive:
                    archive.writestr('manifest.json', json.dumps(manifest))
            self.assertEqual(PACKAGING.validate_runtimes(packages, '0.1.0-preview.6', (21, 'pinned', 'same')), 21)
            with self.assertRaisesRegex(ValueError, 'checkout identity'):
                PACKAGING.validate_runtimes(packages, '0.1.0-preview.6', (22, 'pinned', 'same'))
            with self.assertRaisesRegex(ValueError, 'checkout identity'):
                PACKAGING.validate_runtimes(packages, '0.1.0-preview.6', (21, 'pinned', 'new-checkout'))
            manifest['source']['commit'] = 'different'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'one ABI'):
                PACKAGING.validate_runtimes(packages, '0.1.0-preview.6', (21, 'pinned', 'same'))


if __name__ == '__main__':
    unittest.main()
