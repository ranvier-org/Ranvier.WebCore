"""Pack an already qualified optional provider; never build or publish a renderer."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_distribution(rid, source_revision, test_only_arm64=False):
    if test_only_arm64 and rid != 'linux-arm64':
        raise ValueError('The test-only override is restricted to ARM64 qualification artifacts.')
    if rid != 'linux-x64' and not (rid == 'linux-arm64' and test_only_arm64):
        raise ValueError('Only linux-x64 has a qualified real renderer/provider cohort; ARM64 remains preparatory.')
    if not re.fullmatch(r'[0-9a-f]{40}', source_revision):
        raise ValueError('The provider source revision must be a full lowercase Git commit.')


def validate_identity(package_id, version):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', package_id) or not re.fullmatch(r'[A-Za-z0-9_.+-]+', version):
        raise ValueError('Invalid package identity.')
    if not package_id.startswith('Ranvier.Private.') or not re.fullmatch(r'0\.0\.0-(?:private[A-Za-z0-9.-]+|ci\.[0-9]+)', version):
        raise ValueError('This packager permits private qualification identities only; the final public cohort/version remain unallocated.')


def validate_cohort_label(cohort_label):
    if not re.fullmatch(r'private-[a-z0-9]+(?:-[a-z0-9]+)*', cohort_label):
        raise ValueError('The caller cohort label must be a private-* lowercase token; it does not establish qualification.')


def validate_runtime(provider, native, rid):
    machine = {'linux-x64': 62, 'linux-arm64': 183}[rid]
    for path in [provider, native]:
        data = path.read_bytes()
        if data[:6] != b'\x7fELF\x02\x01' or int.from_bytes(data[18:20], 'little') != machine:
            raise ValueError('The ELF architecture does not match ' + rid)
    dynamic = subprocess.check_output(['readelf', '-d', str(provider)], text=True)
    runpath = re.findall(r'\((?:RUNPATH|RPATH)\).*?\[(.*?)\]', dynamic)
    if runpath != ['$ORIGIN']:
        raise ValueError('Package the installed provider with only its sibling runtime search path.')
    if 'libatspi' in dynamic:
        raise ValueError('The independent AT-SPI client must not become a provider runtime dependency.')
    host = ctypes.CDLL(str(native.resolve()))
    host.rv_abi_version.restype = ctypes.c_int32
    host.rv_abi_has.argtypes = [ctypes.c_char_p]
    host.rv_abi_has.restype = ctypes.c_int32
    abi = host.rv_abi_version()
    if abi != 63 or host.rv_abi_has(b'accessibility-text-style') != 1:
        raise ValueError('The provider requires the matching ABI63 style-run host.')
    return abi


def pack(provider, native, rid, package_id, version, output, source_revision, test_only_arm64=False, cohort_label='private-unspecified'):
    validate_distribution(rid, source_revision, test_only_arm64)
    validate_identity(package_id, version)
    validate_cohort_label(cohort_label)
    abi = validate_runtime(provider, native, rid)
    root = Path(__file__).resolve().parent
    metadata = ET.Element('package')
    fields = ET.SubElement(metadata, 'metadata')
    for name, value in [('id', package_id), ('version', version), ('authors', 'Ranvier'),
                        ('description', 'Optional native AT-SPI accessibility provider; requires an application-selected matching WebCore host.'),
                        ('readme', 'README.md')]:
        ET.SubElement(fields, name).text = value
    ET.SubElement(fields, 'license', type='file').text = 'NOTICE.md'
    payload = {
        'runtimes/' + rid + '/native/libRanvierWebCoreAtspi.so': provider.read_bytes(),
        'include/RanvierAtspi.h': (root / 'RanvierAtspi.h').read_text(encoding='utf-8').encode('utf-8'),
        'include/RanvierWebCoreAbi.h': (root.parents[1] / 'host/RanvierWebCoreAbi.h').read_text(encoding='utf-8').encode('utf-8'),
        'README.md': (root / 'README.md').read_text(encoding='utf-8').encode('utf-8'),
        'NOTICE.md': (root / 'NOTICE.md').read_text(encoding='utf-8').encode('utf-8'),
        'THIRD-PARTY.md': (root / 'THIRD-PARTY.md').read_text(encoding='utf-8').encode('utf-8'),
        'licenses/LGPL-2.1.txt': (root / 'licenses/LGPL-2.1.txt').read_text(encoding='utf-8').encode('utf-8'),
    }
    manifest = dict(id=package_id, version=version, rid=rid, abi=abi,
        callerClaimedProviderSourceRevision=source_revision, sourceProvenance='unverified-caller-claim',
        qualificationScope='ARM64-test-only-unqualified' if test_only_arm64 else 'private-ABI63-provider-only',
        callerClaimedCohortLabel=cohort_label, cohortLabelProvenance='unverified-caller-claim',
        licenseMetadataStatus='original-project-license-unspecified; embedded-XML-license-not-marked',
        hostSha256=sha(native), providerSha256=sha(provider),
        requiredCapability='accessibility-text-style', hostBundled=False,
        dependencies='System GIO/GObject/GLib; no renderer package is selected by this optional provider.',
        payloads={name: hashlib.sha256(data).hexdigest() for name, data in payload.items()})
    payload['provider-manifest.json'] = json.dumps(manifest, indent=2).encode()
    output.mkdir(parents=True, exist_ok=True)
    destination = output / (package_id + '.' + version + '.nupkg')
    if destination.exists():
        raise FileExistsError(destination)
    with zipfile.ZipFile(destination, 'x', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(package_id + '.nuspec', ET.tostring(metadata, encoding='utf-8', xml_declaration=True))
        for name, data in payload.items():
            archive.writestr(name, data)
    return destination, manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--rid', choices=['linux-x64', 'linux-arm64'], required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-revision', required=True, help='Caller-claimed provider commit; syntax checked, provenance unverified.')
    parser.add_argument('--cohort-label', default='private-unspecified', help='Caller-claimed private-* cohort token; establishes no runtime qualification or provenance.')
    parser.add_argument('--test-only-arm64', action='store_true', help='Build a private ARM64 test artifact; confers no runtime qualification or distribution support.')
    args = parser.parse_args()
    destination, manifest = pack(args.provider, args.native, args.rid, args.id, args.version, args.output, args.source_revision, args.test_only_arm64, args.cohort_label)
    print(json.dumps(dict(path=str(destination), sha256=sha(destination), manifest=manifest)))
