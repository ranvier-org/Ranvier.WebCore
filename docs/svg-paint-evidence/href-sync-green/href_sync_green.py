import ctypes, json, sys
sys.path.insert(0, 'tests/abi'); sys.path.insert(0, 'artifacts')
from svg_paint_probe import SvgProbe
from diagnose_href_enumeration import named
cases = {'href': 'href="data:,a"', 'xlink': 'xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href="data:,a"',
         'both': 'xmlns:xlink="http://www.w3.org/1999/xlink" href="data:,a" xlink:href="data:,x"'}
out = {}
for case, attribute in cases.items():
    markup = f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="f"><feImage id="image" {attribute}/></filter></defs></svg>'''
    with SvgProbe(sys.argv[1], 100, 100) as p:
        p.load(markup)
        image = p.node('image')
        href = p.object('rv_dom_svgfe_image_element_get_href', [p.pointer], [image], 'svg_animated_string')
        p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, ctypes.c_char_p], href, b'data:,b')
        rows = named(p, image)
        out[case] = [[name, namespace] for name, namespace in rows if 'href' in name] + [
            ['plain', p.text('rv_dom_element_get_attribute_ns', [p.pointer, ctypes.c_char_p, ctypes.c_char_p], image, None, b'href')],
            ['xlink', p.text('rv_dom_element_get_attribute_ns', [p.pointer, ctypes.c_char_p, ctypes.c_char_p], image, b'http://www.w3.org/1999/xlink', b'href')]]
print(json.dumps(out))
