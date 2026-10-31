"""Native side of the caret hit-testing fixture tests/fixtures/caret-hit.html: loads it with the pinned Ahem font,
attaches the open and closed shadow roots the Chromium oracle attaches, and describes nodes by the oracle's paths."""
import base64
import ctypes
import hashlib
import math
from pathlib import Path
import time
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8

AHEM_SHA256 = '63d2abd0041c3e3b4b52ad8d382353b53c51c6785e76ce56ed9dacad2d2e31c4'
FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'


class RootNodeOptions(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('composed', ctypes.c_int32)]


class ShadowRootInit(ctypes.Structure):
    _fields_ = [('size', ctypes.c_uint32), ('mode', ctypes.c_int32), ('delegates_focus', ctypes.c_int32),
                ('clonable', ctypes.c_int32), ('serializable', ctypes.c_int32), ('slot_assignment', ctypes.c_int32)]


def coordinate(value):
    return float(value) if isinstance(value, str) else value


def page(webkit_source):
    font = (Path(webkit_source) / 'Tools/TestWebKitAPI/Resources/cocoa/Ahem.ttf').read_bytes()
    assert hashlib.sha256(font).hexdigest() == AHEM_SHA256, 'pinned Ahem fixture identity'
    return (FIXTURES / 'caret-hit.html').read_text().replace('{{FONT_BASE64}}', base64.b64encode(font).decode())


class CaretPage:
    """The loaded fixture in an SvgProbe host. Handles it creates are released by the probe's release_all."""

    def __init__(self, p, webkit_source, scale):
        self.p = p
        P, I = p.pointer, p.integer
        p.call('rv_host_set_device_scale', [P, ctypes.c_float], p.host, scale)
        p.load(page(webkit_source), standalone=False)
        self.document = p.bind('rv_host_document', P, [P])(p.host)
        self.cycle = p.bind('rv_run_loop_cycle', I, [I])
        self.same = p.bind('rv_dom_node_is_same_node', I, [P, P, ctypes.POINTER(I)])
        self.scroll_to = p.bind('rv_dom_window_scroll_to_2', I, [P, ctypes.c_double, ctypes.c_double])
        self.roots = {}
        for host, mode, markup in [('host', 2, b'<span id="s">SSSS</span>'), ('closed', 1, b'<span id="t">TTTT</span>')]:
            init = ShadowRootInit(size=ctypes.sizeof(ShadowRootInit), mode=mode)
            root = p.object('rv_dom_element_attach_shadow', [P, ctypes.POINTER(ShadowRootInit)], [p.node(host), ctypes.byref(init)], 'node')
            p.call('rv_dom_shadow_root_set_inner_html', [P, Utf8], root, markup)
            self.roots['open' if mode == 2 else 'closed'] = root
        deadline = time.monotonic() + 10
        while self.width('inline') != 160:
            if time.monotonic() > deadline:
                raise AssertionError('pinned Ahem was not applied: inline width ' + str(self.width('inline')))
            self.cycle(10)
            p.update()
        p.update()

    def width(self, identifier):
        p = self.p
        rect = p.object('rv_dom_element_get_bounding_client_rect', [p.pointer], [p.node(identifier)], 'dom_rect_read_only')
        return p.read('dom_rect_read_only', rect, 'width', p.double)

    def settle(self):
        for _ in range(3):
            self.p.update()
            self.cycle(10)
        self.p.update()

    def scroll(self, x, y):
        self.p.expect(self.scroll_to(self.document, x, y) == 0, 'scrollTo')
        self.settle()
        return self.p.read('window', self.document, 'scroll_x', self.p.double), self.p.read('window', self.document, 'scroll_y', self.p.double)

    def is_same(self, a, b):
        result = self.p.integer()
        self.p.expect(self.same(a, b, ctypes.byref(result)) == 0, 'isSameNode')
        return bool(result.value)

    def relative(self, name, target):
        return self.p.object('rv_dom_node_get_' + name, [self.p.pointer], [target], 'node', nullable=True)

    def describe(self, node):
        """The oracle's description of a node: a text node by its parent and child index, an element by id and name."""
        if not node:
            return None
        p = self.p
        options = RootNodeOptions(size=ctypes.sizeof(RootNodeOptions), composed=0)
        root = p.object('rv_dom_node_get_root_node', [p.pointer, ctypes.POINTER(RootNodeOptions)], [node, ctypes.byref(options)], 'node')
        scope = next((name for name, value in [('document', self.document)] + list(self.roots.items()) if self.is_same(root, value)),
                     p.text('rv_dom_node_get_node_name', [p.pointer], root))
        kind = p.read('node', node, 'node_type', p.short)
        if kind == 3:
            parent = self.relative('parent_node', node)
            index, sibling = 0, self.relative('previous_sibling', node)
            while sibling:
                index, sibling = index + 1, self.relative('previous_sibling', sibling)
            return {'kind': 'text', 'parent': p.text('rv_dom_element_get_id', [p.pointer], parent) or p.text('rv_dom_node_get_node_name', [p.pointer], parent),
                    'index': index, 'scope': scope}
        name = p.text('rv_dom_node_get_node_name', [p.pointer], node)
        identifier = p.text('rv_dom_element_get_id', [p.pointer], node) if kind == 1 else None
        return {'kind': 'element' if kind == 1 else name, 'id': identifier or None, 'name': name, 'scope': scope}

    def rect(self, rect):
        if not rect:
            return None
        return {field: self.p.read('dom_rect_read_only', rect, field, self.p.double) for field in ['x', 'y', 'width', 'height']}


def same_rect(native, chromium, tolerance=0.0):
    if native is None or chromium is None:
        return native is chromium
    return all(math.isclose(native[k], chromium[k], abs_tol=tolerance) for k in ['x', 'y', 'width', 'height'])
