import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeMediaTests(unittest.TestCase):
    def test_original_fixture_matches_committed_identity(self):
        fixture = ROOT/'tests/fixtures/native-media-colors-tone.mp4'
        manifest = json.loads(fixture.with_suffix('.json').read_text())
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).hexdigest(),manifest['sha256'])
        self.assertEqual(fixture.stat().st_size,manifest['bytes'])
        self.assertEqual((manifest['video']['frames'],manifest['video']['frameRate'],manifest['durationSeconds']),(60,30,2))

    def test_optional_os_consumer_is_routed_only_to_windows_gpu(self):
        spec = importlib.util.spec_from_file_location('media_probes',ROOT/'scripts/probes.py')
        probes = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(probes)
        rows = [row for row in probes.PROBES if any('tests/media/windows.py' in command for command in row['commands'])]
        self.assertEqual(len(rows),1)
        self.assertTrue(probes.applies(rows[0],'win-x64','gpu'))
        self.assertFalse(probes.applies(rows[0],'win-x64','slim'))
        self.assertFalse(probes.applies(rows[0],'linux-x64','gpu'))


if __name__ == '__main__':
    unittest.main()
