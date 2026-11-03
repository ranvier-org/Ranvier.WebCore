import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).parent / 'controls/cocoa_progress_paths.py'
spec = importlib.util.spec_from_file_location('progress_paths', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def frame(alpha, end=259):
    pixels = bytearray(bytes([255, 255, 255, 255]) * 300 * 70)
    track, full = (230, 230, 230), (0, 122, 255)
    for y in range(26, 34):
        for x in range(21, 259):
            value = [round((1 - alpha) * base + alpha * target) for base, target in zip(track, full)] if x < end else track
            index = (y * 300 + x) * 4
            pixels[index:index + 4] = bytes([*value, 255])
    return bytes(pixels)


class ReducedVectorCapture(unittest.TestCase):
    def verdict(self, samples):
        checks, _ = module.vector_reduced_contract(samples, frame(0), frame(1))
        return all(value for value, _ in checks)

    def test_full_width_source_opacity_pulse(self):
        self.assertTrue(self.verdict([frame(.35), frame(.4), frame(.45)]))

    def test_full_opacity_is_not_a_reduced_pulse(self):
        self.assertFalse(self.verdict([frame(1), frame(.95), frame(.9)]))

    def test_static_fill_is_not_the_existing_pulse(self):
        self.assertFalse(self.verdict([frame(.4)] * 3))

    def test_missing_right_side_is_rejected(self):
        self.assertFalse(self.verdict([frame(.35, 150), frame(.4, 150), frame(.45, 150)]))


if __name__ == '__main__':
    unittest.main()
