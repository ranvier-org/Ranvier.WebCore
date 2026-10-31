"""G04 screen probe against an actual runtime directory: rv_host_set_screen and the generated Screen and ScreenOrientation
getters. Checks the default screen (the host size, all of it available, 24 bits deep, landscape-primary unless taller
than wide, following rv_host_resize), screens set by the app, the orientation angle of each type on the natural
landscape orientation, the argument and thread errors, two hosts
with different screens, and a document kept past rv_host_destroy. With --report it writes the measured values."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, P, I

OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED = 0, -1, -2, -9
ABI = 54
PORTRAIT_PRIMARY, PORTRAIT_SECONDARY, LANDSCAPE_PRIMARY, LANDSCAPE_SECONDARY = 0, 1, 2, 3
TYPES = ['portrait-primary', 'portrait-secondary', 'landscape-primary', 'landscape-secondary']
ANGLES = {LANDSCAPE_PRIMARY: 0, PORTRAIT_PRIMARY: 90, LANDSCAPE_SECONDARY: 180, PORTRAIT_SECONDARY: 270}


class Metrics(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('width', I), ('height', I), ('avail_left', I), ('avail_top', I),
                ('avail_width', I), ('avail_height', I), ('color_depth', I), ('orientation', I)]


def metrics(width, height, left, top, avail_width, avail_height, depth, orientation, size=None):
    return Metrics(ctypes.sizeof(Metrics) if size is None else size, width, height, left, top, avail_width, avail_height, depth, orientation)


class Screen:
    def __init__(self, native):
        self.n = native
        self.set_screen = native.bind('rv_host_set_screen', I, [P, ctypes.POINTER(Metrics)])

    def read(self, document):
        n = self.n
        values = {}
        for name in ['width', 'height', 'avail_left', 'avail_top', 'avail_width', 'avail_height']:
            values[name] = n.integer('rv_dom_screen_get_' + name, document)
        for name in ['color_depth', 'pixel_depth']:
            values[name] = n.integer('rv_dom_screen_get_' + name, document, ctypes.c_uint32)
        kind = n.integer('rv_dom_screen_orientation_get_type', document)
        values['type'] = TYPES[kind]
        values['angle'] = n.integer('rv_dom_screen_orientation_get_angle', document, ctypes.c_uint16)
        return values


def expect_values(n, label, actual, expected):
    for key, value in expected.items():
        n.expect(actual[key] == value, f'{label}: {key} {actual[key]} != {value}')


def defaults(native, screen, report):
    n = native
    case = Case(n, '<p>x</p>')
    first = screen.read(case.document)
    expect_values(n, 'default', first, {'width': 320, 'height': 200, 'avail_left': 0, 'avail_top': 0, 'avail_width': 320,
                                        'avail_height': 200, 'color_depth': 24, 'pixel_depth': 24, 'type': 'landscape-primary', 'angle': 0})
    n.ok('rv_host_resize', [P, I, I], case.host, 300, 500)
    tall = screen.read(case.document)
    expect_values(n, 'default after resize', tall, {'width': 300, 'height': 500, 'avail_width': 300, 'avail_height': 500,
                                                    'type': 'portrait-primary', 'angle': 90})
    report['default'] = {'created': first, 'resized': tall}
    case.close()


def set_values(native, screen, oracle, report):
    n = native
    case = Case(n, '<p>x</p>')
    measured = {}
    for label, entry in oracle['cases'].items():
        given = entry['metrics']
        values = metrics(given['width'], given['height'], given['availLeft'], given['availTop'], given['availWidth'],
                         given['availHeight'], given['colorDepth'], TYPES.index(given['type']))
        n.ok('rv_host_set_screen', [P, ctypes.POINTER(Metrics)], case.host, ctypes.byref(values))
        actual = screen.read(case.document)
        expect_values(n, label, actual, {'width': given['width'], 'height': given['height'], 'avail_left': given['availLeft'],
                                         'avail_top': given['availTop'], 'avail_width': given['availWidth'],
                                         'avail_height': given['availHeight'], 'color_depth': given['colorDepth'],
                                         'pixel_depth': given['colorDepth'], 'type': given['type'],
                                         'angle': ANGLES[TYPES.index(given['type'])]})
        n.expect(actual['angle'] == entry['chromium']['angle'], f'{label}: angle agrees with Chromium')
        measured[label] = actual
    n.ok('rv_host_resize', [P, I, I], case.host, 640, 480)
    kept = screen.read(case.document)
    n.expect(kept == measured[list(measured)[-1]], 'a set screen does not follow rv_host_resize')
    report['set'] = measured
    case.close()


def errors(native, screen, report):
    n = native
    case = Case(n, '<p id=p>x</p>')
    good = metrics(800, 600, 0, 0, 800, 560, 24, LANDSCAPE_PRIMARY)
    n.expect(screen.set_screen(None, ctypes.byref(good)) == NULL_ARGUMENT, 'null host')
    n.expect(screen.set_screen(case.host, None) == NULL_ARGUMENT, 'null metrics')
    before = screen.read(case.document)
    for label, bad in [('small size', metrics(800, 600, 0, 0, 800, 560, 24, 2, size=8)), ('zero width', metrics(0, 600, 0, 0, 0, 600, 24, 2)),
                       ('negative avail', metrics(800, 600, 0, 0, -1, 600, 24, 2)), ('zero depth', metrics(800, 600, 0, 0, 800, 600, 0, 2)),
                       ('orientation 4', metrics(800, 600, 0, 0, 800, 600, 24, 4)), ('orientation -1', metrics(800, 600, 0, 0, 800, 600, 24, -1))]:
        n.expect(screen.set_screen(case.host, ctypes.byref(bad)) == UNSUPPORTED, label)
    n.expect(screen.read(case.document) == before, 'rejected metrics change nothing')
    paragraph = case.node('p')
    n.expect(n.call('rv_dom_screen_get_width', [P, ctypes.POINTER(I)], paragraph, ctypes.byref(I())) == -11, 'element target')
    n.expect(n.call('rv_dom_screen_get_width', [P, ctypes.POINTER(I)], case.document, None) == NULL_ARGUMENT, 'null result')
    outcome = {}

    def worker():
        outcome['set'] = screen.set_screen(case.host, ctypes.byref(good))
        outcome['get'] = n.call('rv_dom_screen_get_width', [P, ctypes.POINTER(I)], case.document, ctypes.byref(I()))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    n.expect(all(status == WRONG_THREAD for status in outcome.values()), f'wrong thread {outcome}')
    report['errors'] = 'checked'
    case.close()


def two_hosts(native, screen, report):
    n = native
    first, second = Case(n, '<p>a</p>'), Case(n, '<p>b</p>')
    n.ok('rv_host_set_screen', [P, ctypes.POINTER(Metrics)], first.host, ctypes.byref(metrics(1920, 1080, 0, 0, 1920, 1040, 24, LANDSCAPE_PRIMARY)))
    n.ok('rv_host_set_screen', [P, ctypes.POINTER(Metrics)], second.host, ctypes.byref(metrics(1080, 1920, 0, 40, 1080, 1880, 30, PORTRAIT_PRIMARY)))
    a, b = screen.read(first.document), screen.read(second.document)
    n.expect((a['width'], a['avail_height'], a['type']) == (1920, 1040, 'landscape-primary'), f'first host {a}')
    n.expect((b['width'], b['avail_top'], b['color_depth'], b['type']) == (1080, 40, 30, 'portrait-primary'), f'second host {b}')
    report['twoHosts'] = {'first': a, 'second': b}
    first.close()
    after = screen.read(second.document)
    n.expect(after == b, 'a destroyed host leaves another host screen unchanged')
    second.close()


def after_destroy(native, screen, report):
    n = native
    case = Case(n, '<p>x</p>')
    document = case.document
    n.bind('rv_node_retain', P, [P])(document)
    case.close()
    width = I(-1)
    status = n.call('rv_dom_screen_get_width', [P, ctypes.POINTER(I)], document, ctypes.byref(width))
    # The document has no frame after destroy, and WebKit's Screen reports 0 without one.
    n.expect(status == OK and width.value == 0, f'Screen.width after destroy {status} {width.value}')
    n.bind('rv_node_release', None, [P])(document)
    report['afterDestroy'] = status


def verify(native_directory):
    oracle = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/screen-oracle.json').read_text(encoding='utf-8'))
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for feature in ['screen', 'dom-screen', 'dom-screen-orientation']:
        native.expect(has(feature.encode()) == 1, feature + ' advertised')
    screen = Screen(native)
    report = {'browser': oracle['browser'], 'platform': sys.platform}
    defaults(native, screen, report)
    set_values(native, screen, oracle, report)
    errors(native, screen, report)
    two_hosts(native, screen, report)
    after_destroy(native, screen, report)
    report['assertions'] = native.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"PASS screen_metrics: {report['assertions']} assertions", flush=True)


if __name__ == '__main__':
    main()
