"""G02/G12 viewport probe against an actual runtime directory. Compares window metrics, paint size and the delivery
order of resize, scroll, scrollend, visibilitychange, focus/blur and resolution media query changes with the
Chromium oracle tests/fixtures/viewport-events-oracle.json, then checks listener removal, errors and handles held
past rv_host_destroy."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -9, -11
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
TYPES = ['resize', 'scroll', 'scrollend', 'visibilitychange', 'focus', 'blur']
PAGE = '<!doctype html><style>html,body{margin:0}body{height:2000px;width:2000px}</style><body>'
ABI = 54
HIDDEN, VISIBLE = 0, 1


class WindowMetrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_int32), ('innerWidth', ctypes.c_int32), ('innerHeight', ctypes.c_int32),
                ('outerWidth', ctypes.c_int32), ('outerHeight', ctypes.c_int32), ('devicePixelRatio', ctypes.c_double)]


def rounded(value):
    return math.floor(value + 0.5)


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'viewport-events-oracle.json').read_text())
    report = {'browser': oracle['browser'], 'metrics': [], 'steps': [], 'differences': []}
    with SvgProbe(native_directory, 320, 240) as p:
        P, I = p.pointer, p.integer
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
        p.expect(has(b'viewport') == 1, 'viewport advertised')
        window_target = p.bind('rv_host_window_event_target', P, [P])
        metrics = p.bind('rv_host_window_metrics', I, [P, ctypes.POINTER(WindowMetrics)])
        set_visible = p.bind('rv_host_set_visible', I, [P, I])
        match_media = p.bind('rv_host_match_media', P, [P, ctypes.c_char_p])
        query_matches = p.bind('rv_media_query_matches', I, [P, ctypes.POINTER(I)])
        query_media = p.bind('rv_media_query_media', I, [P, P, I, ctypes.POINTER(I)])
        add_listener = p.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        remove_listener = p.bind('rv_listener_remove', I, [P])
        target_release = p.bind('rv_event_target_release', None, [P])
        target_equals = p.bind('rv_event_target_equals', I, [P, P])
        get_target = p.bind('rv_event_get_target', P, [P, I])
        as_node = p.bind('rv_event_target_as_node', P, [P])
        node_release = p.bind('rv_node_release', None, [P])
        resize = p.bind('rv_host_resize', I, [P, I, I])
        set_scale = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
        paint_size = p.bind('rv_host_paint_size', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
        scroll_to = p.bind('rv_host_scroll_to', I, [P, I, I])
        set_focused = p.bind('rv_host_set_focused', I, [P, I])
        cycle = p.bind('rv_run_loop_cycle', I, [I])
        visibility = p.bind('rv_dom_document_get_visibility_state', I, [P, ctypes.POINTER(I)])
        document = p.bind('rv_host_document', P, [P])
        p.load(PAGE, standalone=False)
        page_document = document(p.host)
        p.expect(bool(page_document), 'document')

        def read():
            value = WindowMetrics(size=ctypes.sizeof(WindowMetrics))
            p.expect(metrics(p.host, ctypes.byref(value)) == OK, 'window metrics')
            return value

        def settle():
            for _ in range(3):
                p.update()
                p.expect(cycle(20) >= 0, 'run loop cycle')
            p.update()

        # G02: CSS viewport dimensions against device-pixel paint dimensions.
        for expected in oracle['metrics']:
            p.call('rv_host_resize', [P, I, I], p.host, expected['width'], expected['height'])
            p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, expected['scale'])
            settle()
            value = read()
            width, height = I(), I()
            p.expect(paint_size(p.host, ctypes.byref(width), ctypes.byref(height)) == OK, 'paint size')
            native = {'innerWidth': value.innerWidth, 'innerHeight': value.innerHeight, 'outerWidth': value.outerWidth,
                      'outerHeight': value.outerHeight, 'devicePixelRatio': value.devicePixelRatio,
                      'paintWidth': width.value, 'paintHeight': height.value}
            label = '{width}x{height}@{scale}'.format(**expected)
            report['metrics'].append({'case': label, 'native': native, 'chromium': expected})
            p.expect((native['innerWidth'], native['innerHeight']) == (expected['innerWidth'], expected['innerHeight']), label + ' inner size')
            p.expect((native['outerWidth'], native['outerHeight']) == (expected['width'], expected['height']), label + ' outer size equals the viewport')
            p.expect(math.isclose(native['devicePixelRatio'], expected['devicePixelRatio'], abs_tol=1e-6), label + ' devicePixelRatio')
            floor = (math.floor(expected['width'] * expected['scale']), math.floor(expected['height'] * expected['scale']))
            p.expect((native['paintWidth'], native['paintHeight']) == floor, label + ' native paint truncates: ' + str(native))
            browser = (expected['paintWidth'], expected['paintHeight'])
            p.expect(browser == (rounded(expected['width'] * expected['scale']), rounded(expected['height'] * expected['scale'])), label + ' Chromium paint rounds')
            if browser != floor:
                report['differences'].append({'case': label, 'nativePaint': floor, 'chromiumPaint': browser})

        # G12: delivery order.
        p.call('rv_host_resize', [P, I, I], p.host, 320, 240)
        p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, 1.0)
        p.call('rv_host_set_focused', [P, I], p.host, 1)
        settle()
        window = window_target(p.host)
        p.expect(bool(window), 'window target')
        log, listeners = [], []

        def label_target(event):
            target = get_target(event, 0)
            try:
                if target_equals(target, window):
                    return 'window'
                node = as_node(target)
                if node:
                    node_release(node)
                    return 'document'
                return 'other'
            finally:
                target_release(target)

        def record(source):
            def run(context, event):
                current = get_target(event, 1)
                try:
                    if source == 'window' and not target_equals(current, window):
                        log.append({'source': source, 'type': 'wrong currentTarget'})
                        return 0
                finally:
                    target_release(current)
                buffer, length = ctypes.create_string_buffer(64), I()
                p.bind('rv_event_type', I, [P, P, I, ctypes.POINTER(I)])(event, buffer, len(buffer), ctypes.byref(length))
                state = I(-1)
                visibility(page_document, ctypes.byref(state))
                value = read()
                log.append({'source': source, 'type': buffer.raw[:length.value].decode(), 'target': label_target(event),
                            'innerWidth': value.innerWidth, 'devicePixelRatio': value.devicePixelRatio, 'visibilityState': state.value})
                return 0
            return CALLBACK(run)

        window_callback = record('window')
        for name in TYPES:
            listener = add_listener(window, name.encode(), 0, window_callback, None)
            p.expect(bool(listener), 'window listener ' + name)
            listeners.append(listener)
        armed = {}

        def arm():
            value = read().devicePixelRatio
            media = '(resolution: {}dppx)'.format(format(value, 'g')).encode()
            query = match_media(p.host, media)
            p.expect(bool(query), 'media query list')
            matches = I(-1)
            p.expect(query_matches(query, ctypes.byref(matches)) == OK and matches.value == 1, 'armed query matches')
            buffer, length = ctypes.create_string_buffer(128), I()
            p.expect(query_media(query, buffer, len(buffer), ctypes.byref(length)) == OK, 'media text')
            text = buffer.raw[:length.value].decode()
            callback = record('media:' + text)
            listener = add_listener(query, b'change', 0, callback, None)
            p.expect(bool(listener), 'change listener')
            armed.update(query=query, listener=listener, callback=callback)

        def disarm():
            p.expect(remove_listener(armed['listener']) == OK, 'change listener removal')
            target_release(armed['query'])
            armed.clear()

        def take():
            events = list(log)
            log.clear()
            if any(item['source'].startswith('media:') for item in events):
                disarm()
                arm()
            return events

        arm()
        steps = {
            'resize 400x300': lambda: resize(p.host, 400, 300),
            'scroll 0,100': lambda: scroll_to(p.host, 0, 100),
            'scale 1.25': lambda: set_scale(p.host, 1.25),
            'resize 401x300 at 1.25': lambda: resize(p.host, 401, 300),
            'resize 401x301 and scale 1.5': lambda: (resize(p.host, 401, 301), set_scale(p.host, 1.5)),
            'blur': lambda: set_focused(p.host, 0),
            'focus': lambda: set_focused(p.host, 1),
        }
        for step in oracle['steps']:
            steps[step['name']]()
            settle()
            events = take()
            native = [item['source'] + ':' + item['type'] for item in events]
            chromium = [item['source'] + ':' + item['type'] for item in step['events']]
            report['steps'].append({'name': step['name'], 'native': events, 'chromium': step['events']})
            if step['name'] == 'scale 1.25':
                # Chromium's device-metrics emulation defers the media query report to the next resize.
                p.expect(native == ['media:(resolution: 1dppx):change'], 'scale-only change reports at once: ' + str(native))
                report['differences'].append({'step': step['name'], 'native': native, 'chromium': chromium})
            elif step['name'] == 'resize 401x300 at 1.25':
                p.expect(native == ['window:resize'], 'resize after the scale report: ' + str(native))
                report['differences'].append({'step': step['name'], 'native': native, 'chromium': chromium})
            else:
                p.expect(native == chromium, step['name'] + ' order ' + str(native) + ' vs ' + str(chromium))
                p.expect([item['target'] for item in events] == [item['target'] for item in step['events']], step['name'] + ' targets')
            for item, expected in zip(events, step['events']):
                p.expect(item['innerWidth'] == expected['innerWidth'] and math.isclose(item['devicePixelRatio'], expected['devicePixelRatio']), step['name'] + ' values in ' + item['type'])

        # One rendering update: resize, then scroll, then the media query report.
        resize(p.host, 360, 280)
        scroll_to(p.host, 0, 50)
        set_scale(p.host, 2.0)
        p.update()
        events = take()
        combined = [item['source'] + ':' + item['type'] for item in events]
        # An instant scroll ends in the scroll steps that report it.
        p.expect(combined == ['window:resize', 'window:scroll', 'window:scrollend', 'media:(resolution: 1.5dppx):change'], 'update order ' + str(combined))
        settle()
        p.expect(take() == [], 'nothing after the update')
        report['steps'].append({'name': 'one update: resize, scroll, scale 2', 'native': combined})

        # Visibility: queued visibilitychange, and resize deferred while hidden.
        p.expect(set_visible(p.host, 0) == OK, 'hide')
        settle()
        hidden = take()
        p.expect([item['type'] for item in hidden] == ['visibilitychange'] and hidden[0]['visibilityState'] == HIDDEN and hidden[0]['target'] == 'document', 'hidden ' + str(hidden))
        resize(p.host, 300, 200)
        settle()
        p.expect(take() == [], 'resize deferred while hidden')
        p.expect(set_visible(p.host, 0) == OK, 'hide twice')
        settle()
        p.expect(take() == [], 'no change, no event')
        p.expect(set_visible(p.host, 1) == OK, 'show')
        settle()
        shown = take()
        p.expect([item['type'] for item in shown] == ['visibilitychange', 'resize'] and shown[0]['visibilityState'] == VISIBLE, 'shown ' + str(shown))
        report['steps'].append({'name': 'hide, resize, show', 'native': hidden + shown})

        # Removal stops delivery.
        for listener in listeners:
            p.expect(remove_listener(listener) == OK, 'listener removal')
        disarm()
        resize(p.host, 320, 240)
        scroll_to(p.host, 0, 0)
        set_scale(p.host, 1.0)
        set_focused(p.host, 0)
        set_visible(p.host, 0)
        settle()
        p.expect(log == [], 'no delivery after removal ' + str(log))
        set_visible(p.host, 1)
        set_focused(p.host, 1)

        # Errors.
        value = WindowMetrics(size=ctypes.sizeof(WindowMetrics))
        p.expect(metrics(None, ctypes.byref(value)) == NULL_ARGUMENT and metrics(p.host, None) == NULL_ARGUMENT, 'metrics null')
        small = WindowMetrics(size=8)
        p.expect(metrics(p.host, ctypes.byref(small)) == UNSUPPORTED, 'metrics size check')
        p.expect(set_visible(None, 1) == NULL_ARGUMENT, 'visible null')
        p.expect(not match_media(None, b'(color)') and not match_media(p.host, None), 'match_media null')
        matches = I()
        p.expect(query_matches(None, ctypes.byref(matches)) == NULL_ARGUMENT, 'matches null')
        p.expect(query_matches(window, ctypes.byref(matches)) == WRONG_INTERFACE, 'window is not a media query list')
        length = I()
        p.expect(query_media(window, None, 0, ctypes.byref(length)) == WRONG_INTERFACE, 'media of a window')
        invalid = match_media(p.host, b'not a (valid query')
        p.expect(bool(invalid) and query_matches(invalid, ctypes.byref(matches)) == OK and matches.value == 0, 'invalid query is not all')
        buffer = ctypes.create_string_buffer(64)
        p.expect(query_media(invalid, buffer, len(buffer), ctypes.byref(length)) == OK and buffer.raw[:length.value] == b'not all', 'invalid query serializes as not all')
        target_release(invalid)
        thread_results = []

        def off_thread():
            value = WindowMetrics(size=ctypes.sizeof(WindowMetrics))
            thread_results.append((metrics(p.host, ctypes.byref(value)), set_visible(p.host, 1), bool(match_media(p.host, b'(color)')), bool(window_target(p.host))))

        worker = threading.Thread(target=off_thread)
        worker.start()
        worker.join()
        p.expect(thread_results == [(WRONG_THREAD, WRONG_THREAD, False, False)], 'wrong thread ' + str(thread_results))

        # Handles held past destroy.
        held_query = match_media(p.host, b'(min-width: 100px)')
        held_listener = add_listener(window, b'resize', 0, window_callback, None)
        held_change = add_listener(held_query, b'change', 0, window_callback, None)
        node_release(page_document)
        p.dispose_host()
        p.expect(query_matches(held_query, ctypes.byref(matches)) in (OK, UNSUPPORTED), 'query after destroy')
        p.expect(remove_listener(held_listener) == OK and remove_listener(held_change) == OK, 'removal after destroy')
        target_release(held_query)
        target_release(window)
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
    print(f'PASS viewport_events: {assertions} assertions', flush=True)
