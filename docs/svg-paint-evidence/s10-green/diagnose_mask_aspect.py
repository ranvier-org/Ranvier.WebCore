import ctypes
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests/abi'))
from svg_paint_probe import SvgProbe
repo=Path(__file__).resolve().parents[1]
with SvgProbe(repo/'artifacts/svg-paint-candidate/runtime',400,300) as p:
 p.load((repo/'tests/fixtures/svg-clip-mask-marker.svg').read_bytes())
 mask,geometry,marker=(p.node(n) for n in ['mask','maskGeometry','marker'])
 def report(label):
  pixels=p.paint()
  print(label,{'mask':p.pixel(pixels,175,25),'marker':{str((x,y)):p.pixel(pixels,x,y) for x,y in [(222,202),(225,202),(222,207),(225,207),(225,195),(230,200)]}},flush=True)
 report('initial')
 p.call('rv_dom_element_set_attribute',[p.pointer,ctypes.c_char_p,ctypes.c_char_p],geometry,b'fill',b'black');report('black')
 style=p.property('svg_element',mask,'style','css_style_declaration')
 p.call('rv_dom_css_style_declaration_set_property',[p.pointer,ctypes.c_char_p,ctypes.c_char_p,ctypes.c_char_p],style,b'mask-type',b'alpha',b'');report('alpha')
 print('style',p.text('rv_dom_css_style_declaration_get_property_value',[p.pointer,ctypes.c_char_p],style,b'mask-type'))
 p.call('rv_dom_element_set_attribute',[p.pointer,ctypes.c_char_p,ctypes.c_char_p],geometry,b'x',b'151');report('alphaRepaint')
 box=p.property('svg_marker_element',marker,'view_box','svg_animated_rect');base=p.property('svg_animated_rect',box,'base_val','svg_rect')
 p.call('rv_dom_svg_rect_set_width',[p.pointer,p.single],base,20);report('none')
 aspect=p.property('svg_marker_element',marker,'preserve_aspect_ratio','svg_animated_preserve_aspect_ratio');base=p.property('svg_animated_preserve_aspect_ratio',aspect,'base_val','svg_preserve_aspect_ratio')
 p.call('rv_dom_svg_preserve_aspect_ratio_set_align',[p.pointer,p.short],base,6);report('meet')
