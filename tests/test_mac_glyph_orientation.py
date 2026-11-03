import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).parent / 'gpu/mac/glyph_orientation.py'
spec = importlib.util.spec_from_file_location('glyph_orientation', path)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class GlyphOrientation(unittest.TestCase):
    def image(self, reflected=False):
        width, height = 10, 12
        points = {(x, y) for x in range(2, 8) for y in range(2, 4)}
        points |= {(x, y) for x in range(2, 6) for y in range(5, 7)}
        points |= {(x, y) for x in range(2, 4) for y in range(2, 10)}
        if reflected:
            points = {(x, height - 1 - y) for x, y in points}
        return width, height, [(0, 0, 0) if (x, y) in points else (255, 255, 255)
                               for y in range(height) for x in range(width)]

    def test_upright_shape_has_exact_reference_overlap(self):
        result = probe.compare(self.image(), self.image(), (0, 0, 10, 12), True)
        self.assertEqual(result['uprightMaskIoU'], 1)
        self.assertFalse(result['closerToVerticalReflection'])
        self.assertTrue(result['cpuF']['topHeavyF'])

    def test_vertical_flip_rejected_even_with_same_ink_count(self):
        result = probe.compare(self.image(), self.image(True), (0, 0, 10, 12), True)
        self.assertEqual(result['cpuInk'], result['gpuInk'])
        self.assertEqual(result['verticalReflectionMaskIoU'], 1)
        self.assertTrue(result['closerToVerticalReflection'])
        self.assertFalse(result['gpuF']['topHeavyF'])

    def test_no_text_does_not_pass(self):
        with self.assertRaisesRegex(ValueError, 'Missing dark glyph'):
            probe.compare(self.image(), (10, 12, [(255, 255, 255)] * 120), (0, 0, 10, 12))


if __name__ == '__main__':
    unittest.main()
