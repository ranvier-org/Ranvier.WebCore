"""Shared harness of the pointer-input probes (touch_input.py, pen_input.py, pointer_lock.py): the RvPointerSample
layout, a host with a recording listener on the document, and the PointerEvent, MouseEvent and TouchEvent fields
each recorded event carries."""
import ctypes
import hashlib
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import bind as bind_utf8

OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, NOT_ELEMENT, UNSUPPORTED = 0, -1, -2, -3, -4, -9
MOUSE, PEN, TOUCH = 0, 1, 2
MOVE, DOWN, UP, CANCEL, STATIONARY = 0, 1, 2, 3, 4
BUTTON_NONE, BUTTON_LEFT = -1, 0
LOCK_NONE, LOCK_PENDING, LOCK_LOCKED = 0, 1, 2
PEN_BASE = 1 << 30
i32, f32, f64, p = ctypes.c_int32, ctypes.c_float, ctypes.c_double, ctypes.c_void_p
CALLBACK = ctypes.CFUNCTYPE(i32, p, p)


class Sample(ctypes.Structure):
    _fields_ = [('size', i32), ('pointerType', i32), ('id', i32), ('action', i32), ('x', f64), ('y', f64),
                ('button', i32), ('buttons', i32), ('modifiers', i32), ('clickCount', i32), ('pressure', f32),
                ('tangentialPressure', f32), ('tiltX', i32), ('tiltY', i32), ('twist', i32), ('width', f32),
                ('height', f32), ('movementX', f64), ('movementY', f64)]


class TouchGeometry(ctypes.Structure):
    _fields_ = [('size', i32), ('rotationAngle', f32), ('radiusX', f64), ('radiusY', f64), ('force', f32)]


def sample(kind, action, x, y, id=0, button=BUTTON_NONE, buttons=0, pressure=math.nan, width=1.0, height=1.0, **extra):
    value = Sample(size=ctypes.sizeof(Sample), pointerType=kind, id=id, action=action, x=x, y=y, button=button,
                   buttons=buttons, pressure=pressure, width=width, height=height)
    for key, item in extra.items():
        setattr(value, key, item)
    return value


POINTER_FIELDS = [('pointerId', 'rv_dom_pointer_event_get_pointer_id', i32), ('width', 'rv_dom_pointer_event_get_width', f64),
                  ('height', 'rv_dom_pointer_event_get_height', f64), ('pressure', 'rv_dom_pointer_event_get_pressure', f32),
                  ('tangentialPressure', 'rv_dom_pointer_event_get_tangential_pressure', f32),
                  ('tiltX', 'rv_dom_pointer_event_get_tilt_x', i32), ('tiltY', 'rv_dom_pointer_event_get_tilt_y', i32),
                  ('twist', 'rv_dom_pointer_event_get_twist', i32), ('isPrimary', 'rv_dom_pointer_event_get_is_primary', i32)]
MOUSE_FIELDS = [('movementX', 'rv_dom_mouse_event_get_movement_x', f64), ('movementY', 'rv_dom_mouse_event_get_movement_y', f64)]


class Harness:
    def __init__(self, directory, width=320, height=240):
        self.directory = Path(directory).resolve()
        self.checks = 0
        self.before = self.hashes()
        self.search = os.add_dll_directory(str(self.directory)) if sys.platform == 'win32' else None
        filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
        self.library = ctypes.CDLL(str(self.directory / filename))
        b = self.bind
        self.abi_has = b('rv_abi_has', i32, [ctypes.c_char_p])
        self.host_create = b('rv_host_create', p, [i32, i32])
        self.host_destroy = b('rv_host_destroy', None, [p])
        self.load_html_utf8 = b('rv_host_load_html', i32, [p, ctypes.c_char_p, i32])
        self.load_html = lambda host, html: self.load_html_utf8(host, html, len(html))
        self.host_document = b('rv_host_document', p, [p])
        self.query = b('rv_node_query_selector', p, [p, ctypes.c_char_p, ctypes.POINTER(i32)])
        self.node_release = b('rv_node_release', None, [p])
        self.node_equals = b('rv_node_equals', i32, [p, p]) if hasattr(self.library, 'rv_node_equals') else None
        self.add_listener_utf8 = b('rv_node_add_event_listener', p, [p, ctypes.c_char_p, i32, i32, CALLBACK, p])
        self.add_listener = lambda target, name, capture, callback, context: self.add_listener_utf8(target, name, len(name), capture, callback, context)
        self.listener_remove = b('rv_listener_remove', i32, [p])
        self.event_type = b('rv_event_type', i32, [p, ctypes.c_char_p, i32, ctypes.POINTER(i32)])
        self.event_target = b('rv_event_target', p, [p, i32])
        self.event_number = b('rv_event_number', i32, [p, i32, ctypes.POINTER(f64)])
        self.is_trusted = b('rv_dom_event_get_is_trusted', i32, [p, ctypes.POINTER(i32)])
        self.pointer_type = b('rv_dom_pointer_event_get_pointer_type', i32, [p, ctypes.c_char_p, i32, ctypes.POINTER(i32)])
        self.fields = [(k, b(n, i32, [p, ctypes.POINTER(t)]), t) for k, n, t in POINTER_FIELDS + MOUSE_FIELDS]
        self.mouse = b('rv_host_mouse', i32, [p, i32, i32, i32, i32, i32, i32])
        self.pointer = b('rv_host_pointer', i32, [p, ctypes.POINTER(Sample), i32])
        self.set_focused = b('rv_host_set_focused', i32, [p, i32])
        self.run_loop = b('rv_run_loop_cycle', i32, [i32])
        self.last_exception = b('rv_last_exception', i32, [i32, ctypes.c_char_p, i32, ctypes.POINTER(i32)])
        self.attribute = b('rv_element_get_attribute', i32, [p, ctypes.c_char_p, ctypes.c_char_p, i32, ctypes.POINTER(i32)])
        self.host = None
        self.listeners = []
        self.log = []
        self.callback = CALLBACK(self.on_event)

    def bind(self, name, returns, arguments):
        return bind_utf8(self.library, name, returns, arguments)

    def hashes(self):
        return {str(f.relative_to(self.directory)): hashlib.sha256(f.read_bytes()).hexdigest() for f in self.directory.rglob('*') if f.is_file()}

    def expect(self, condition, message):
        self.checks += 1
        if not condition:
            raise AssertionError(message)

    def text(self, fn, *arguments):
        buffer, length = ctypes.create_string_buffer(256), i32()
        status = fn(*arguments, buffer, 256, ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8') if status == OK else status

    def id_of(self, node):
        if not node:
            return None
        value = self.text(self.attribute, node, b'id')
        return value if isinstance(value, str) else '#' + str(value)

    def exception_name(self):
        return self.text(self.last_exception, 0)

    def open(self, html, events):
        self.host = self.host_create(320, 240)
        self.expect(bool(self.host), 'host created')
        self.expect(self.load_html(self.host, html) == OK, 'page loaded')
        self.document = self.host_document(self.host)
        for name in events:
            listener = self.add_listener(self.document, name.encode(), 0, self.callback, None)
            self.expect(bool(listener), 'listener ' + name)
            self.listeners.append(listener)
        self.drain()

    def node(self, selector):
        status = i32()
        node = self.query(self.document, selector.encode(), ctypes.byref(status))
        self.expect(bool(node) and status.value == OK, 'node ' + selector)
        return node

    def close(self):
        for listener in self.listeners:
            self.expect(self.listener_remove(listener) == OK, 'listener removed')
        self.listeners = []
        if self.host:
            self.node_release(self.document)
            self.host_destroy(self.host)
            self.host = None

    def finish(self):
        if self.search:
            self.search.close()
        self.expect(self.hashes() == self.before, 'runtime unchanged')

    def drain(self):
        # Queued tasks such as pointerlockchange run here. A fixed count of cycles: assertions never depend on it.
        for _ in range(4):
            self.run_loop(0)

    def on_event(self, context, event):
        record = {'type': self.text(self.event_type, event)}
        trusted = i32()
        record['trusted'] = trusted.value if self.is_trusted(event, ctypes.byref(trusted)) == OK else None
        target = self.event_target(event, 0)
        record['target'] = self.id_of(target) if target else None
        x, y = f64(), f64()
        if self.event_number(event, 0, ctypes.byref(x)) == OK and self.event_number(event, 1, ctypes.byref(y)) == OK:
            record['clientX'], record['clientY'] = x.value, y.value
        buttons = f64()
        if self.event_number(event, 3, ctypes.byref(buttons)) == OK:
            record['buttons'] = int(buttons.value)
        kind = self.text(self.pointer_type, event)
        if isinstance(kind, str):
            record['pointerType'] = kind
        for key, fn, t in self.fields:
            value = t()
            if fn(event, ctypes.byref(value)) == OK:
                record[key] = value.value
        if self.on_extra:
            self.on_extra(event, record)
        self.log.append(record)
        return 0

    on_extra = None

    def take(self):
        self.drain()
        out, self.log = self.log, []
        return out

    def send(self, *samples):
        array = (Sample * len(samples))(*samples)
        return self.pointer(self.host, array, len(samples))
