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

    def test_gpu_meta_depends_on_the_gpu_runtimes_and_the_slim_fallback_at_one_version(self):
        project = ET.parse(ROOT / 'packaging/gpu/Ranvier.WebCore.Native.Gpu.Meta.csproj')
        references = project.findall('.//PackageReference')
        gpu = {'Ranvier.WebCore.Native.Gpu.' + rid for rid in PACKAGING.GPU_RIDS}
        fallback = {'Ranvier.WebCore.Native.' + rid for rid in RIDS - set(PACKAGING.GPU_RIDS)}
        self.assertEqual(fallback, {'Ranvier.WebCore.Native.win-arm64'})
        self.assertEqual({r.get('Include') for r in references}, gpu | fallback)
        self.assertEqual({r.get('Version') for r in references}, {'[$(Version)]'})
        self.assertEqual(project.findtext('.//PackageId'), 'Ranvier.WebCore.Native.Gpu')
        self.assertEqual(project.findtext('.//IncludeBuildOutput'), 'false')

    def test_gpu_aggregate_needs_every_gpu_runtime_from_the_slim_identity(self):
        version, identity = '0.1.0-preview.6', (21, 'pinned', 'same')

        def write(packages, package_flavor, rid, **change):
            manifest = dict(rid=rid, version=version, flavor=package_flavor, abi=21, webkit='pinned',
                            source=dict(commit='same', dirty=False))
            manifest.update(change)
            with zipfile.ZipFile(PACKAGING.runtime_package(packages, package_flavor, rid, version), 'w') as archive:
                archive.writestr('manifest.json', json.dumps(manifest))

        with tempfile.TemporaryDirectory() as temporary:
            packages = pathlib.Path(temporary)
            for rid in RIDS:
                write(packages, 'slim', rid)
            self.assertFalse(PACKAGING.has_gpu_runtimes(packages, version, identity))
            write(packages, 'gpu', 'win-x64')
            with self.assertRaisesRegex(ValueError, 'missing'):
                PACKAGING.has_gpu_runtimes(packages, version, identity)
            for rid in PACKAGING.GPU_RIDS:
                write(packages, 'gpu', rid)
            self.assertTrue(PACKAGING.has_gpu_runtimes(packages, version, identity))
            write(packages, 'gpu', 'osx-arm64', abi=22)
            with self.assertRaisesRegex(ValueError, 'one ABI'):
                PACKAGING.has_gpu_runtimes(packages, version, identity)
            write(packages, 'gpu', 'osx-arm64', flavor='slim')
            with self.assertRaisesRegex(ValueError, 'flavor differs'):
                PACKAGING.has_gpu_runtimes(packages, version, identity)

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
