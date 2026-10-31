import ctypes, sys
from pathlib import Path
sys.path.insert(0, 'tests/abi')
from svg_paint_probe import SvgProbe

markup = Path('tests/fixtures/mathml-surface.html').read_bytes()
for variant in sys.argv[2:]:
    with SvgProbe(sys.argv[1], 320, 240) as p:
        p.load(markup, standalone=False)
        p.update()
        math, mi, inline, row = (p.node(name) for name in ['math', 'mi', 'inline', 'row'])
        if 'htmlfirst' in variant:
            math, mi, inline, row = (p.node(name) for name in ['html', 'html', 'inline', 'html'])
        if 'focus' in variant:
            p.call('rv_dom_math_ml_element_focus', [p.pointer, p.pointer], p.node('focusable'), None)
        if 'dataset' in variant:
            p.object('rv_dom_math_ml_element_get_dataset', [p.pointer], [math], 'dom_string_map')
        if 'stylemap' in variant:
            p.object('rv_dom_math_ml_element_get_attribute_style_map', [p.pointer], [mi], 'style_property_map_read_only')
        if 'style' in variant:
            p.object('rv_dom_math_ml_element_get_style', [p.pointer], [math], 'css_style_declaration')
        if 'rect' in variant:
            p.object('rv_dom_element_get_bounding_client_rect', [p.pointer], [mi], 'dom_rect_read_only')
        document = p.object('rv_dom_node_get_owner_document', [p.pointer], [math], 'node')
        if 'typed' in variant or 'text' in variant:
            sys.path.insert(0, 'tests/abi')
            import mathml_surface as m
            target_map = p.object('rv_dom_math_ml_element_get_attribute_style_map', [p.pointer], [mi], 'style_property_map_read_only')
            if 'typed' in variant:
                value = p.object('rv_dom_css_unit_value_create', [p.pointer, ctypes.c_double, ctypes.c_char_p, p.integer], [document, 10.0, b'px', 2], 'css_style_value')
                item = m.StyleInput(1, 1, value, m.Span())
            else:
                encoded = ctypes.create_string_buffer(b'rgb(0, 0, 255)', 14)
                item = m.StyleInput(1, 2, None, m.Span(ctypes.cast(encoded, ctypes.c_void_p), 14))
            items = (m.StyleInput * 1)(item)
            name = b'padding-left' if 'typed' in variant else b'background-color'
            p.call('rv_dom_style_property_map_set', [p.pointer, p.pointer, ctypes.c_char_p, p.integer, ctypes.POINTER(m.StyleInputs)], target_map, document, name, len(name), ctypes.byref(m.StyleInputs(1, 1, items)))
            p.update()
        if 'computed' in variant:
            p.object('rv_dom_window_get_computed_style', [p.pointer, p.pointer, p.pointer, p.integer], [document, mi, None, -1], 'css_style_declaration')
        if 'tab' in variant:
            p.call('rv_dom_math_ml_element_focus', [p.pointer, p.pointer], p.node('focusable'), None)
            p.bind('rv_host_key', p.integer, [p.pointer, p.integer, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p, p.integer, p.integer])(p.host, 0, b'Tab', b'Tab', b'', 0, 0)
        if 'remove' in variant:
            p.call('rv_node_remove', [p.pointer], math)
        watches = [p.bind('rv_node_watch', p.pointer, [p.pointer])(owner) for owner in [math, mi, inline, row]]
        keep = []
        if 'keepdataset' in variant:
            keep.append(('rv_dom_dom_string_map_release', p.object('rv_dom_math_ml_element_get_dataset', [p.pointer], [math], 'dom_string_map')))
        if 'keepmap' in variant:
            keep.append(('rv_dom_style_property_map_read_only_release', p.object('rv_dom_math_ml_element_get_attribute_style_map', [p.pointer], [mi], 'style_property_map_read_only')))
        if 'keepnode' in variant:
            extra = p.bind('rv_node_retain', p.pointer, [p.pointer])(math)
            p.retained.append(('rv_node_release', extra))
            keep.append(('rv_node_release', extra))
        if 'keephtmldataset' in variant:
            body = p.bind('rv_document_body', p.pointer, [p.pointer])(p.host)
            p.retained.append(('rv_node_release', body))
            html = p.node('html')
            keep.append(('rv_dom_dom_string_map_release', p.object('rv_dom_html_element_get_dataset', [p.pointer], [html], 'dom_string_map')))
        for entry in keep:
            p.retained.remove(entry)
        for release, value in list(reversed(p.retained)):
            p.bind(release, None, [p.pointer])(value)
        p.retained.clear()
        p.dispose_host()
        p.collect()
        for release, value in keep:
            p.bind(release, None, [p.pointer])(value)
        p.collect()
        p.collect()
        alive = p.bind('rv_watch_alive', p.integer, [p.pointer])
        print(variant, [alive(watch) for watch in watches], flush=True)
        for watch in watches:
            p.bind('rv_watch_release', None, [p.pointer])(watch)
