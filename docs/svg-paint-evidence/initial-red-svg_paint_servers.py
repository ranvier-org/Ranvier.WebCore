import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe


def verify(native_directory):
    with SvgProbe(native_directory) as p:
        p.load((Path(__file__).resolve().parents[1] / 'fixtures/svg-paint-servers.svg').read_bytes())
        linear = p.node('linear')
        _, x2 = p.length('svg_linear_gradient_element', linear, 'x2')
        p.expect(p.read('svg_length', x2, 'value') == 100, 'actual gradient coordinate producer')
        before = p.paint()
        p.expect(p.pixel(before, 25, 50)[0] > p.pixel(before, 25, 50)[2], 'initial real linear gradient paint')
        p.set_length(x2, 50)
        p.expect(p.attribute(linear, 'x2') == '50', 'gradient mutation reflects authored coordinate')
        after = p.paint()
        p.expect(p.pixel(after, 75, 50) == [0, 0, 255, 255], 'typed coordinate mutation changes actual gradient paint')
        print(f'PASS SVG paint servers: {p.assertions} assertions', flush=True)
        return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
