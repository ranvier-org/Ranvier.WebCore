import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, 'tests/abi')
from svg_paint_probe import SvgProbe

markup = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><defs><filter id="f"><feImage id="image" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='4' height='4'/%3E"/></filter></defs><rect width="10" height="10" filter="url(#f)"/></svg>'''


class Strings(ctypes.Structure):
    _fields_ = [('present', ctypes.c_int32), ('count', ctypes.c_int32), ('items', ctypes.POINTER(ctypes.c_char_p))]


def raw(p, target):
    count = p.bind('rv_element_attribute_count', p.integer, [p.pointer])(target)
    return [p.text('rv_element_attribute_at', [p.pointer, p.integer, p.integer], target, i, 0) for i in range(count)]


def named(p, target):
    attributes = p.object('rv_dom_element_get_attributes', [p.pointer], [target], 'named_node_map')
    out = []
    for i in range(p.read('named_node_map', attributes, 'length', p.unsigned)):
        attr = p.object('rv_dom_named_node_map_item', [p.pointer, p.unsigned], [attributes, i], 'node')
        out.append((p.text('rv_dom_attr_get_name', [p.pointer], attr), p.text('rv_dom_attr_get_namespace_uri', [p.pointer], attr)))
    return out


def names(p, target):
    result = Strings()
    p.call('rv_dom_element_get_attribute_names', [p.pointer, ctypes.POINTER(Strings)], target, ctypes.byref(result))
    return [result.items[i].decode() for i in range(result.count)]


def main():
  rows = []
  for order in ['raw-first', 'names-first', 'named-first', 'after-paint-raw']:
      with SvgProbe(sys.argv[1], 100, 100) as p:
          p.load(markup)
          image = p.node('image')
          href = p.object('rv_dom_svgfe_image_element_get_href', [p.pointer], [image], 'svg_animated_string')
          p.call('rv_dom_svg_animated_string_set_base_val', [p.pointer, ctypes.c_char_p], href, b'data:,changed')
          row = {'order': order}
          if order == 'after-paint-raw':
              p.paint()
          sequence = {'raw-first': ['raw', 'names', 'named', 'raw'], 'names-first': ['names', 'raw', 'named', 'raw'],
                      'named-first': ['named', 'raw', 'names', 'raw'], 'after-paint-raw': ['raw', 'names', 'named', 'raw']}[order]
          for step, route in enumerate(sequence):
              row[f'{step}:{route}'] = {'raw': raw, 'names': names, 'named': named}[route](p, image)
          rows.append(row)
  print(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
