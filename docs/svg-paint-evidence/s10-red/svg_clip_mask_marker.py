import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe


def verify(native_directory):
    with SvgProbe(native_directory,400,300) as p:
        p.load((Path(__file__).resolve().parents[1]/'fixtures/svg-clip-mask-marker.svg').read_bytes())
        clip=p.node('clip')
        units=p.property('svg_clip_path_element',clip,'clip_path_units','svg_animated_enumeration')
        p.expect(p.read('svg_animated_enumeration',units,'base_val',p.short)==1,'actual clipPath unit producer')
        before=p.paint()
        p.expect(p.pixel(before,25,25)==[255,0,0,255] and p.pixel(before,75,25)==[255,255,255,255],'actual initial clipping')
        geometry=p.node('clipGeometry')
        _,width=p.length('svg_rect_element',geometry,'width')
        p.set_length(width,80)
        p.expect(p.pixel(p.paint(),75,25)==[255,0,0,255],'typed clip geometry changes actual paint')
        print(f'PASS SVG clip/mask/marker: {p.assertions} assertions',flush=True)
        return p.assertions


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--native-directory',required=True)
    verify(parser.parse_args().native_directory)
