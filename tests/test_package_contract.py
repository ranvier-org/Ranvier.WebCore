import pathlib
import hashlib
import importlib.util
import json
import struct
import tempfile
import types
import unittest
import xml.etree.ElementTree as ET
import zipfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
RIDS = {'win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64'}
SPEC = importlib.util.spec_from_file_location('package_managed', ROOT / 'scripts/package_managed.py')
PACKAGING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGING)
SMOKE_SPEC = importlib.util.spec_from_file_location('smoke', ROOT / 'scripts/smoke.py')
SMOKE = importlib.util.module_from_spec(SMOKE_SPEC)
SMOKE_SPEC.loader.exec_module(SMOKE)


def synthetic_elf_so(needed=(), exports=()):
    dynstr = bytearray(b'\x00')
    dyn_entries = bytearray()
    for name in needed:
        off = len(dynstr)
        dynstr += name.encode('utf-8') + b'\x00'
        dyn_entries += struct.pack('<qQ', 1, off)
    dyn_entries += struct.pack('<qQ', 0, 0)

    symstr = bytearray(b'\x00')
    dynsym = bytearray(struct.pack('<IBBHQQ', 0, 0, 0, 0, 0, 0))
    for sym in exports:
        off = len(symstr)
        symstr += sym.encode('utf-8') + b'\x00'
        dynsym += struct.pack('<IBBHQQ', off, (1 << 4) | 2, 0, 1, 0x1000, 16)

    body = bytearray(64)
    def add_blob(blob):
        while len(body) % 8:
            body.append(0)
        start = len(body)
        body.extend(blob)
        return start, len(blob)

    dynstr_off, dynstr_sz = add_blob(dynstr)
    dyn_off, dyn_sz = add_blob(dyn_entries)
    symstr_off, symstr_sz = add_blob(symstr)
    sym_off, sym_sz = add_blob(dynsym)
    while len(body) % 8:
        body.append(0)
    shoff = len(body)
    sections = [
        struct.pack('<IIQQQQIIQQ', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, dynstr_off, dynstr_sz, 0, 0, 1, 0),
        struct.pack('<IIQQQQIIQQ', 0, 6, 0, 0, dyn_off, dyn_sz, 1, 0, 8, 16),
        struct.pack('<IIQQQQIIQQ', 0, 3, 0, 0, symstr_off, symstr_sz, 0, 0, 1, 0),
        struct.pack('<IIQQQQIIQQ', 0, 11, 0, 0, sym_off, sym_sz, 3, 1, 8, 24),
    ]
    body += b''.join(sections)
    ident = b'\x7fELF\x02\x01\x01' + b'\x00' * 9
    header = struct.pack('<16sHHIQQQIHHHHHH', ident, 3, 62, 1, 0, 0, shoff, 0, 64, 0, 0, 64, len(sections), 0)
    body[:64] = header
    return bytes(body)


class PackageContract(unittest.TestCase):
    def test_cpu_meta_depends_on_every_slim_runtime_at_one_version(self):
        project = ET.parse(ROOT / 'packaging/cpu/Ranvier.WebCore.Native.Cpu.Meta.csproj')
        references = project.findall('.//PackageReference')
        self.assertEqual({r.get('Include') for r in references},
                         {'Ranvier.WebCore.Native.Cpu.' + rid for rid in RIDS})
        self.assertEqual({r.get('Version') for r in references}, {'[$(Version)]'})
        self.assertEqual(project.findtext('.//PackageId'), 'Ranvier.WebCore.Native.Cpu')
        self.assertEqual(project.findtext('.//IncludeBuildOutput'), 'false')

    def test_default_meta_depends_on_the_gpu_runtimes_and_the_cpu_fallback_at_one_version(self):
        project = ET.parse(ROOT / 'packaging/Ranvier.WebCore.Native.Meta.csproj')
        self.assertEqual(project.findtext('.//EnableDefaultCompileItems'), 'false',
                         'the default aggregate sits above the .Cpu and .Gpu projects and must not glob their obj')
        references = project.findall('.//PackageReference')
        gpu = {'Ranvier.WebCore.Native.' + rid for rid in PACKAGING.GPU_RIDS}
        fallback = {'Ranvier.WebCore.Native.Cpu.' + rid for rid in RIDS - set(PACKAGING.GPU_RIDS)}
        self.assertEqual(fallback, {'Ranvier.WebCore.Native.Cpu.win-arm64'})
        self.assertEqual({r.get('Include') for r in references}, gpu | fallback)
        self.assertEqual({r.get('Version') for r in references}, {'[$(Version)]'})
        self.assertEqual(project.findtext('.//PackageId'), 'Ranvier.WebCore.Native')
        self.assertEqual(project.findtext('.//IncludeBuildOutput'), 'false')

    def test_gpu_alias_depends_only_on_the_default_aggregate(self):
        project = ET.parse(ROOT / 'packaging/gpu/Ranvier.WebCore.Native.Gpu.Meta.csproj')
        references = project.findall('.//PackageReference')
        self.assertEqual([(r.get('Include'), r.get('Version')) for r in references],
                         [('Ranvier.WebCore.Native', '[$(Version)]')])
        self.assertEqual(project.findtext('.//PackageId'), 'Ranvier.WebCore.Native.Gpu')
        self.assertEqual(project.findtext('.//IncludeBuildOutput'), 'false')

    def test_every_script_names_a_flavor_package_alike(self):
        names = repr(PACKAGING.FLAVOR_SUFFIX)
        self.assertEqual(PACKAGING.FLAVOR_SUFFIX, {'slim': '.Cpu', 'gpu': '', 'lean': '.Lean'})
        for path in ['scripts/build.py', 'scripts/release.py', '.github/workflows/build.yml']:
            with self.subTest(path=path):
                self.assertIn(names, (ROOT / path).read_text())

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
        self.assertEqual(native, [], 'managed interop must allow selecting the native flavor')
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
                path = packages / f'Ranvier.WebCore.Native.Cpu.{rid}.0.1.0-preview.6.nupkg'
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

    def test_linux_smoke_enforces_static_hidden_icu(self):
        args = types.SimpleNamespace(expect_flavor=None, expect_version=None, expect_commit=None, build_dir=None, no_load=True)
        with tempfile.TemporaryDirectory() as temporary:
            stage = pathlib.Path(temporary)
            native = stage / 'runtimes/linux-x64/native'
            native.mkdir(parents=True)
            host = native / 'libRanvierWebCoreHost.so'

            def write_stage(needed, exports):
                payload = synthetic_elf_so(needed=needed, exports=exports)
                host.write_bytes(payload)
                manifest = dict(
                    rid='linux-x64', flavor='slim', version='0.1.1-rc.9', webkit='pinned', abi=64,
                    source=dict(commit='a' * 40, dirty=False, builder='ci'),
                    total_bytes=len(payload),
                    files=[dict(name='libRanvierWebCoreHost.so', bytes=len(payload), sha256=hashlib.sha256(payload).hexdigest())],
                )
                (stage / 'manifest.json').write_text(json.dumps(manifest))

            write_stage(['libharfbuzz.so.0', 'libglib-2.0.so.0', 'libc.so.6'], ['rv_abi_version', 'rv_host_create'])
            SMOKE.check(stage, args)

            for bad_needed in ('libicuuc.so.74', 'libicui18n.so.74', 'libicudata.so.74', 'libharfbuzz-icu.so.0'):
                with self.subTest(needed=bad_needed):
                    write_stage(['libharfbuzz.so.0', bad_needed], ['rv_abi_version'])
                    with self.assertRaises(SystemExit) as cm:
                        SMOKE.check(stage, args)
                    self.assertIn(bad_needed, str(cm.exception))

            for leaked in ('hb_icu_script_to_script', 'icudt77_dat'):
                with self.subTest(leaked=leaked):
                    write_stage(['libharfbuzz.so.0'], ['rv_abi_version', leaked])
                    with self.assertRaises(SystemExit) as cm:
                        SMOKE.check(stage, args)
                    self.assertIn(leaked, str(cm.exception))

    def test_linux_workflows_and_package_list_require_no_distro_icu(self):
        packages = [line.strip() for line in (ROOT / 'scripts/linux-packages.txt').read_text().splitlines()
                    if line.strip() and not line.lstrip().startswith('#')]
        self.assertNotIn('libicu-dev', packages)
        for rel in ('.github/workflows/build.yml', '.github/workflows/atspi-provider.yml'):
            with self.subTest(workflow=rel):
                text = (ROOT / rel).read_text()
                self.assertNotIn('libicu74', text)
                self.assertNotIn('libharfbuzz-icu0', text)


if __name__ == '__main__':
    unittest.main()
