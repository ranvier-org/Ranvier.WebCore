"""Rendered default-mode regressions across compositing boundaries and HTML replacement."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'abi'))
from web_animations import Arena, I, OK, P, Page, Native, animate, computed, paint, seek


def color(native, page, expected, label):
    actual = paint(native, page)(20, 20)
    native.expect(all(abs(a - b) <= 2 for a, b in zip(actual, expected)),
                  label + ': expected ' + str(expected) + ', got ' + str(actual))


def animation_boundary(native):
    markup = '<style>html,body{margin:0;background:white}#a{width:40px;height:40px;background:blue}</style><div id=a></div>'
    page = Page(native, markup)
    try:
        color(native, page, [0, 0, 255], 'normal frame')
        element = page.element('a')
        for index, (end, fill, points) in enumerate([
                (1, 'both', [(0, [255, 255, 255]), (500, [127, 127, 255]), (1000, [0, 0, 255])]),
                (0.5, 'none', [(0, [255, 255, 255]), (500, [191, 191, 255])])]):
            arena = Arena()
            status, animation = animate(native, page, 'animate', element,
                                        [{'props': {'opacity': '0'}}, {'props': {'opacity': str(end)}}],
                                        {'duration': 1000, 'fill': fill}, arena)
            native.expect(status == OK and animation, 'animation created')
            try:
                native.ok('rv_dom_web_animation_pause', [P], animation)
                for time, expected in points:
                    seek(native, animation, time)
                    if index == 1 and time == 500:
                        native.expect(computed(native, element, 'opacity') == '0.25', 'second animation computed opacity')
                    color(native, page, expected, 'animation ' + str(index) + ' at ' + str(time))
            finally:
                native.ok('rv_dom_web_animation_cancel', [P], animation)
                native.bind('rv_event_target_release', None, [P])(animation)
    finally:
        page.close()


def html_replacement(native):
    markup = lambda value: '<style>html,body{margin:0;background:white}#a{width:40px;height:40px;transform:translateZ(0);background:' + value + '}</style><div id=a></div>'
    page = Page(native, markup('blue'))
    held = []
    try:
        page.element('a')
        color(native, page, [0, 0, 255], 'first composited document')
        for value, expected in [('red', [255, 0, 0]), ('lime', [0, 255, 0]), ('blue', [0, 0, 255])]:
            held.extend(page.elements.values())
            held.append(page.document)
            page.elements.clear()
            utf8 = markup(value).encode()
            native.ok('rv_host_load_html', [P, P, I], page.host, utf8, len(utf8))
            page.document = native.bind('rv_host_document', P, [P])(page.host)
            page.element('a')
            color(native, page, expected, 'reloaded composited document ' + value)
    finally:
        page.close()
        release = native.bind('rv_node_release', None, [P])
        for node in held:
            release(node)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--scenario', choices=['animation', 'reload'])
    args = parser.parse_args()
    native = Native(args.native_directory)
    if args.scenario != 'reload':
        animation_boundary(native)
    if args.scenario != 'animation':
        html_replacement(native)
    print(f'PASS default compositor reattachment: {native.assertions} assertions')


if __name__ == '__main__':
    main()
