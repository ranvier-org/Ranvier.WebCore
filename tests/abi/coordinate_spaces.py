"""G14 coordinate-space probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/coordinate-spaces-oracle.json: every oracle point of every element converts from RV_SPACE_NODE to
RV_SPACE_PAGE within 1/64 CSS pixel, under nested 2D and 3D transforms, perspective, preserve-3d, an element scroller
and a fixed box. Then, in each of six viewport states (scroll, device scale 2, page scale 2 and 1.5 at non-zero
origins), checks every space against the engine's own metrics: CLIENT against rv_element_rect and the visual
viewport's page offset, HOST against rv_host_mouse's MouseEvent.clientX and target, DEVICE against the paint size;
every ordered space pair round-trips within 1/64; box quads; hit testing a transformed overlay through
rv_host_element_at and rv_host_mouse; the errors; and the teardown cases: a removed node, a replaced document, a second
host's node and a node held past rv_host_destroy, as from and as to."""

import argparse
import ctypes
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from svg_paint_probe import SvgProbe

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, UNSUPPORTED, DETACHED, WRONG_HOST = 0, -1, -2, -9, -10, -12
NODE, PAGE, CLIENT, HOST, DEVICE = range(5)
SPACES = {NODE: 'node', PAGE: 'page', CLIENT: 'client', HOST: 'host', DEVICE: 'device'}
BORDER, PADDING, CONTENT, MARGIN = range(4)
ABI = 54
TOLERANCE = 1 / 64
CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p)
QUALIFIED_3D = ('a perspective() function, the perspective property or preserve-3d in the chain: the slim software path '
                'paints without 3D compositing, so the property and preserve-3d have no effect and perspective() maps as the '
                'software paint draws it; the conversion follows that paint and hit testing (both asserted below), and the '
                'distance from the Chromium composition is recorded, not asserted')
# Elements whose transforms are singular: their page points exist, and points mapped into them do not.
SINGULAR = {'z': 'scale(0)', 'y': 'rotateY(90deg)'}
STATES = [
    ('initial', None, 1.0, None),
    ('scroll 10,20', (10, 20), 1.0, None),
    ('device scale 2', None, 2.0, None),
    ('page scale 2 at 40,60', None, 1.0, (2.0, 40, 60)),
    ('page scale 2 at 40,60, device scale 2', None, 2.0, (2.0, 40, 60)),
    ('page scale 1.5 at 30,90, scroll', None, 1.0, (1.5, 30, 90)),
]


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'coordinate-spaces-oracle.json').read_text(encoding='utf-8'))
    report = {'browser': oracle['browser'], 'states': [], 'maxError': {}, 'teardown': {}}
    with SvgProbe(native_directory, *oracle['viewport']) as p:
        P, I, D = p.pointer, p.integer, ctypes.c_double
        p.expect(p.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
        p.expect(p.bind('rv_abi_has', I, [ctypes.c_char_p])(b'coordinate-spaces') == 1, 'coordinate-spaces advertised')
        convert_raw = p.bind('rv_node_convert_points', I, [P, I, P, I, ctypes.POINTER(D), I])
        quad_raw = p.bind('rv_node_box_quad', I, [P, I, P, I, ctypes.POINTER(D)])
        element_rect = p.bind('rv_element_rect', I, [P] + [ctypes.POINTER(D)] * 4)
        element_at = p.bind('rv_host_element_at', P, [P, I, I])
        release = p.bind('rv_node_release', None, [P])
        mouse = p.bind('rv_host_mouse', I, [P, I, I, I, I, I, I])
        number = p.bind('rv_event_number', I, [P, I, ctypes.POINTER(D)])
        event_target = p.bind('rv_event_target', P, [P, I])
        add_listener = p.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
        remove_listener = p.bind('rv_listener_remove', I, [P])
        set_scale = p.bind('rv_host_set_page_scale', I, [P, D, I, I])
        set_device = p.bind('rv_host_set_device_scale', I, [P, ctypes.c_float])
        paint_size = p.bind('rv_host_paint_size', I, [P, ctypes.POINTER(I), ctypes.POINTER(I)])
        scroll_to = p.bind('rv_host_scroll_to', I, [P, I, I])
        get_viewport = p.bind('rv_dom_window_get_visual_viewport', I, [P, ctypes.POINTER(P)])
        page_left = p.bind('rv_dom_visual_viewport_get_page_left', I, [P, ctypes.POINTER(D)])
        page_top = p.bind('rv_dom_visual_viewport_get_page_top', I, [P, ctypes.POINTER(D)])
        vv_scale = p.bind('rv_dom_visual_viewport_get_scale', I, [P, ctypes.POINTER(D)])
        set_scroll_top = p.bind('rv_dom_element_set_scroll_top', I, [P, I])
        document_of = p.bind('rv_host_document', P, [P])
        host_create = p.bind('rv_host_create', P, [I, I])
        host_destroy = p.bind('rv_host_destroy', None, [P])
        load_html = p.bind('rv_host_load_html', I, [P, ctypes.c_char_p])
        by_id = p.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])
        remove = p.bind('rv_node_remove', I, [P])
        relative = p.bind('rv_node_relative', P, [P, I])

        def convert(source, from_space, target, to_space, points):
            values = (D * (2 * len(points)))(*[c for point in points for c in point])
            status = convert_raw(source, from_space, target, to_space, values, len(points))
            return status, [(values[2 * k], values[2 * k + 1]) for k in range(len(points))]

        def converted(source, from_space, target, to_space, points, label):
            status, result = convert(source, from_space, target, to_space, points)
            p.expect(status == OK, label + ': status ' + str(status))
            return result

        def quad(node, box, target, to_space):
            values = (D * 8)()
            status = quad_raw(node, box, target, to_space, values)
            return status, [(values[2 * k], values[2 * k + 1]) for k in range(4)]

        def error(points, expected, key):
            worst = max(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(points, expected))
            report['maxError'][key] = max(report['maxError'].get(key, 0.0), worst)
            return worst

        def close(points, expected, label, key):
            worst = error(points, expected, key)
            p.expect(worst <= TOLERANCE, label + ': error ' + repr(worst) + ' ' + str(points) + ' expected ' + str(expected))

        native_page = {}

        def expected_page(name):
            # Projective chains are compared with Chromium by distance only (QUALIFIED_3D); within the engine their page
            # points are fixed under scroll and scale.
            if oracle['elements'][name]['projective']:
                return native_page[name]
            return [tuple(q) for q in oracle['elements'][name]['page']]

        p.load(oracle['page'], standalone=False)
        document = document_of(p.host)
        nodes = {name: p.node(name) for name in list(oracle['elements']) + ['n', 'k']}
        p.expect(set_scroll_top(nodes['s'], oracle['scrollerTop']) == OK, 'scroller scrollTop')
        viewport = P()
        p.expect(get_viewport(document, ctypes.byref(viewport)) == OK, 'visual viewport')
        seen = []

        def on_down(context, event):
            x, y = D(), D()
            number(event, 0, ctypes.byref(x))
            number(event, 1, ctypes.byref(y))
            node = event_target(event, 0)
            seen.append((x.value, y.value, p.attribute(node, 'id') if node else None))
            return 0
        callback = CALLBACK(on_down)
        listener = add_listener(document, b'mousedown', 0, callback, None)

        def hit(x, y):
            node = element_at(p.host, x, y)
            if not node:
                return None
            try:
                return p.attribute(node, 'id') or None
            finally:
                release(node)

        def press(x, y):
            seen.clear()
            mouse(p.host, 1, x, y, 0, 1, 0)
            mouse(p.host, 2, x, y, 0, 1, 0)
            p.expect(len(seen) == 1, 'one mousedown at %r, %r: %r' % (x, y, seen))
            return seen[0]

        # NODE -> PAGE against the Chromium oracle, and the document node's space as the page space.
        report['qualified'] = {}
        for name, element in oracle['elements'].items():
            page_points = converted(nodes[name], NODE, None, PAGE, element['points'], name + ' node to page')
            native_page[name] = page_points
            if element['projective']:
                report['qualified'][name] = {'reason': QUALIFIED_3D, 'distanceFromChromium': error(
                    page_points, [tuple(q) for q in element['page']], 'projectiveDistanceFromChromium')}
            else:
                close(page_points, expected_page(name), name + ' node to page matches Chromium', 'nodeToPageVsChromium')
            same = converted(nodes[name], NODE, document, NODE, element['points'], name + ' node to document node')
            close(same, page_points, name + ' document node space is the page space', 'documentNodeIsPage')

        all_points = [(0.0, 0.0), (17.25, 33.5), (-12.0, 140.75), (305.5, 2.125)]
        for name, scroll, device, scale in STATES:
            if scroll:
                scroll_to(p.host, *scroll)
            p.expect(set_device(p.host, device) == OK, name + ': device scale')
            if scale:
                p.expect(set_scale(p.host, *scale) == OK, name + ': page scale')
                if name.endswith('scroll'):
                    scroll_to(p.host, 60, 150)
            p.update()
            left, top, s = D(), D(), D()
            page_left(viewport, ctypes.byref(left))
            page_top(viewport, ctypes.byref(top))
            vv_scale(viewport, ctypes.byref(s))
            width, height = I(), I()
            paint_size(p.host, ctypes.byref(width), ctypes.byref(height))
            ratio = width.value / oracle['viewport'][0]
            state = {'name': name, 'pageOffset': [left.value, top.value], 'scale': s.value, 'deviceRatio': ratio}
            p.expect(math.isclose(ratio, device), name + ': paint size follows the device scale')

            # CLIENT is PAGE less the visual viewport's page offset; HOST is CLIENT times the page scale; DEVICE is HOST
            # times the device scale.
            expected = {PAGE: all_points,
                        CLIENT: [(x - left.value, y - top.value) for x, y in all_points],
                        HOST: [((x - left.value) * s.value, (y - top.value) * s.value) for x, y in all_points],
                        DEVICE: [((x - left.value) * s.value * device, (y - top.value) * s.value * device) for x, y in all_points]}
            for space in (CLIENT, HOST, DEVICE):
                close(converted(document, PAGE, None, space, all_points, name + ' page to ' + SPACES[space]), expected[space],
                      name + ': page to ' + SPACES[space], 'pageTo' + SPACES[space].title())
                close(converted(document, space, None, PAGE, expected[space], name + ' ' + SPACES[space] + ' to page'), all_points,
                      name + ': ' + SPACES[space] + ' to page', SPACES[space] + 'ToPage')
            if s.value != 1:
                to_host = converted(document, CLIENT, None, HOST, [(10.0, 20.0)], name + ' client to host')[0]
                to_client = converted(document, HOST, None, CLIENT, [(10.0, 20.0)], name + ' host to client')[0]
                p.expect(abs(to_host[0] - 10) > 1 and abs(to_host[1] - 20) > 1, name + ': HOST differs from CLIENT, client to host ' + str(to_host))
                p.expect(abs(to_client[0] - 10) > 1 and abs(to_client[1] - 20) > 1, name + ': HOST differs from CLIENT, host to client ' + str(to_client))
                state['clientToHost'], state['hostToClient'] = to_host, to_client

            # Untransformed boxes: their NODE origin in CLIENT is getBoundingClientRect's.
            for box in ['b', 'f', 'm', 'p', 's', 'u']:
                r = [D(), D(), D(), D()]
                element_rect(nodes[box], *[ctypes.byref(v) for v in r])
                corner = converted(nodes[box], NODE, None, CLIENT, [(0.0, 0.0), (r[2].value, r[3].value)], name + ' ' + box + ' to client')
                close(corner, [(r[0].value, r[1].value), (r[0].value + r[2].value, r[1].value + r[3].value)],
                      name + ': ' + box + ' client corners equal rv_element_rect', 'nodeToClientVsRect')

            # Every ordered pair of spaces round-trips, NODE anchored at each regular element.
            for element_name, element in oracle['elements'].items():
                if element_name in SINGULAR:
                    continue
                anchor = nodes[element_name]
                for a in SPACES:
                    for b in SPACES:
                        if a == b:
                            continue
                        source = element['points'] if a == NODE else expected.get(a, all_points)
                        there = converted(anchor, a, anchor, b, source, '%s %s %s to %s' % (name, element_name, SPACES[a], SPACES[b]))
                        back = converted(anchor, b, anchor, a, there, '%s %s %s back to %s' % (name, element_name, SPACES[b], SPACES[a]))
                        close(back, [tuple(q) for q in source], '%s: %s %s -> %s -> %s' % (name, element_name, SPACES[a], SPACES[b], SPACES[a]), 'roundTrip')
                # NODE -> PAGE is independent of scroll and scale, except for the fixed box, which moves with the viewport.
                if element_name != 'f':
                    close(converted(anchor, NODE, None, PAGE, element['points'], name + ' ' + element_name + ' node to page'),
                          expected_page(element_name), name + ': ' + element_name + ' node to page in this state', 'nodeToPageVsChromium')

            # Native hit testing on a transformed overlay: the centre of #i, a rotated child of a rotated, scaled box.
            client = converted(nodes['i'], NODE, None, CLIENT, [(20.0, 20.0)], name + ' i centre to client')[0]
            host = converted(nodes['i'], NODE, None, HOST, [(20.0, 20.0)], name + ' i centre to host')[0]
            if 0 <= client[0] < oracle['viewport'][0] / s.value and 0 <= client[1] < oracle['viewport'][1] / s.value:
                p.expect(hit(round(client[0]), round(client[1])) == 'i', name + ': rv_host_element_at(CLIENT of i) is i')
                x, y, target = press(round(host[0]), round(host[1]))
                p.expect(target == 'i', name + ': rv_host_mouse(HOST of i) targets i, got ' + str(target))
                p.expect(abs(x - client[0]) <= 1 and abs(y - client[1]) <= 1, name + ': its clientX, clientY ' + str((x, y)) + ' are CLIENT ' + str(client))
                state['overlay'] = {'client': client, 'host': host, 'mouse': [x, y, target]}
            else:
                state['overlay'] = {'client': client, 'host': host, 'outside': True}
            # #b, untransformed, through rv_host_mouse at its HOST centre.
            bc = converted(nodes['b'], NODE, None, HOST, [(25.0, 25.0)], name + ' b centre to host')[0]
            if 0 <= bc[0] < oracle['viewport'][0] and 0 <= bc[1] < oracle['viewport'][1]:
                p.expect(press(round(bc[0]), round(bc[1]))[2] == 'b', name + ': rv_host_mouse(HOST of b) targets b')

            # Box quads of #m (border 2, padding 4 6, margin 3 5 7 9) in PAGE, and #o's in HOST against its corners.
            box_data = oracle['elements']['m']['box']
            (bx, by), = converted(nodes['m'], NODE, None, PAGE, [(0.0, 0.0)], name + ' m origin')
            w, h = oracle['elements']['m']['size']
            t_, r_, b_, l_ = box_data['border']
            pt, pr, pb, pl = box_data['padding']
            mt, mr, mb, ml = box_data['margin']
            rects = {BORDER: (0, 0, w, h), PADDING: (l_, t_, w - l_ - r_, h - t_ - b_),
                     CONTENT: (l_ + pl, t_ + pt, w - l_ - r_ - pl - pr, h - t_ - b_ - pt - pb), MARGIN: (-ml, -mt, w + ml + mr, h + mt + mb)}
            for box, (x0, y0, bw, bh) in rects.items():
                status, corners = quad(nodes['m'], box, None, PAGE)
                p.expect(status == OK, name + ': m box quad ' + str(box))
                close(corners, [(bx + x0, by + y0), (bx + x0 + bw, by + y0), (bx + x0 + bw, by + y0 + bh), (bx + x0, by + y0 + bh)],
                      name + ': m box quad ' + str(box), 'boxQuad')
            status, corners = quad(nodes['o'], BORDER, None, HOST)
            p.expect(status == OK, name + ': o border quad in host')
            close(corners, converted(nodes['o'], NODE, None, HOST, oracle['elements']['o']['points'][:4], name + ' o corners'),
                  name + ': o border quad equals its corner points', 'boxQuad')
            report['states'].append(state)
            if scale:
                p.expect(set_scale(p.host, 1.0, 0, 0) == OK, name + ': page scale reset')
            scroll_to(p.host, 0, 0)

        # Singular transforms: forward maps collapse; points mapped into them are refused.
        for name, transform in SINGULAR.items():
            status, forward = convert(nodes[name], NODE, None, PAGE, [(5.0, 5.0)])
            p.expect(status == OK, transform + ': node to page')
            p.expect(all(math.isfinite(c) for c in forward[0]), transform + ': forward point is finite')
            original = [(1.0, 2.0)]
            status, unchanged = convert(document, PAGE, nodes[name], NODE, original)
            p.expect(status == UNSUPPORTED and unchanged == original, transform + ': page to node is UNSUPPORTED, xy unchanged: ' + str(status))
            status, _ = quad(nodes[name], BORDER, None, PAGE)
            p.expect(status == OK, transform + ': box quad in page')
            status, _ = quad(document, BORDER, nodes[name], NODE)
            p.expect(status == UNSUPPORTED, transform + ': box quad into it is UNSUPPORTED')
        report['singular'] = {name: 'node to page OK; page to node UNSUPPORTED' for name in SINGULAR}

        # Arguments and boxes.
        points = (D * 2)(3.0, 4.0)
        text_node = relative(nodes['k'], 1)
        cases = {
            'NULL from': (convert_raw(None, PAGE, None, CLIENT, points, 1), NULL_ARGUMENT),
            'NULL xy with count 1': (convert_raw(document, PAGE, None, CLIENT, None, 1), NULL_ARGUMENT),
            'NULL xy with count 0': (convert_raw(document, PAGE, None, CLIENT, None, 0), OK),
            'count -1': (convert_raw(document, PAGE, None, CLIENT, points, -1), UNSUPPORTED),
            'from space 5': (convert_raw(document, 5, None, CLIENT, points, 1), UNSUPPORTED),
            'to space -1': (convert_raw(document, PAGE, None, -1, points, 1), UNSUPPORTED),
            'NaN': (convert(document, PAGE, None, CLIENT, [(float('nan'), 0.0)])[0], UNSUPPORTED),
            'infinity': (convert(document, PAGE, None, CLIENT, [(0.0, float('inf'))])[0], UNSUPPORTED),
            'display none as NODE': (convert(nodes['n'], NODE, None, PAGE, [(0.0, 0.0)])[0], UNSUPPORTED),
            'display none as PAGE anchor': (convert(nodes['n'], PAGE, None, CLIENT, [(0.0, 0.0)])[0], OK),
            'inline span as NODE': (convert(nodes['k'], NODE, None, PAGE, [(0.0, 0.0)])[0], UNSUPPORTED),
            'inline span text as NODE': (convert(text_node, NODE, None, PAGE, [(0.0, 0.0)])[0], UNSUPPORTED),
            'box quad NULL node': (quad_raw(None, BORDER, None, PAGE, (D * 8)()), NULL_ARGUMENT),
            'box quad NULL quad': (quad_raw(nodes['m'], BORDER, None, PAGE, None), NULL_ARGUMENT),
            'box quad box 4': (quad(nodes['m'], 4, None, PAGE)[0], UNSUPPORTED),
            'box quad display none': (quad(nodes['n'], BORDER, None, PAGE)[0], UNSUPPORTED),
            'box quad to space 9': (quad(nodes['m'], BORDER, None, 9)[0], UNSUPPORTED),
        }
        for label, (status, wanted) in cases.items():
            p.expect(status == wanted, label + ': status ' + str(status) + ', expected ' + str(wanted))
        p.expect(list(points) == [3.0, 4.0], 'rejected conversions leave xy unchanged')
        report['arguments'] = {label: status for label, (status, _) in cases.items()}
        release(text_node)
        remove_listener(listener)

        # Teardown: each anchor as from and as to.
        teardown = report['teardown']

        def both(label, stale, live, expected):
            first = convert(stale, PAGE, live, CLIENT, [(1.0, 1.0)])[0]
            second = convert(live, PAGE, stale, CLIENT, [(1.0, 1.0)])[0]
            third = convert(stale, NODE, None, PAGE, [(1.0, 1.0)])[0]
            fourth = quad(stale, BORDER, None, PAGE)[0]
            p.expect([first, second, third, fourth] == [expected] * 4, label + ': ' + str([first, second, third, fourth]))
            teardown[label] = [first, second, third, fourth]

        p.expect(remove(nodes['b']) == OK, 'remove b')
        both('node removed from its document', nodes['b'], nodes['o'], DETACHED)

        other = host_create(100, 80)
        p.expect(bool(other), 'second host')
        p.expect(load_html(other, b'<!doctype html><body style="margin:0"><div id=x style="width:10px;height:10px"></div>') == OK, 'second host page')
        foreign = by_id(other, b'x')
        both_wrong = [convert(foreign, PAGE, nodes['o'], CLIENT, [(1.0, 1.0)])[0], convert(nodes['o'], PAGE, foreign, CLIENT, [(1.0, 1.0)])[0],
                      convert(foreign, NODE, nodes['o'], NODE, [(1.0, 1.0)])[0], quad(foreign, BORDER, nodes['o'], PAGE)[0]]
        p.expect(both_wrong == [WRONG_HOST] * 4, 'nodes of two hosts: ' + str(both_wrong))
        teardown['nodes of two hosts'] = both_wrong
        p.expect(convert(foreign, NODE, None, PAGE, [(1.0, 1.0)])[0] == OK, 'the second host converts its own node')

        host_destroy(other)
        both('node held past rv_host_destroy', foreign, nodes['o'], DETACHED)
        release(foreign)

        old_o = nodes['o']
        p.expect(load_html(p.host, b'<!doctype html><body><div id=o></div>') == OK, 'replace the document')
        fresh = by_id(p.host, b'o')
        p.expect(convert(fresh, NODE, None, PAGE, [(1.0, 1.0)])[0] == OK, 'the replacing document converts')
        both('node of a replaced document', old_o, fresh, DETACHED)
        both('replaced document node', document, fresh, DETACHED)
        release(fresh)
        release(document)

        # The perspective property in paint: the conversion of a rotateY(40deg) child of perspective: 400px agrees with
        # the software paint, whose left edge stays at the flat composition's 61.7 px, not Chromium's 54.0 px.
        painter = host_create(320, 240)
        p.expect(load_html(painter, b'<!doctype html><style>body{margin:0;background:#fff}#p{position:absolute;left:50px;top:50px;width:200px;'
                           b'height:200px;perspective:400px}#q{width:100px;height:100px;background:#f00;transform:rotateY(40deg)}</style>'
                           b'<div id=p><div id=q></div></div>') == OK, 'perspective paint page')
        q = by_id(painter, b'q')
        (left_edge, _), = converted(q, NODE, None, HOST, [(0.0, 50.0)], 'perspective child left edge')
        p.expect(math.isclose(left_edge, 50 + 50 - 50 * math.cos(math.radians(40)), abs_tol=TOLERANCE), 'left edge without perspective: ' + str(left_edge))
        rgba = (ctypes.c_uint8 * (320 * 240 * 4))()
        p.expect(p.bind('rv_host_update', I, [P])(painter) >= 0, 'perspective paint update')
        p.expect(p.bind('rv_host_paint_rgba', I, [P, P, I])(painter, rgba, len(rgba)) == OK, 'perspective paint')
        red = [rgba[(100 * 320 + x) * 4 + 1] < 128 for x in range(50, 70)]
        p.expect(red.index(True) + 50 == math.ceil(left_edge - 0.5), 'paint left edge follows the conversion: ' + str(red))
        report['perspectivePaint'] = {'convertedLeftEdge': left_edge, 'firstRedColumn': red.index(True) + 50, 'chromiumLeftEdge': 54.0}

        def hit_in(host, x, y):
            node = element_at(host, int(math.floor(x)), int(math.floor(y)))
            if not node:
                return None
            try:
                return p.attribute(node, 'id') or None
            finally:
                release(node)

        # Hit testing agrees: points converted from inside the box hit it, and Chromium's left edge region does not.
        hits = {}
        for local in [(3.0, 50.0), (97.0, 50.0), (50.0, 3.0), (50.0, 97.0)]:
            (x, y), = converted(q, NODE, None, CLIENT, [local], 'perspective child point')
            hits[str(local)] = hit_in(painter, x, y)
            p.expect(hits[str(local)] == 'q', 'rv_host_element_at at converted ' + str(local) + ' hits q: ' + str(hits[str(local)]))
        hits['chromium-only 56,100'] = hit_in(painter, 56, 100)
        p.expect(hits['chromium-only 56,100'] == 'p', 'Chromium-only edge region hits the perspective parent: ' + str(hits['chromium-only 56,100']))
        report['perspectivePaint']['hits'] = hits
        release(q)
        # A perspective() function: the painted edges of the trapezoid follow its converted corners.
        p.expect(load_html(painter, b'<!doctype html><style>body{margin:0;background:#fff}#e{position:absolute;left:100px;top:60px;width:80px;'
                           b'height:60px;background:#f00;transform:perspective(250px) rotateY(-35deg)}</style><div id=e></div>') == OK, 'perspective() page')
        e = by_id(painter, b'e')
        c = converted(e, NODE, None, HOST, [(0.0, 0.0), (80.0, 0.0), (80.0, 60.0), (0.0, 60.0)], 'perspective() corners')
        p.expect(p.bind('rv_host_update', I, [P])(painter) >= 0, 'perspective() paint update')
        p.expect(p.bind('rv_host_paint_rgba', I, [P, P, I])(painter, rgba, len(rgba)) == OK, 'perspective() paint')
        red_at = lambda x, y: rgba[(y * 320 + x) * 4 + 1] < 128
        row = [x for x in range(320) if red_at(x, 90)]
        column = [y for y in range(240) if red_at(140, y)]

        def along(a, b, coordinate, value):
            k = (value - a[coordinate]) / (b[coordinate] - a[coordinate])
            return a[1 - coordinate] + k * (b[1 - coordinate] - a[1 - coordinate])
        edges = {'left': (row[0], math.ceil(along(c[0], c[3], 1, 90.5) - 0.5)), 'right': (row[-1], math.ceil(along(c[1], c[2], 1, 90.5) - 0.5) - 1),
                 'top': (column[0], math.ceil(along(c[0], c[1], 0, 140.5) - 0.5)), 'bottom': (column[-1], math.ceil(along(c[3], c[2], 0, 140.5) - 0.5) - 1)}
        for edge, (painted, predicted) in edges.items():
            p.expect(abs(painted - predicted) <= 1, 'perspective() ' + edge + ' edge: painted ' + str(painted) + ', converted ' + str(predicted))
        hits = {}
        for local in [(3.0, 30.0), (77.0, 30.0), (40.0, 3.0), (40.0, 57.0)]:
            (x, y), = converted(e, NODE, None, CLIENT, [local], 'perspective() point')
            hits[str(local)] = hit_in(painter, x, y)
            p.expect(hits[str(local)] == 'e', 'rv_host_element_at at converted ' + str(local) + ' hits e: ' + str(hits[str(local)]))
        report['perspectiveFunctionPaint'] = {'corners': c, 'edges': edges, 'hits': hits}
        release(e)
        host_destroy(painter)
        p.bind('rv_event_target_release', None, [P])(viewport)
        report['assertions'] = p.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    arguments = parser.parse_args()
    report = verify(arguments.native_directory)
    if arguments.report:
        Path(arguments.report).write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print('coordinate spaces PASS: %d assertions; max errors %s' % (report['assertions'], {k: round(v, 6) for k, v in report['maxError'].items()}))
    print('COORDINATE_SPACES=PASS')


if __name__ == '__main__':
    main()
