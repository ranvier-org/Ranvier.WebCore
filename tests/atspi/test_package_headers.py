"""Hermetic SDK header packaging controls; no native library is loaded."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('provider_header_package', ROOT / 'providers/atspi/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageHeaderTests(unittest.TestCase):
    def test_checkout_line_endings_do_not_change_sdk_header_or_its_manifest_hash(self):
        expected = b'#pragma once\n#include "RanvierWebCoreAbi.h"\n'
        results = []
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            source = repository / 'providers/atspi'
            source.mkdir(parents=True)
            (repository / 'host').mkdir()
            (repository / 'host/RanvierWebCoreAbi.h').write_bytes(b'#pragma once\n')
            for name in ['README.md', 'NOTICE.md', 'THIRD-PARTY.md', 'licenses/LGPL-2.1.txt']:
                destination = source / name
                destination.parent.mkdir(exist_ok=True)
                destination.write_bytes((ROOT / 'providers/atspi' / name).read_bytes())
            provider = repository / 'provider.so'
            native = repository / 'host.so'
            provider.write_bytes(b'unit fixture, never loaded')
            native.write_bytes(b'unit fixture, never loaded')
            for index, ending in enumerate([b'\n', b'\r\n']):
                (source / 'RanvierAtspi.h').write_bytes(expected.replace(b'\n', ending))
                with patch.object(package, '__file__', str(source / 'package.py')), patch.object(package, 'validate_runtime', return_value=63):
                    destination, manifest = package.pack(provider, native, 'linux-x64', 'Ranvier.Private.Atspi.HeaderControl', '0.0.0-privateheader.' + str(index), repository / 'output', 'a' * 40)
                with zipfile.ZipFile(destination) as archive:
                    data = archive.read('include/RanvierAtspi.h')
                self.assertEqual(data, expected)
                self.assertEqual(manifest['payloads']['include/RanvierAtspi.h'], hashlib.sha256(expected).hexdigest())
                results.append(data)
        self.assertEqual(results[0], results[1])


if __name__ == '__main__':
    unittest.main()
