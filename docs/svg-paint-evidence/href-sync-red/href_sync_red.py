import ctypes, json, sys
sys.path.insert(0, 'tests/abi'); sys.path.insert(0, 'artifacts')
from svg_paint_probe import SvgProbe
from diagnose_href_enumeration import named
cases = {'href': 'href', 'xlink': 'xmlns:xlink="http://www.w3.org/1999/xlink" xlink:href'}
out = {}
for case, attribute in cases.items():
    markup = f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="f"><feImage id="image" {attribute}="data:,a"/></filter></defs></svg>'''
    with SvgProbe(sys.argv[1], 100, 100) as p:
        p.load(markup)
        image = p.node('image')
        href = p.object('rv_dom_svgfe_image_element_get_href', [p.pointer], [image], 'svg_animated_string')
        p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, ctypes.c_char_p], href, b'data:,b')
        out[case] = [(name, namespace, p.text('rv_dom_element_get_attribute_ns', [p.pointer, ctypes.c_char_p, ctypes.c_char_p], image, namespace.encode() if namespace else None, b'href')) for name, namespace in named(p, image)]
print(json.dumps(out))
