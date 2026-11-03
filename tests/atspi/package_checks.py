"""Use real ELF and ABI controls for optional provider packaging."""
import argparse
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', required=True, type=Path)
    parser.add_argument('--uninstalled-provider', required=True, type=Path)
    parser.add_argument('--native', required=True, type=Path)
    parser.add_argument('--previous-native', required=True, type=Path)
    parser.add_argument('--report', required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    args = parser.parse_args()
    source = Path(__file__).resolve().parents[2] / 'providers/atspi/package.py'
    spec = importlib.util.spec_from_file_location('atspi_package', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    rows = []
    def rejected(name, action, kind=ValueError):
        try:
            action()
        except kind as error:
            rows.append(dict(name=name, passed=True, reason=str(error)))
        else:
            rows.append(dict(name=name, passed=False))
    assert module.validate_runtime(args.provider, args.native, 'linux-x64') == 63
    rows.append(dict(name='installed actual ABI63 style module accepted', passed=True))
    rejected('wrong architecture', lambda: module.validate_runtime(args.provider, args.native, 'linux-arm64'))
    rejected('old ABI62 host', lambda: module.validate_runtime(args.provider, args.previous_native, 'linux-x64'))
    rejected('uninstalled absolute build rpath', lambda: module.validate_runtime(args.uninstalled_provider, args.native, 'linux-x64'))
    with tempfile.TemporaryDirectory(prefix='ranvier-atspi-package-') as temporary:
        output = Path(temporary)
        rejected('package path injection', lambda: module.pack(args.provider, args.native, 'linux-x64', '../escape', '0.0.0-privatecontrol', output, args.source_revision))
        destination, manifest = module.pack(args.provider, args.native, 'linux-x64', 'Ranvier.Private.Atspi.Control', '0.0.0-privatecontrol', output, args.source_revision, cohort_label='private-da11-abi347')
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
            assert names.count('runtimes/linux-x64/native/libRanvierWebCoreAtspi.so') == 1
            assert not any('libRanvierWebCoreHost.so' in name or name.endswith('.dll') for name in names)
            assert json.loads(archive.read('provider-manifest.json')) == manifest
            assert manifest['callerClaimedProviderSourceRevision'] == args.source_revision
            assert manifest['sourceProvenance'] == 'unverified-caller-claim'
            assert manifest['qualificationScope'] == 'private-ABI63-provider-only'
            assert manifest['callerClaimedCohortLabel'] == 'private-da11-abi347'
            assert manifest['cohortLabelProvenance'] == 'unverified-caller-claim'
            assert 'providerSourceRevision' not in manifest
            assert 'original-project-license-unspecified' in manifest['licenseMetadataStatus']
            assert 'Embedded protocol declarations' in archive.read('THIRD-PARTY.md').decode()
            assert 'GNU LESSER GENERAL PUBLIC LICENSE' in archive.read('licenses/LGPL-2.1.txt').decode()
            license_metadata = ET.fromstring(archive.read('Ranvier.Private.Atspi.Control.nuspec')).find('metadata/license')
            assert license_metadata.attrib == {'type': 'file'} and license_metadata.text == 'NOTICE.md'
        rows.append(dict(name='only provider native asset and exact manifest bundled', passed=True))
        before = module.sha(destination)
        rejected('existing artifact is not overwritten', lambda: module.pack(args.provider, args.native, 'linux-x64', 'Ranvier.Private.Atspi.Control', '0.0.0-privatecontrol', output, args.source_revision), FileExistsError)
        assert before == module.sha(destination)
        rejected('final cohort label cannot imply acceptance', lambda: module.pack(args.provider, args.native, 'linux-x64', 'Ranvier.Private.Atspi.Control', '0.0.0-privatefinal', output, args.source_revision, cohort_label='final-abi347'))
    args.report.write_text(json.dumps(rows, indent=2))
    print(json.dumps(dict(checks=len(rows), failures=[row for row in rows if not row['passed']])))
    return int(any(not row['passed'] for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
