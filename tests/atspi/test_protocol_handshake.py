import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('atspi_protocol', Path(__file__).with_name('run.py'))
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)


class ProtocolHandshake(unittest.TestCase):
    def test_client_cannot_observe_a_partial_response(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            opened, proceed = threading.Event(), threading.Event()
            original = Path.write_text
            errors = []

            def paused_write(path, text, *args, **kwargs):
                original(path, '', *args, **kwargs)
                opened.set()
                if not proceed.wait(3):
                    raise TimeoutError('Test did not release the paused writer')
                return original(path, text, *args, **kwargs)

            def publish():
                try:
                    protocol.publish_response(root, {'action': 'release'})
                except BaseException as error:
                    errors.append(error)
                    opened.set()

            with patch.object(Path, 'write_text', paused_write):
                writer = threading.Thread(target=publish)
                writer.start()
                try:
                    self.assertTrue(opened.wait(3))
                    self.assertFalse((root / 'response.json').exists())
                finally:
                    proceed.set()
                    writer.join(3)
            self.assertFalse(writer.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(json.loads((root / 'response.json').read_text()), {'action': 'release'})
            self.assertFalse((root / 'response.tmp').exists())


if __name__ == '__main__':
    unittest.main()
