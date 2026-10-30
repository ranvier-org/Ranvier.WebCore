import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys
import threading

def verify(directory):
    checks = 0

    def expect(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise AssertionError(message)
    directory = Path(directory).resolve()
    before = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
    print('RUNTIME_BEFORE=' + json.dumps(before, sort_keys=True), flush=True)
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    library = ctypes.CDLL(str(directory / filename))
    integer, pointer = (ctypes.c_int32, ctypes.c_void_p)

    def bind(name, returns, arguments):
        function = getattr(library, name)
        function.restype, function.argtypes = (returns, arguments)
        return function
    has = bind('rv_abi_has', integer, [ctypes.c_char_p])
    expect(has(b'capabilities') == 1, 'H07 introspection surface must be advertised')
    count = bind('rv_capability_count', integer, [integer])
    name_at = bind('rv_capability_name_at', integer, [integer, integer, pointer, integer, ctypes.POINTER(integer)])
    fact = bind('rv_host_capability_fact', integer, [pointer, integer, ctypes.c_char_p, integer, ctypes.POINTER(integer)])
    kind = bind('rv_host_capability_value_kind', integer, [pointer, integer, ctypes.c_char_p, ctypes.POINTER(integer)])
    number = bind('rv_host_capability_value_number', integer, [pointer, integer, ctypes.c_char_p, ctypes.POINTER(ctypes.c_double)])
    text = bind('rv_host_capability_value_text', integer, [pointer, integer, ctypes.c_char_p, pointer, integer, ctypes.POINTER(integer)])
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(host, 'Capability assertion failed')
    try:
        catalogues = {}
        for category in range(5):
            catalogues[category] = []
            expect(count(category) > 0, 'Capability assertion failed')
            for index in range(count(category)):
                length = integer(-99)
                expect(name_at(category, index, None, 0, ctypes.byref(length)) == -6, 'Capability assertion failed')
                expect(length.value > 0, 'Capability assertion failed')
                buffer = ctypes.create_string_buffer(length.value + 1)
                buffer.raw = b'!' * len(buffer)
                expect(name_at(category, index, buffer, length.value, ctypes.byref(length)) == 0, 'Capability assertion failed')
                expect(buffer.raw[length.value] == ord('!'), 'exact byte transport writes no terminator')
                name = buffer.raw[:length.value]
                catalogues[category].append(name.decode('utf-8'))
                for dimension in range(5):
                    value = integer(42)
                    expect(fact(host, category, name, dimension, ctypes.byref(value)) == 0, 'Capability assertion failed')
                    expect(value.value in [-1, 0, 1], 'Capability assertion failed')
        for category in range(5):
            for dimension in range(5):
                value = integer(42)
                expect(fact(host, category, b'unknown-future-facility', dimension, ctypes.byref(value)) == 0, 'Capability assertion failed')
                expect(value.value == -1, 'Capability assertion failed')
        absent = integer(42)
        expect(kind(host, 4, b'unknown-future-facility', ctypes.byref(absent)) == 0 and absent.value == 0, 'Capability assertion failed')
        sentinel = ctypes.c_double(42)
        expect(number(host, 4, b'unknown-future-facility', ctypes.byref(sentinel)) == -9 and sentinel.value == 42, 'Capability assertion failed')
        length = integer(42)
        buffer = ctypes.create_string_buffer(b'untouched')
        expect(text(host, 4, b'unknown-future-facility', buffer, len(buffer), ctypes.byref(length)) == -9, 'Capability assertion failed')
        expect(length.value == 42 and buffer.value == b'untouched', 'Capability assertion failed')

        def get_fact(category, name, dimension):
            value = integer(42)
            expect(fact(host, category, name.encode(), dimension, ctypes.byref(value)) == 0, 'Capability assertion failed')
            return value.value

        def get_number(category, name, expected_kind):
            value_kind = integer(42)
            expect(kind(host, category, name.encode(), ctypes.byref(value_kind)) == 0 and value_kind.value == expected_kind, 'Capability assertion failed')
            value = ctypes.c_double(42)
            expect(number(host, category, name.encode(), ctypes.byref(value)) == 0, 'Capability assertion failed')
            return value.value
        expect('dom:Document' in catalogues[0] and 'svg-document' in catalogues[0], 'Capability assertion failed')
        expect(get_fact(0, 'dom:Document', 0) == 1 and get_fact(0, 'dom:Document', 1) == -1, 'Capability assertion failed')
        expect(get_number(1, 'scripts', 1) == 0 and get_number(1, 'vm-entry-guard', 1) == 1, 'Capability assertion failed')
        expect(get_number(1, 'automatic-images', 1) == 1, 'Capability assertion failed')
        expect(get_number(1, 'viewport-width', 2) == 320 and get_number(1, 'viewport-height', 2) == 240, 'Capability assertion failed')
        expect(get_number(1, 'device-scale', 2) == 1, 'Capability assertion failed')
        expect(get_number(1, 'paint-width', 2) == 320 and get_number(1, 'paint-height', 2) == 240, 'Capability assertion failed')
        for name in ['network', 'sqlite', 'indexeddb', 'cache-storage', 'service-worker', 'shared-worker', 'websocket', 'webtransport', 'file-system', 'push', 'inspector', 'jsc-inspector', 'crypto-other-algorithms']:
            flag_name = {'network': 'USE_NETWORK_STUB', 'sqlite': 'USE_SQLITE_STUB', 'webtransport': 'USE_BROWSER_API_STUB', 'file-system': 'USE_BROWSER_API_STUB', 'inspector': 'USE_INSPECTOR_STUB', 'jsc-inspector': 'USE_JSC_INSPECTOR_STUB', 'crypto-other-algorithms': 'USE_CRYPTO_STUB'}.get(name, 'USE_WEB_API_STUB')
            flag_kind = integer(42)
            expect(kind(host, 4, ('build:' + flag_name).encode(), ctypes.byref(flag_kind)) == 0, 'Capability assertion failed')
            if flag_kind.value == 1 and get_number(4, 'build:' + flag_name, 1) == 1:
                expect(get_fact(4, name, 1) == 0, 'Compiled stub must not claim implementation: ' + name)
        expect(get_fact(4, 'resource-callback', 1) == 1, 'Capability assertion failed')
        expect(get_number(4, 'resource-callback', 1) == 0, 'Capability assertion failed')
        expect(get_fact(4, 'resource-callback', 4) == -1, 'Callback wiring cannot prove external readiness')
        for category in range(5):
            expect(get_fact(category, 'unknown-future-facility', 4) == -1, 'Capability assertion failed')
        for category, name in [(2, 'image/png'), (2, 'image/svg+xml'), (3, 'woff2')]:
            expect(get_number(category, name, 1) in [0, 1], 'Capability assertion failed')
            expect(get_fact(category, name, 4) == -1, 'Format query does not prove arbitrary decode/render')
        size = integer(-99)
        expect(text(host, 1, b'compositing-mode', None, 0, ctypes.byref(size)) == -6 and size.value > 0, 'Capability assertion failed')
        buffer = ctypes.create_string_buffer(b'!' * (size.value + 1))
        buffer.raw = b'!' * len(buffer)
        length = integer(-99)
        expect(text(host, 1, b'compositing-mode', buffer, size.value - 1, ctypes.byref(length)) == -6, 'Capability assertion failed')
        expect(buffer.raw == b'!' * len(buffer) and length.value == size.value, 'Capability assertion failed')
        expect(text(host, 1, b'compositing-mode', buffer, size.value, ctypes.byref(length)) == 0, 'Capability assertion failed')
        expect(buffer.raw[size.value] == ord('!'), 'Capability assertion failed')
        old = ctypes.c_double(42)
        expect(number(host, 1, b'compositing-mode', ctypes.byref(old)) == -9 and old.value == 42, 'Capability assertion failed')
        sentinel = integer(42)
        for target, category, name, dimension, expected in [(None, 0, b'input', 0, -1), (host, -1, b'input', 0, -9), (host, 0, None, 0, -1), (host, 0, b'input', 5, -9), (host, 0, b'', 0, -9)]:
            expect(fact(target, category, name, dimension, ctypes.byref(sentinel)) == expected, 'Capability assertion failed')
            expect(sentinel.value == 42, 'Capability assertion failed')
        wrong_thread = []

        def background():
            sentinel = integer(42)
            wrong_thread.append((fact(host, 0, b'input', 0, ctypes.byref(sentinel)), sentinel.value))
        thread = threading.Thread(target=background)
        thread.start()
        thread.join()
        expect(wrong_thread == [(-2, 42)], 'Capability assertion failed')
        video_kind = integer(42)
        expect(kind(host, 4, b'build:ENABLE_VIDEO', ctypes.byref(video_kind)) == 0, 'Video compile observation status')
        if video_kind.value == 1:
            if get_number(4,'build:ENABLE_VIDEO',1) == 1:
                expect(get_fact(4,'video',1) == 1, 'Compiled-in video differs from host enablement')
                expect(get_number(1,'media',1) == 0, 'Host media remains disabled on compiled-in video profiles')
            else:
                expect(get_fact(4,'video',1) == 0, 'Compiled-out video is an authoritative negative')
                absent = integer(42)
                expect(kind(host,1,b'media',ctypes.byref(absent)) == 0 and absent.value == 0, 'Compiled-out media setting is absent rather than false')
        expect(bind('rv_host_load_html',integer,[pointer,ctypes.c_char_p])(host,b'<!doctype html><body>replacement') == 0,'Document replacement')
        document = bind('rv_host_document',pointer,[pointer])(host)
        expect(bool(document),'Current document handle')
        try:
            query=b'font-format(woff2)'
            raw=integer(42)
            expect(bind('rv_dom_css_supports_1',integer,[pointer,pointer,integer,ctypes.POINTER(integer)])(document,query,len(query),ctypes.byref(raw)) == 0,'Current-document raw font query')
            expect(get_number(3,'woff2',1) == raw.value,'Font query refreshes the current document after replacement')
        finally:
            bind('rv_node_release',None,[pointer])(document)
    finally:
        bind('rv_host_destroy', None, [pointer])(host)
        stale=integer(42)
        expect(fact(host,0,b'input',0,ctypes.byref(stale)) == -9 and stale.value == 42,'Destroyed host is rejected before dereference')
        after = {str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.rglob('*') if p.is_file()}
        expect(before == after, 'executed native runtime changed')
        if search:
            search.close()
    print('CAPABILITIES_NATIVE_CHECKS=' + str(checks), flush=True)
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('native_directory', nargs='?')
    parser.add_argument('--native-directory',dest='named_directory')
    arguments=parser.parse_args()
    directory=arguments.named_directory or arguments.native_directory
    if not directory: parser.error('A native directory is required')
    verify(directory)
