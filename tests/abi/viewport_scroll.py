"""G05 viewport scrolling probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/viewport-scroll-oracle.json through the Window scroll members, the scrolling element and a scrolling
box at device scales 1, 1.5 and 2, then checks the qualified truncation steps, clamping, scroll/scrollend delivery,
errors and a document held past rv_host_destroy."""

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
OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -9, -11
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
ABI = 54
BEHAVIOR = {None: 0, 'auto': 0, 'instant': 1, 'smooth': 2}
# Steps where the engine's truncation toward zero gives another whole pixel than Chromium's rounding to nearest, at
# every scale and on every scroller (the qualification in docs/viewport-scroll-evidence).
QUALIFIED = ['scrollTo(10.25, 20.5)', 'scrollTo(10.75, 20.75)', 'scrollTo(10.4, 20.4) from 10.75, 20.75',
             'scrollTo({left: 3.3, top: 7.7, behavior: instant})', 'scrollTo({top: 9.6}) keeps left', 'scroll(5.5, 6.5)',
             'scrollBy(0.4, 0.4)', 'scrollBy(0.4, 0.4) again', 'scrollBy({top: 0.6})', 'scrollBy(-0.3, -0.3)',
             'scrollBy(-0.5, -0.5) from the maximum', 'scrollTop = 33.3, scrollLeft = 11.6',
             'scrollTo({left: 0.5, top: 50.5, behavior: smooth})']


class ScrollToOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('behavior', ctypes.c_int32), ('left', ctypes.POINTER(ctypes.c_double)),
                ('top', ctypes.POINTER(ctypes.c_double))]


def options(value):
    holders = {key: ctypes.c_double(value[key]) for key in ['left', 'top'] if key in value}
    result = ScrollToOptions(size=ctypes.sizeof(ScrollToOptions), behavior=BEHAVIOR[value.get('behavior')],
                             left=ctypes.pointer(holders['left']) if 'left' in holders else None,
                             top=ctypes.pointer(holders['top']) if 'top' in holders else None)
    result._holders = holders
    return result


def truncated(step, current, maximum):
    """The engine's whole-pixel position after the step: the CSS target truncated toward zero, then clamped."""
    args, operation = step['args'], step['operation']
    if operation == 'set':
        target = [float(int(args[0])), float(int(args[1]))]
    elif isinstance(args[0], dict):
        target = [args[0].get('left'), args[0].get('top')]
        if operation == 'scrollBy':
            target = [current[i] + (target[i] or 0) for i in range(2)]
        target = [current[i] if target[i] is None else target[i] for i in range(2)]
    else:
        target = [current[0] + args[0], current[1] + args[1]] if operation == 'scrollBy' else list(args)
    bounds = [maximum['width'], maximum['height']]
    return tuple(min(max(int(math.trunc(target[i])), 0), bounds[i]) for i in range(2))


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'viewport-scroll-oracle.json').read_text())
    report = {'browser': oracle['browser'], 'cases': [], 'qualified': [], 'smooth': []}
    with SvgProbe(native_directory, *oracle['viewport']) as p:
        P, I, D = p.pointer, p.integer, ctypes.c_double
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'dom-window-scrolling') == 1, 'dom-window-scrolling advertised')
        window_get = {axis: p.bind('rv_dom_window_get_scroll_' + axis, I, [P, ctypes.POINTER(D)]) for axis in 'xy'}
        window_pair = {op: p.bind('rv_dom_window_' + op + '_2', I, [P, D, D]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        window_options = {op: p.bind('rv_dom_window_' + op + '_1', I, [P, ctypes.POINTER(ScrollToOptions)]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        element_get = {f: p.bind('rv_dom_element_get_' + f, I, [P, ctypes.POINTER(I)]) for f in ['scroll_left', 'scroll_top', 'scroll_width', 'scroll_height', 'client_width', 'client_height']}
        element_set = {f: p.bind('rv_dom_element_set_' + f, I, [P, I]) for f in ['scroll_left', 'scroll_top']}
        element_pair = {op: p.bind('rv_dom_element_' + op, I, [P, D, D]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        element_options = {op: p.bind('rv_dom_element_' + op + '_1', I, [P, ctypes.POINTER(ScrollToOptions)]) for op in ['scroll', 'scroll_to', 'scroll_by']}
        host_position = p.bind('rv_host_scroll_position', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        add = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        remove = p.bind('rv_listener_remove', I, [P])
        event_type = p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)])
        target_release = p.bind('rv_event_target_release', None, [P])
        node_release = p.bind('rv_node_release', None, [P])
        p.load(oracle['page'], standalone=False)
        document = p.bind('rv_host_document', P, [P])(p.host)
        p.expect(bool(document), 'document')
        root = P()
        p.expect(p.bind('rv_dom_document_get_scrolling_element', I, [P, ctypes.POINTER(P)])(document, ctypes.byref(root)) == OK and bool(root), 'scrolling element')
        root = root.value
        box = p.node('box')

        def element(target, field):
            value = I(-12345)
            p.expect(element_get[field](target, ctypes.byref(value)) == OK, field)
            return value.value

        def window_position():
            values = []
            for axis in 'xy':
                value = D(-1)
                p.expect(window_get[axis](document, ctypes.byref(value)) == OK, 'scroll' + axis.upper())
                values.append(value.value)
            return tuple(values)

        def viewport():
            x, y = I(), I()
            p.expect(host_position(p.host, ctypes.byref(x), ctypes.byref(y)) == OK, 'host scroll position')
            through_window = window_position()
            through_root = (element(root, 'scroll_left'), element(root, 'scroll_top'))
            p.expect(through_window == through_root == (x.value, y.value), 'viewport reads agree ' + str((through_window, through_root, x.value, y.value)))
            return through_root

        def box_position():
            return element(box, 'scroll_left'), element(box, 'scroll_top')

        log = []

        def listener(source):
            def run(context, event):
                buffer, length = ctypes.create_string_buffer(32), I()
                event_type(event, buffer, len(buffer), ctypes.byref(length))
                log.append(source + ':' + buffer.raw[:length.value].decode())
                return 0
            return CALLBACK(run)

        window = p.bind('rv_host_window_event_target', P, [P])(p.host)
        box_target = p.bind('rv_node_as_event_target', P, [P])(box)
        callbacks = [listener('window'), listener('box')]
        listeners = []
        for kind in [b'scroll', b'scrollend']:
            listeners.append(add(window, kind, 0, callbacks[0], None))
            listeners.append(add(box_target, kind, 0, callbacks[1], None))
        p.expect(all(listeners), 'scroll listeners')

        def settle(smooth=False):
            for _ in range(200 if smooth else 4):
                p.update()
                cycle(16 if smooth else 20)
                if smooth and 'scrollend' in ''.join(log):
                    break
            for _ in range(3):
                p.update()
                cycle(20)

        def run_step(route, step):
            args, operation = step['args'], step['operation']
            name = {'scrollTo': 'scroll_to', 'scrollBy': 'scroll_by', 'scroll': 'scroll'}.get(operation)
            if operation == 'set':
                # The setters are WebIDL long: the caller converts the CSS value, and ToInt32 truncates.
                target = box if route == 'box' else root
                p.expect(element_set['scroll_top'](target, int(args[1])) == OK and element_set['scroll_left'](target, int(args[0])) == OK, step['name'])
            elif route == 'window':
                status = window_options[name](document, ctypes.byref(options(args[0]))) if isinstance(args[0], dict) else window_pair[name](document, *args)
                p.expect(status == OK, step['name'])
            else:
                target = box if route == 'box' else root
                status = element_options[name](target, ctypes.byref(options(args[0]))) if isinstance(args[0], dict) else element_pair[name](target, *args)
                p.expect(status == OK, step['name'])

        for case in oracle['cases']:
            p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, case['scale'])
            routes = ['window', 'scrollingElement'] if case['scroller'] == 'viewport' else ['box']
            scroller = root if case['scroller'] == 'viewport' else box
            for route in routes:
                window_pair['scroll_to'](document, 0, 0)
                element_pair['scroll_to'](box, 0, 0)
                settle()
                log.clear()
                maximum = {'width': element(scroller, 'scroll_width') - element(scroller, 'client_width'),
                           'height': element(scroller, 'scroll_height') - element(scroller, 'client_height')}
                label = '{}@{} {}'.format(case['scroller'], case['scale'], route)
                p.expect(maximum == case['maximum'], label + ' maximum ' + str(maximum) + ' vs ' + str(case['maximum']))
                read = viewport if case['scroller'] == 'viewport' else box_position
                source = 'box' if case['scroller'] == 'box' else 'window'
                record = {'case': label, 'maximum': maximum, 'steps': []}
                for step in case['steps']:
                    before = read()
                    expected = truncated(step, before, maximum)
                    smooth = isinstance(step['args'][0], dict) and step['args'][0].get('behavior') == 'smooth'
                    run_step(route, step)
                    settle(smooth)
                    after = read()
                    events = list(log)
                    log.clear()
                    chromium = (step['after']['scrollX'], step['after']['scrollY']) if case['scroller'] == 'viewport' else (step['after']['boxLeft'], step['after']['boxTop'])
                    chromium_events = [e['listener'] + ':' + e['type'] for e in step['events']]
                    p.expect(after == expected, label + ' ' + step['name'] + ' truncates toward zero: ' + str(after) + ' expected ' + str(expected))
                    p.expect(all(float(v).is_integer() for v in chromium), label + ' Chromium keeps whole pixels: ' + str(chromium))
                    if smooth:
                        p.expect(after != before and events[-1:] == [source + ':scrollend'] and set(events[:-1]) == {source + ':scroll'} and len(events) >= 2,
                                 label + ' smooth scroll then one scrollend: ' + str(events))
                        report['smooth'].append({'case': label, 'native': events, 'chromium': chromium_events})
                    else:
                        moved = after != before
                        p.expect(events == ([source + ':scroll', source + ':scrollend'] if moved else []), label + ' ' + step['name'] + ' events ' + str(events))
                    # A step is qualified when its whole-pixel value or, for an instant scroll, its events differ.
                    qualified = after != tuple(chromium) or (not smooth and events != chromium_events)
                    p.expect(qualified == (step['name'] in QUALIFIED), label + ' ' + step['name'] + ' qualification: native ' + str(after) + ' Chromium ' + str(chromium)
                             + ' events ' + str(events) + ' vs ' + str(chromium_events))
                    if qualified:
                        report['qualified'].append({'case': label, 'step': step['name'], 'native': after, 'chromium': chromium,
                                                    'nativeEvents': events, 'chromiumEvents': chromium_events})
                    record['steps'].append({'name': step['name'], 'native': after, 'chromium': chromium, 'nativeEvents': events})
                report['cases'].append(record)

        # Options defaults and errors.
        p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, 1.0)
        window_pair['scroll_to'](document, 7, 9)
        settle()
        log.clear()
        p.expect(window_options['scroll_to'](document, None) == OK and window_options['scroll_by'](document, None) == OK, 'NULL options take the IDL default {}')
        empty = ScrollToOptions(size=4, behavior=99)
        p.expect(window_options['scroll'](document, ctypes.byref(empty)) == OK, 'fields past size take their defaults')
        settle()
        p.expect(viewport() == (7, 9) and log == [], 'empty options leave the position: ' + str(log))
        bad = options({'top': 5.0})
        bad.behavior = 7
        p.expect(window_options['scroll_to'](document, ctypes.byref(bad)) == UNSUPPORTED, 'unknown behavior')
        result = D()
        p.expect(window_get['x'](None, ctypes.byref(result)) == NULL_ARGUMENT and window_get['y'](document, None) == NULL_ARGUMENT, 'getter nulls')
        p.expect(window_pair['scroll_to'](None, 1, 1) == NULL_ARGUMENT and window_options['scroll_by'](None, None) == NULL_ARGUMENT, 'operation nulls')
        p.expect(window_get['x'](box, ctypes.byref(result)) == WRONG_INTERFACE and window_pair['scroll_by'](box, 1, 1) == WRONG_INTERFACE, 'an element is not a document')
        implementation = P()
        p.expect(p.bind('rv_dom_document_get_implementation', I, [P, ctypes.POINTER(P)])(document, ctypes.byref(implementation)) == OK, 'implementation')
        detached = P()
        p.expect(p.bind('rv_dom_dom_implementation_create_html_document', I, [P, Utf8, ctypes.POINTER(P)])(implementation, b'detached', ctypes.byref(detached)) == OK and bool(detached), 'windowless document')
        p.bind('rv_dom_dom_implementation_release', None, [P])(implementation)
        p.expect(window_get['y'](detached, ctypes.byref(result)) == UNSUPPORTED and window_pair['scroll'](detached, 1, 1) == UNSUPPORTED
                 and window_options['scroll_to'](detached, None) == UNSUPPORTED, 'a windowless document has no Window')
        node_release(detached)
        thread_results = []

        def off_thread():
            value = D()
            thread_results.append((window_get['x'](document, ctypes.byref(value)), window_pair['scroll_to'](document, 1, 1), window_options['scroll_by'](document, None)))

        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        p.expect(thread_results == [(WRONG_THREAD,) * 3], 'wrong thread ' + str(thread_results))
        p.expect(viewport() == (7, 9), 'off-thread calls do not scroll')

        # A document held past destroy.
        for item in listeners:
            p.expect(remove(item) == OK, 'listener removal')
        target_release(box_target)
        target_release(window)
        node_release(root)
        p.dispose_host()
        status_x = window_get['x'](document, ctypes.byref(result))
        p.expect(status_x == UNSUPPORTED or (status_x == OK and result.value == 0), 'scrollX after destroy: ' + str(status_x))
        p.expect(window_pair['scroll_to'](document, 3, 3) in (OK, UNSUPPORTED) and window_options['scroll_by'](document, None) in (OK, UNSUPPORTED), 'scrolling after destroy is inert')
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
    print(f'PASS viewport_scroll: {assertions} assertions', flush=True)
