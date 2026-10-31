import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe


def verify(native_directory):
    with SvgProbe(native_directory) as p:
        p.load((Path(__file__).resolve().parents[1] / 'fixtures/svg-filters.svg').read_bytes())
        filter_node = p.node('filter')
        units = p.property('svg_filter_element', filter_node, 'filter_units', 'svg_animated_enumeration')
        p.expect(p.read('svg_animated_enumeration', units, 'base_val', p.short) == 1, 'real filter units producer')
        blur = p.node('blur')
        before = p.pixel(p.paint(), 15, 30)
        p.expect(before == [255, 255, 255, 255], 'unblurred source leaves exterior white')
        p.call('rv_dom_svgfe_gaussian_blur_element_set_std_deviation', [p.pointer, p.single, p.single], blur, 5, 0)
        after = p.pixel(p.paint(), 15, 30)
        p.expect(after[0] == 255 and after[1] < 250 and after[2] < 250, 'typed blur parameters change actual rendered paint')
        print(f'PASS SVG filters: {p.assertions} assertions', flush=True)
        return p.assertions


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
