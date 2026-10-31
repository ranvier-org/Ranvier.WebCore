import ctypes
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8


class SvgProbe:
    pointer = ctypes.c_void_p
    integer = ctypes.c_int32
    unsigned = ctypes.c_uint32
    single = ctypes.c_float
    double = ctypes.c_double
    short = ctypes.c_uint16

    def __init__(self, native_directory, width=500, height=300):
        self.directory = Path(native_directory).resolve()
        filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
        self.search = os.add_dll_directory(str(self.directory)) if sys.platform == 'win32' else None
        self.library = ctypes.CDLL(str(self.directory / filename))
        self.width, self.height = width, height
        self.retained, self.watches = [], []
        self.assertions = 0
        self.host = self.bind('rv_host_create', self.pointer, [self.integer, self.integer])(width, height)
        self.expect(bool(self.host), 'SVG paint host creation')

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        self.release_all()
        self.dispose_host()
        for watch in self.watches:
            self.bind('rv_watch_release', None, [self.pointer])(watch)
        if self.search:
            self.search.close()

    def bind(self, name, result, arguments):
        try:
            return bind_utf8(self.library, name, result, arguments)
        except AttributeError as error:
            raise AssertionError('required native binding is absent: ' + name) from error

    def expect(self, condition, label):
        self.assertions += 1
        if not condition:
            raise AssertionError(label)

    def close(self, actual, expected, label, tolerance=0.001):
        self.expect(len(actual) == len(expected) and all(math.isclose(a, b, rel_tol=0, abs_tol=tolerance) for a, b in zip(actual, expected)), label + ': ' + str(actual))

    def call(self, name, arguments, *values):
        status = self.bind(name, self.integer, arguments)(*values)
        self.expect(status == 0, name + ': status ' + str(status))

    def object(self, name, arguments, values, root, nullable=False):
        result = self.pointer()
        self.call(name, arguments + [ctypes.POINTER(self.pointer)], *values, ctypes.byref(result))
        if not nullable:
            self.expect(bool(result.value), name + ': nonnull')
        if result.value:
            self.retained.append(('rv_node_release' if root == 'node' else 'rv_dom_' + root + '_release', result.value))
        return result.value

    def read(self, root, target, field, scalar=None):
        scalar = scalar or self.single
        result = scalar()
        self.call('rv_dom_' + root + '_get_' + field, [self.pointer, ctypes.POINTER(scalar)], target, ctypes.byref(result))
        return result.value

    def text(self, name, arguments, *values):
        buffer, length = ctypes.create_string_buffer(8192), self.integer()
        self.call(name, arguments + [self.pointer, self.integer, ctypes.POINTER(self.integer)], *values, buffer, len(buffer), ctypes.byref(length))
        return None if length.value < 0 else buffer.value.decode()

    def exception(self, name, arguments, values, expected):
        status = self.bind(name, self.integer, arguments)(*values)
        self.expect(status == -3, name + ': exception status ' + str(status))
        self.expect(self.text('rv_last_exception', [self.integer], 0) == expected, name + ': exception ' + expected)

    def load(self, markup, standalone=True):
        self.call('rv_host_load_svg' if standalone else 'rv_host_load_html', [self.pointer, ctypes.c_char_p], self.host, markup.encode() if isinstance(markup, str) else markup)

    def node(self, identifier):
        result = self.bind('rv_document_get_element_by_id', self.pointer, [self.pointer, ctypes.c_char_p])(self.host, identifier.encode())
        self.expect(bool(result), 'real SVG node ' + identifier)
        self.retained.append(('rv_node_release', result))
        return result

    def property(self, kind, target, field, root):
        return self.object('rv_dom_' + kind + '_get_' + field, [self.pointer], [target], root)

    def length(self, kind, target, field):
        animated = self.property(kind, target, field, 'svg_animated_length')
        return animated, self.property('svg_animated_length', animated, 'base_val', 'svg_length')

    def set_length(self, target, value):
        self.call('rv_dom_svg_length_set_value', [self.pointer, self.single], target, value)

    def attribute(self, target, name):
        return self.text('rv_dom_element_get_attribute', [self.pointer, Utf8], target, name.encode())

    def attributes(self, target):
        count = self.bind('rv_element_attribute_count', self.integer, [self.pointer])(target)
        self.expect(count >= 0, 'real element attribute enumeration')
        result, names = {}, []
        for index in range(count):
            name = self.text('rv_element_attribute_at', [self.pointer, self.integer, self.integer], target, index, 0)
            names.append(name)
            result[name] = self.text('rv_element_attribute_at', [self.pointer, self.integer, self.integer], target, index, 1)
        self.expect(len(names) == len(set(names)), 'element attribute qualified names are unique: ' + str(names))
        return result

    def update(self):
        self.expect(self.bind('rv_host_update', self.integer, [self.pointer])(self.host) >= 0, 'SVG paint update')

    def paint(self):
        self.update()
        rgba = (ctypes.c_uint8 * (self.width * self.height * 4))()
        self.call('rv_host_paint_rgba', [self.pointer, self.pointer, self.integer], self.host, rgba, len(rgba))
        return rgba

    def pixel(self, rgba, x, y):
        return list(rgba[(y * self.width + x) * 4:(y * self.width + x) * 4 + 4])

    def watch(self, node):
        watch = self.bind('rv_node_watch', self.pointer, [self.pointer])(node)
        self.expect(bool(watch), 'SVG weak owner watch')
        self.watches.append(watch)
        return watch

    def release_nodes(self):
        for release, target in list(reversed(self.retained)):
            if release == 'rv_node_release':
                self.bind(release, None, [self.pointer])(target)
                self.retained.remove((release, target))

    def release_all(self):
        for release, target in reversed(self.retained):
            self.bind(release, None, [self.pointer])(target)
        self.retained.clear()

    def dispose_host(self):
        if self.host:
            self.bind('rv_host_destroy', None, [self.pointer])(self.host)
            self.host = None

    def collect(self):
        self.expect(self.bind('rv_run_loop_cycle', self.integer, [self.integer])(100) >= 0, 'SVG disposal event cycle')
        self.bind('rv_release_memory', None, [])()
        self.bind('rv_collect_garbage', None, [])()

    def expect_expired(self):
        for watch in self.watches:
            self.expect(self.bind('rv_watch_alive', self.integer, [self.pointer])(watch) == 0, 'SVG owner expires after final release/collection')
