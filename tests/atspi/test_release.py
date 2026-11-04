"""Release packing of the public two-RID AT-SPI provider; fixtures are ELF headers, never loaded."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('atspi_release', Path(__file__).parents[2] / 'providers/atspi/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
VERSION = '0.1.1-rc.1'


def module(machine, salt):
    data = bytearray(64)
    data[:6] = b'\x7fELF\x02\x01'
    data[18:20] = machine.to_bytes(2, 'little')
    data[40] = salt
    return bytes(data)


def write_build(root, rid, machine, abi=64, overrides=None):
    directory = root / rid
    directory.mkdir()
    provider = module(machine, len(rid))
    (directory / 'libRanvierWebCoreAtspi.so').write_bytes(provider)
    receipt = dict(rid=rid, version=VERSION, abi=abi, providerSha256=hashlib.sha256(provider).hexdigest(),
                   hostSha256='a' * 64, protocolPassed=True, consumerPassed=True, directStylePassed=True)
    receipt.update(overrides or {})
    (directory / 'build-receipt.json').write_text(json.dumps(receipt))
    return directory


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)

    def test_payload_carries_both_runtimes_and_a_consumer_readable_manifest(self):
        builds = {rid: release.read_build(write_build(self.root, rid, machine), rid, VERSION)
                  for rid, machine in release.RIDS.items()}
        payload, manifest = release.payload_for(builds, VERSION, 64)
        for rid in release.RIDS:
            self.assertIn(f'runtimes/{rid}/native/libRanvierWebCoreAtspi.so', payload)
            self.assertEqual(manifest['runtimes'][rid]['abi'], 64)
        for name in ['include/RanvierAtspi.h', 'include/RanvierWebCoreAbi.h', 'NOTICE.md', 'PUBLIC-README.md',
                     'THIRD-PARTY.md', 'licenses/LGPL-2.1.txt']:
            self.assertEqual(manifest['payloads'][name], hashlib.sha256(payload[name]).hexdigest())
        self.assertEqual(json.loads(payload['provider-manifest.json']), manifest)
        consumer = importlib.util.spec_from_file_location('consumer', Path(__file__).with_name('consumer.py'))
        checker = importlib.util.module_from_spec(consumer)
        consumer.loader.exec_module(checker)
        for rid in release.RIDS:
            self.assertEqual(checker.select_runtime(manifest, rid)['rid'], rid)

    def test_wrong_architecture_is_rejected(self):
        directory = write_build(self.root, 'linux-arm64', release.RIDS['linux-x64'])
        with self.assertRaises(ValueError):
            release.read_build(directory, 'linux-arm64', VERSION)

    def test_receipt_must_describe_the_provider_and_its_passed_checks(self):
        for key, bad in [('version', '0.1.1-rc.2'), ('rid', 'linux-arm64'), ('providerSha256', '0' * 64),
                         ('abi', '64'), ('protocolPassed', False), ('consumerPassed', False), ('directStylePassed', False)]:
            with self.subTest(key=key):
                root = self.root / key
                root.mkdir()
                directory = write_build(root, 'linux-x64', release.RIDS['linux-x64'], overrides={key: bad})
                with self.assertRaises(ValueError):
                    release.read_build(directory, 'linux-x64', VERSION)

    def test_release_workflow_packs_the_provider_for_every_tag(self):
        workflow = (Path(__file__).parents[2] / '.github/workflows/build.yml').read_text()
        job = workflow.split('\n  atspi-package:\n', 1)[1].split('\n  publish:\n', 1)[0]
        self.assertIn('providers/atspi/release.py', job)
        self.assertIn('name: package-atspi', job)
        build = workflow.split('
  atspi:
', 1)[1].split('
  atspi-package:
', 1)[0]
        # tests/atspi/run.py starts /usr/libexec/at-spi2-registryd, which at-spi2-core installs.
        self.assertIn('at-spi2-core', build)
        self.assertIn('fail-fast: false', build)
        publish = workflow.split('\n  publish:\n', 1)[1]
        self.assertIn('atspi-package', publish.split('needs:', 1)[1].split('\n', 1)[0])


if __name__ == '__main__':
    unittest.main()
