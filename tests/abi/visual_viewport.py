"""G03 visual viewport probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/visual-viewport-oracle.json through Window.visualViewport, rv_host_resize, rv_host_set_device_scale,
rv_host_set_page_scale and rv_host_wheel, comparing VisualViewport's members and the ordered distinct visualViewport
and window resize/scroll events of every step. Then checks page scale and obscured inset arguments, what the insets
change, listener removal, errors and a VisualViewport held past rv_host_destroy."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from utf8_inputs import Utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED, DETACHED, WRONG_INTERFACE = 0, -1, -2, -9, -10, -11
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
ABI = 54
MEMBERS = {'offsetLeft': 'offset_left', 'offsetTop': 'offset_top', 'pageLeft': 'page_left', 'pageTop': 'page_top',
           'width': 'width', 'height': 'height', 'scale': 'scale'}
# Steps where the engine differs from Chromium (docs/visual-viewport-evidence). While page-scaled, WebKit's layout
# viewport stays at the document origin, so offsetLeft/offsetTop equal pageLeft/pageTop, and every visual viewport pan
# also scrolls the window.
QUALIFIED = {
    'scrollTo(100, 50) at page scale 2': 'offsets equal the page position; the visual viewport also fires scroll',
    'wheel 30, 40 at 150, 100 at page scale 2': 'offsets equal the page position; the window also fires scroll',
    'page scale 1 at 100,50': 'the window also fires scroll',
}


class WindowMetrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('innerWidth', ctypes.c_int32), ('innerHeight', ctypes.c_int32),
                ('outerWidth', ctypes.c_int32), ('outerHeight', ctypes.c_int32), ('devicePixelRatio', ctypes.c_double)]


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'visual-viewport-oracle.json').read_text())
    report = {'browser': oracle['browser'], 'steps': [], 'qualified': [], 'pageScale': [], 'insets': []}
    with SvgProbe(native_directory, *oracle['viewport']) as p:
        P, I, D = p.pointer, p.integer, ctypes.c_double
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        for feature in [b'visual-viewport', b'dom:VisualViewport', b'page-scale', b'obscured-insets']:
            p.expect(has(feature) == 1, feature.decode() + ' advertised')
        get_viewport = p.bind('rv_dom_window_get_visual_viewport', I, [P, ctypes.POINTER(P)])
        getters = {name: p.bind('rv_dom_visual_viewport_get_' + c, I, [P, ctypes.POINTER(D)]) for name, c in MEMBERS.items()}
        window_scroll = {axis: p.bind('rv_dom_window_get_scroll_' + axis, I, [P, ctypes.POINTER(D)]) for axis in 'xy'}
        scroll_to = p.bind('rv_dom_window_scroll_to_2', I, [P, D, D])
        set_page_scale = p.bind('rv_host_set_page_scale', I, [P, D, I, I])
        page_scale = p.bind('rv_host_page_scale', I, [P, ctypes.POINTER(D)])
        set_insets = p.bind('rv_host_set_obscured_insets', I, [P, D, D, D, D])
        set_device_scale = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
        resize = p.bind('rv_host_resize', I, [P, I, I])
        wheel = p.bind('rv_host_wheel', I, [P, I, I, ctypes.c_float, ctypes.c_float, I])
        metrics = p.bind('rv_host_window_metrics', I, [P, ctypes.POINTER(WindowMetrics)])
        element_at = p.bind('rv_host_element_at', P, [P, I, I])
        element_rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
        by_id = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
        same_node = p.bind('rv_dom_node_is_same_node', I, [P, P, ctypes.POINTER(I)])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        add = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        remove = p.bind('rv_listener_remove', I, [P])
        event_type = p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)])
        get_target = p.bind('rv_event_get_target', P, [P, I])
        target_equals = p.bind('rv_event_target_equals', I, [P, P])
        target_release = p.bind('rv_event_target_release', None, [P])
        as_target = p.bind('rv_node_as_event_target', P, [P])
        node_release = p.bind('rv_node_release', None, [P])
        window = p.bind('rv_host_window_event_target', P, [P])(p.host)
        p.expect(bool(window), 'window target')
        p.load(oracle['page'] + '<div id=top style="position:absolute;left:0;top:0;width:50px;height:50px"></div>'
               '<div id=low style="position:absolute;left:0;top:150px;width:50px;height:50px"></div>', standalone=False)
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.expect(bool(document), 'document')
        top, low = by_id(p.host, b'top'), by_id(p.host, b'low')
        p.expect(bool(top) and bool(low), 'probe boxes')

        viewport = P()
        p.expect(get_viewport(document, ctypes.byref(viewport)) == OK and bool(viewport), 'Window.visualViewport')
        again = P()
        p.expect(get_viewport(document, ctypes.byref(again)) == OK and target_equals(viewport, again) == 1, 'visualViewport is [SameObject]')
        target_release(again)

        log = []

        def listener(source, target):
            def run(context, event):
                current = get_target(event, 1)
                try:
                    if not target_equals(current, target):
                        log.append(source + ':wrong currentTarget')
                        return 0
                finally:
                    target_release(current)
                buffer, length = ctypes.create_string_buffer(32), I()
                event_type(event, buffer, len(buffer), ctypes.byref(length))
                log.append(source + ':' + buffer.raw[:length.value].decode())
                return 0
            return CALLBACK(run)

        callbacks = {'visualViewport': listener('visualViewport', viewport), 'window': listener('window', window)}
        listeners = []
        for source, target in [('visualViewport', viewport), ('window', window)]:
            for kind in [b'resize', b'scroll']:
                handle = add(target, kind, 0, callbacks[source], None)
                p.expect(bool(handle), source + ' listener')
                listeners.append(handle)

        def settle():
            for _ in range(4):
                p.update()
                p.expect(cycle(20) >= 0, 'run loop cycle')
            p.update()

        def read():
            result = {}
            for name, getter in getters.items():
                value = D(math.nan)
                p.expect(getter(viewport, ctypes.byref(value)) == OK, 'VisualViewport.' + name)
                result[name] = value.value
            return result

        def window_state():
            value = WindowMetrics(size=ctypes.sizeof(WindowMetrics))
            p.expect(metrics(p.host, ctypes.byref(value)) == OK, 'window metrics')
            x, y = D(), D()
            p.expect(window_scroll['x'](document, ctypes.byref(x)) == OK and window_scroll['y'](document, ctypes.byref(y)) == OK, 'window scroll')
            return {'innerWidth': value.innerWidth, 'innerHeight': value.innerHeight, 'scrollX': x.value, 'scrollY': y.value}

        def distinct(events):
            return list(dict.fromkeys(events))

        settle()
        for step in oracle['steps']:
            settle()
            log.clear()
            args, operation = step['args'], step['operation']
            if operation == 'scrollTo':
                p.expect(scroll_to(document, *args) == OK, step['name'])
            elif operation == 'resize':
                p.expect(resize(p.host, *args) == OK, step['name'])
            elif operation == 'deviceScale':
                p.expect(set_device_scale(p.host, args[0]) == OK, step['name'])
            elif operation == 'pageScale':
                p.expect(set_page_scale(p.host, *args) == OK, step['name'])
            elif operation == 'wheel':
                p.expect(wheel(p.host, args[0], args[1], args[2], args[3], 0) >= 0, step['name'])
            settle()
            native, events = read(), distinct(log)
            p.expect('visualViewport:wrong currentTarget' not in events and 'window:wrong currentTarget' not in events, step['name'] + ' currentTarget')
            chromium = {name: step['state'][name] for name in MEMBERS}
            name = step['name']
            # Chromium's page position matches in every step: the qualifications are confined to the offsets and events.
            for member in ['pageLeft', 'pageTop', 'width', 'height', 'scale']:
                p.expect(native[member] == chromium[member], name + ' ' + member + ': native ' + str(native[member]) + ' Chromium ' + str(chromium[member]))
            differs = native != chromium or events != step['events']
            p.expect(differs == (name in QUALIFIED), name + ' qualification: native ' + str(native) + ' ' + str(events)
                     + ' Chromium ' + str(chromium) + ' ' + str(step['events']))
            if name in QUALIFIED:
                p.expect((native['offsetLeft'], native['offsetTop']) == ((native['pageLeft'], native['pageTop']) if native['scale'] != 1 else (0.0, 0.0)),
                         name + ' native offsets: ' + str(native))
                p.expect([e for e in events if e != 'window:scroll' and e != 'visualViewport:scroll'] == [e for e in step['events'] if e not in ('window:scroll', 'visualViewport:scroll')]
                         and 'window:scroll' in events and 'visualViewport:scroll' in events, name + ' native events: ' + str(events))
                report['qualified'].append({'step': name, 'reason': QUALIFIED[name], 'native': native, 'chromium': chromium,
                                            'nativeEvents': events, 'chromiumEvents': step['events']})
            report['steps'].append({'name': name, 'native': native, 'nativeEvents': events, 'nativeWindow': window_state(),
                                    'chromiumWindow': {key: step['state'][key] for key in ['innerWidth', 'innerHeight', 'scrollX', 'scrollY']}})

        # Page scale arguments: finite and above 0, otherwise RV_ERR_UNSUPPORTED and the scale stays. The engine
        # applies the scale unclamped.
        current = D()
        for value in [0.0, -1.0, math.nan, math.inf, -math.inf]:
            settle()
            log.clear()
            p.expect(set_page_scale(p.host, value, 0, 0) == UNSUPPORTED, 'page scale ' + repr(value) + ' rejected')
            settle()
            p.expect(page_scale(p.host, ctypes.byref(current)) == OK and current.value == 1 and read()['scale'] == 1 and log == [],
                     'page scale ' + repr(value) + ' leaves scale 1: ' + str(log))
        for value, size in [(0.25, (1280.0, 960.0)), (10.0, (32.0, 24.0)), (1.5, (320 / 1.5, 160.0)), (1.0, (320.0, 240.0))]:
            settle()
            log.clear()
            p.expect(set_page_scale(p.host, value, 0, 0) == OK, 'page scale ' + repr(value))
            settle()
            state = read()
            p.expect(page_scale(p.host, ctypes.byref(current)) == OK and math.isclose(current.value, value, rel_tol=1e-6), 'rv_host_page_scale ' + repr(value))
            # The size is in LayoutUnits: whole multiples of 1/64 CSS pixel.
            p.expect(math.isclose(state['scale'], value, rel_tol=1e-6) and abs(state['width'] - size[0]) < 1 / 64
                     and abs(state['height'] - size[1]) < 1 / 64 and (state['width'] * 64).is_integer(), 'page scale ' + repr(value) + ' unclamped: ' + str(state))
            p.expect(distinct(log) == ['visualViewport:resize'], 'page scale ' + repr(value) + ' fires one visualViewport resize: ' + str(log))
            report['pageScale'].append({'scale': value, 'state': state, 'events': distinct(log)})
        # An explicit origin scrolls the scaled document there.
        settle()
        log.clear()
        p.expect(set_page_scale(p.host, 2.0, 40, 60) == OK, 'page scale 2 at 40,60')
        settle()
        state = read()
        p.expect((state['pageLeft'], state['pageTop'], state['width'], state['height']) == (20.0, 30.0, 160.0, 120.0), 'origin 40,60 at scale 2: ' + str(state))
        p.expect(distinct(log) == ['visualViewport:resize', 'window:scroll', 'visualViewport:scroll'], 'origin events ' + str(log))
        p.expect(set_page_scale(p.host, 1.0, 0, 0) == OK, 'page scale reset')
        settle()

        # Obscured insets shrink the visual viewport and the window's inner size by the covered edges and leave the
        # document's coordinates in place: hit testing covers only the unobscured area.
        for value in [(-1.0, 0, 0, 0), (0, math.nan, 0, 0), (0, 0, math.inf, 0), (0, 0, 0, -0.5)]:
            p.expect(set_insets(p.host, *value) == UNSUPPORTED, 'insets ' + repr(value) + ' rejected')
        rect = [D() for _ in range(4)]
        for insets, expected in [((20.0, 0.0, 40.0, 0.0), (320.0, 180.0)), ((0.0, 30.0, 0.0, 10.0), (280.0, 240.0)), ((0.0, 0.0, 0.0, 0.0), (320.0, 240.0))]:
            settle()
            log.clear()
            p.expect(set_insets(p.host, *insets) == OK, 'insets ' + repr(insets))
            settle()
            state, window_values = read(), window_state()
            p.expect((state['width'], state['height']) == expected and (window_values['innerWidth'], window_values['innerHeight']) == tuple(int(v) for v in expected),
                     'insets ' + repr(insets) + ' size: ' + str(state) + ' ' + str(window_values))
            p.expect((state['offsetLeft'], state['offsetTop'], state['pageLeft'], state['pageTop'], state['scale']) == (0.0, 0.0, 0.0, 0.0, 1.0), 'insets ' + repr(insets) + ' position')
            p.expect(distinct(log) == ['window:resize', 'visualViewport:resize'], 'insets ' + repr(insets) + ' events ' + str(log))
            p.expect(element_rect(top, *[ctypes.byref(v) for v in rect]) == OK and [v.value for v in rect] == [0.0, 0.0, 50.0, 50.0], 'insets keep the document in place')
            hits = {}
            for label, x, y in [('top', 10, 10), ('low', 10, 160), ('right', expected[0] - 1, 10), ('bottom', 10, expected[1] - 1)]:
                node = element_at(p.host, int(x), int(y))
                hits[label] = bool(node)
                if node and label in ('top', 'low'):
                    same = I()
                    p.expect(same_node(node, top if label == 'top' else low, ctypes.byref(same)) == OK, 'isSameNode')
                    hits[label] = same.value == 1
                if node:
                    node_release(node)
            # The top inset leaves the content in place: the box at the document's top still answers at y 10.
            p.expect(hits['top'] and hits['right'] and hits['bottom'] and hits['low'] == (expected[1] > 160), 'insets ' + repr(insets) + ' hit inside: ' + str(hits))
            report['insets'].append({'insets': insets, 'state': state, 'window': window_values, 'events': distinct(log), 'hits': hits})
            # The covered right and bottom areas have nothing to hit.
            covered = [(10, int(expected[1])), (int(expected[0]), 10)] + ([(10, 239)] if insets[2] else []) + ([(319, 10)] if insets[1] else [])
            for x, y in covered:
                node = element_at(p.host, x, y)
                p.expect(not node, 'insets ' + repr(insets) + ' no hit at ' + str((x, y)))
                if node:
                    node_release(node)

        # Errors.
        value = D()
        p.expect(getters['width'](None, ctypes.byref(value)) == NULL_ARGUMENT and getters['scale'](viewport, None) == NULL_ARGUMENT, 'getter nulls')
        p.expect(get_viewport(None, ctypes.byref(P())) == NULL_ARGUMENT and get_viewport(document, None) == NULL_ARGUMENT, 'visualViewport nulls')
        p.expect(getters['width'](window, ctypes.byref(value)) == WRONG_INTERFACE, 'the window is not a VisualViewport')
        top_target = as_target(top)
        p.expect(getters['height'](top_target, ctypes.byref(value)) == WRONG_INTERFACE, 'an element is not a VisualViewport')
        target_release(top_target)
        p.expect(get_viewport(top, ctypes.byref(P())) == WRONG_INTERFACE, 'an element is not a document')
        p.expect(set_page_scale(None, 2.0, 0, 0) == NULL_ARGUMENT and page_scale(p.host, None) == NULL_ARGUMENT
                 and set_insets(None, 0, 0, 0, 0) == NULL_ARGUMENT, 'host input nulls')
        implementation = P()
        p.expect(p.bind('rv_dom_document_get_implementation', I, [P, ctypes.POINTER(P)])(document, ctypes.byref(implementation)) == OK, 'implementation')
        windowless = P()
        p.expect(p.bind('rv_dom_dom_implementation_create_html_document', I, [P, Utf8, ctypes.POINTER(P)])(implementation, b'windowless', ctypes.byref(windowless)) == OK, 'windowless document')
        p.bind('rv_dom_dom_implementation_release', None, [P])(implementation)
        p.expect(get_viewport(windowless, ctypes.byref(P())) == UNSUPPORTED, 'a windowless document has no visualViewport')
        node_release(windowless)
        results = []

        def off_thread():
            v = D()
            results.append((getters['width'](viewport, ctypes.byref(v)), get_viewport(document, ctypes.byref(P())),
                            set_page_scale(p.host, 2.0, 0, 0), set_insets(p.host, 1, 1, 1, 1), page_scale(p.host, ctypes.byref(v))))

        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        p.expect(results == [(WRONG_THREAD,) * 5], 'wrong thread ' + str(results))
        p.expect(read()['scale'] == 1 and read()['width'] == 320, 'off-thread calls change nothing')

        # Teardown: removed listeners stop delivery; a held VisualViewport reports RV_ERR_DETACHED after destroy.
        for handle in listeners:
            p.expect(remove(handle) == OK, 'listener removal')
        settle()
        log.clear()
        p.expect(resize(p.host, 300, 200) == OK and set_page_scale(p.host, 2.0, 0, 0) == OK, 'changes after removal')
        settle()
        p.expect(log == [], 'no delivery after listener removal: ' + str(log))
        late = add(viewport, b'resize', 0, callbacks['visualViewport'], None)
        p.expect(bool(late), 'listener held past destroy')
        node_release(top)
        node_release(low)
        target_release(window)
        p.dispose_host()
        for name, getter in getters.items():
            value = D(-7)
            p.expect(getter(viewport, ctypes.byref(value)) == DETACHED and value.value == -7, name + ' after destroy is RV_ERR_DETACHED')
        p.expect(get_viewport(document, ctypes.byref(P())) in (OK, UNSUPPORTED), 'visualViewport after destroy is inert')
        p.expect(remove(late) == OK, 'late listener removal')
        target_release(viewport)
        node_release(document)
        p.collect()
        p.expect(log == [], 'no delivery after destroy')
        report['assertions'] = p.assertions
        return p.assertions, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    assertions, report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS visual_viewport: {assertions} assertions', flush=True)
