"""Failed SVG images stay empty while the same failed HTML image keeps its icon."""
import argparse
import ctypes as C
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe
from svg_resources import Handler, IMAGES
from utf8_inputs import Utf8

PAGE = '''<style>html,body{margin:0;background:white}img{position:absolute;left:64px;top:8px;width:32px;height:32px}</style>
<svg xmlns="http://www.w3.org/2000/svg" width="128" height="64"><image id="svg" x="8" y="8" width="32" height="32"/></svg><img id="html">'''
EVENT = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p)


def verify(directory):
    with SvgProbe(directory, 128, 64) as p:
        P, I = p.pointer, p.integer
        p.call('rv_host_set_accelerated_compositing', [P, I], p.host, 0)
        held, callback_failures, events, callbacks, listeners = {}, [], [], [], []
        finish = p.bind('rv_resource_load_finish', I, [P, C.c_char_p, I, C.c_char_p])
        fail = p.bind('rv_resource_load_fail', I, [P])

        def serve(_, load, url):
            name = url.decode().rsplit('/', 1)[-1]
            if name.startswith('slow'):
                held[name] = load
                return
            status = finish(load, IMAGES[name], len(IMAGES[name]), b'image/png') if name in IMAGES else fail(load)
            if status != 0:
                callback_failures.append((name, status))

        handler = Handler(serve)
        p.call('rv_host_set_resource_handler', [P, Handler, P], p.host, handler, None)
        p.load(PAGE, standalone=False)
        svg, html = p.node('svg'), p.node('html')
        for node, label in [(svg, 'svg'), (html, 'html')]:
            for kind in ['load', 'error']:
                callback = EVENT(lambda _, event, text=label+'.'+kind: events.append(text) or 0)
                callbacks.append(callback)
                listener = p.bind('rv_node_add_event_listener', P, [P, Utf8, I, EVENT, P])(
                    node, kind.encode(), 0, callback, None)
                p.expect(bool(listener), 'image event listener')
                listeners.append(listener)
        samples = []
        painting_failures = []

        def set_url(node, value):
            p.call('rv_dom_element_set_attribute', [P, Utf8, Utf8], node,
                   b'href' if node == svg else b'src', ('https://fixture.test/'+value).encode())

        def settle(label):
            for _ in range(5):
                p.expect(p.bind('rv_run_loop_cycle', I, [I])(20) >= 0, 'image event cycle')
            rgba = p.paint()
            counts = [sum(p.pixel(rgba, x, y) != [255,255,255,255]
                          for y in range(10,38) for x in range(left+2,left+30)) for left in [8,64]]
            samples.append(dict(label=label, svg=p.pixel(rgba,20,20), html=p.pixel(rgba,76,20),
                                svg_inner_nonwhite=counts[0], html_inner_nonwhite=counts[1]))
            return samples[-1]

        try:
            set_url(svg, 'blue.png')
            set_url(html, 'blue.png')
            blue = settle('valid blue')
            p.expect(blue['svg'] == blue['html'] == [0,0,255,255], 'both valid images paint blue')
            p.expect(events.count('svg.load') == events.count('html.load') == 1, 'one load event per successful image')
            for index, name in enumerate(['missing.png', 'broken.png'], 1):
                set_url(svg, name)
                set_url(html, name)
                failed = settle(name)
                if failed['svg_inner_nonwhite'] != 0:
                    painting_failures.append(name+': SVG fallback painted '+str(failed['svg']))
                p.expect(failed['html_inner_nonwhite'] > 0, 'HTML broken-image icon remains visible: '+name)
                p.expect(events.count('svg.error') == events.count('html.error') == index,
                         'one error event per failed image generation: '+name)
            set_url(svg, 'slow-red.png')
            pending = settle('pending')
            p.expect('slow-red.png' in held, 'pending SVG resource is held')
            if pending['svg_inner_nonwhite'] != 0:
                painting_failures.append('pending SVG retained the failed-image fallback')
            set_url(svg, 'green.png')
            green = settle('valid replacement')
            p.expect(green['svg'] == [0,255,0,255], 'replacement SVG image paints green')
            loads = events.count('svg.load')
            stale = held.pop('slow-red.png')
            p.expect(finish(stale, IMAGES['red.png'], len(IMAGES['red.png']), b'image/png') == 0, 'stale resource completion accepted once')
            stale_sample = settle('stale completion')
            p.expect(stale_sample['svg'] == [0,255,0,255], 'stale completion cannot replace current SVG pixels')
            p.expect(events.count('svg.load') == loads and events.count('svg.error') == 2, 'stale completion changes no image event counts')
            p.expect(not held and not callback_failures, 'all resource callbacks complete successfully')
            result = dict(result='FAIL' if painting_failures else 'PASS', assertions=p.assertions,
                          samples=samples, events=events, painting_failures=painting_failures,
                          renderer='CPU paint', gpu_claim=False)
            print(json.dumps(result), flush=True)
            p.expect(not painting_failures, 'failed SVG images must not paint the HTML placeholder: '+repr(painting_failures))
            return result
        finally:
            for listener in listeners:
                p.bind('rv_listener_remove', None, [P])(listener)
            p.call('rv_host_set_resource_handler', [P, Handler, P], p.host, Handler(), None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
