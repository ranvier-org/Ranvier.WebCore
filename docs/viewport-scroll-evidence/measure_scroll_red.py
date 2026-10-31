"""G05 RED measurement: replays the Chromium oracle steps of tests/fixtures/viewport-scroll-oracle.json on a runtime
through the exports that exist today (the scrolling element's generated Element.scroll* members for the viewport, the
box's for the element), and writes the native values and events beside Chromium's."""
import ctypes
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / 'tests/abi'))
from svg_paint_probe import SvgProbe

CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)


class ScrollToOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('behavior', ctypes.c_int32), ('left', ctypes.POINTER(ctypes.c_double)), ('top', ctypes.POINTER(ctypes.c_double))]


BEHAVIOR = {None: 0, 'auto': 0, 'instant': 1, 'smooth': 2}


def measure(native_directory, out):
    oracle = json.loads((repo / 'tests/fixtures/viewport-scroll-oracle.json').read_text())
    result = {'runtime': str(native_directory), 'cases': [], 'missing': []}
    with SvgProbe(native_directory, 320, 240) as p:
        P, I, D = p.pointer, p.integer, ctypes.c_double
        result['abiVersion'] = p.bind('rv_abi_version', I, [])()
        for name in ['rv_dom_window_get_scroll_x', 'rv_dom_window_get_scroll_y', 'rv_dom_window_scroll_to', 'rv_dom_window_scroll_by',
                     'rv_dom_window_scroll', 'rv_dom_window_get_page_x_offset']:
            if not hasattr(p.library, name):
                result['missing'].append(name)
        p.load(oracle['page'], standalone=False)
        document = p.bind('rv_host_document', P, [P])(p.host)
        root = P()
        p.expect(p.bind('rv_dom_document_get_scrolling_element', I, [P, ctypes.POINTER(P)])(document, ctypes.byref(root)) == 0 and bool(root), 'scrolling element')
        box = p.node('box')
        position = p.bind('rv_host_scroll_position', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
        getter = {f: p.bind('rv_dom_element_get_' + f, I, [P, ctypes.POINTER(I)]) for f in ['scroll_left', 'scroll_top', 'scroll_width', 'scroll_height', 'client_width', 'client_height']}
        setter = {f: p.bind('rv_dom_element_set_' + f, I, [P, I]) for f in ['scroll_left', 'scroll_top']}
        pair = {op: p.bind('rv_dom_element_' + op, I, [P, D, D]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        options = {op: p.bind('rv_dom_element_' + op + '_1', I, [P, ctypes.POINTER(ScrollToOptions)]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        window = p.bind('rv_host_window_event_target', P, [P])(p.host)
        box_target = p.bind('rv_node_as_event_target', P, [P])(box)
        add = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        event_type = p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)])

        def read(element, field):
            value = I(-12345)
            p.expect(getter[field](element, ctypes.byref(value)) == 0, field)
            return value.value

        def state():
            x, y = I(), I()
            position(p.host, ctypes.byref(x), ctypes.byref(y))
            return {'hostX': x.value, 'hostY': y.value, 'documentLeft': read(root, 'scroll_left'), 'documentTop': read(root, 'scroll_top'),
                    'boxLeft': read(box, 'scroll_left'), 'boxTop': read(box, 'scroll_top')}

        log = []

        def listener(source):
            def run(context, event):
                buffer, length = ctypes.create_string_buffer(32), I()
                event_type(event, buffer, len(buffer), ctypes.byref(length))
                log.append(dict(listener=source, type=buffer.raw[:length.value].decode(), **state()))
                return 0
            return CALLBACK(run)

        callbacks = [listener('window'), listener('box')]
        for kind in [b'scroll', b'scrollend']:
            p.expect(bool(add(window, kind, 0, callbacks[0], None)), 'window listener')
            p.expect(bool(add(box_target, kind, 0, callbacks[1], None)), 'box listener')

        def settle(rounds=4):
            for _ in range(rounds):
                p.update()
                cycle(20)
            p.update()

        def settle_smooth():
            for _ in range(200):
                p.update()
                cycle(16)
                if any(item['type'] == 'scrollend' for item in log):
                    break
            settle()

        for case in oracle['cases']:
            p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, case['scale'])
            element = root if case['scroller'] == 'viewport' else box
            pair['scroll_to'](root, 0, 0)
            pair['scroll_to'](box, 0, 0)
            settle()
            log.clear()
            maximum = {'width': read(element, 'scroll_width') - read(element, 'client_width'), 'height': read(element, 'scroll_height') - read(element, 'client_height')}
            record = {'scale': case['scale'], 'scroller': case['scroller'], 'maximum': maximum, 'chromiumMaximum': case['maximum'], 'steps': []}
            for step in case['steps']:
                args, operation = step['args'], step['operation']
                op = {'scrollTo': 'scroll_to', 'scrollBy': 'scroll_by', 'scroll': 'scroll'}.get(operation)
                smooth = False
                if operation == 'set':
                    # The generated setters take int32 (WebKit IDL long): the caller converts, as ToInt32 truncates.
                    setter['scroll_top'](element, int(args[1]))
                    setter['scroll_left'](element, int(args[0]))
                elif isinstance(args[0], dict):
                    holders = {k: D(args[0][k]) for k in ['left', 'top'] if k in args[0]}
                    value = ScrollToOptions(size=ctypes.sizeof(ScrollToOptions), behavior=BEHAVIOR[args[0].get('behavior')],
                                            left=ctypes.pointer(holders['left']) if 'left' in holders else None,
                                            top=ctypes.pointer(holders['top']) if 'top' in holders else None)
                    smooth = args[0].get('behavior') == 'smooth'
                    p.expect(options[op](element, ctypes.byref(value)) == 0, step['name'])
                else:
                    p.expect(pair[op](element, args[0], args[1]) == 0, step['name'])
                settle_smooth() if smooth else settle()
                after = state()
                native = (after['documentLeft'], after['documentTop']) if case['scroller'] == 'viewport' else (after['boxLeft'], after['boxTop'])
                chromium = (step['after']['scrollX'], step['after']['scrollY']) if case['scroller'] == 'viewport' else (step['after']['boxLeft'], step['after']['boxTop'])
                record['steps'].append({'name': step['name'], 'native': native, 'chromium': chromium, 'nativeState': after,
                                        'nativeEvents': [e['listener'] + ':' + e['type'] for e in log],
                                        'chromiumEvents': [e['listener'] + ':' + e['type'] for e in step['events']]})
                log.clear()
            result['cases'].append(record)
        p.release_all()
    Path(out).write_text(json.dumps(result, indent=2) + '\n')
    for case in result['cases']:
        print(case['scale'], case['scroller'], 'max', case['maximum'], 'chromium', case['chromiumMaximum'])
        for s in case['steps']:
            flag = '' if (s['native'] == tuple(s['chromium']) and s['nativeEvents'] == s['chromiumEvents']) else '  <> '
            print('  ', flag, s['name'], s['native'], tuple(s['chromium']), s['nativeEvents'], s['chromiumEvents'] if flag else '')
    print('missing', result['missing'], 'abi', result['abiVersion'])


if __name__ == '__main__':
    measure(sys.argv[1], sys.argv[2])
