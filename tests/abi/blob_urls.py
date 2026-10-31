"""#144 blob URL probe against an actual runtime directory. Replays tests/fixtures/blob-urls-cases.json and compares
the results with the Chromium oracle tests/fixtures/blob-urls-oracle.json: object URL format and lifetime, blob: image
loads, rv_blob_url_read, rv_blob_read (Blob.text/arrayBuffer/bytes), FileReader event order and state, file-backed
blobs from rv_file_create_from_path, isolation between hosts, and teardown with outstanding reads. Progress events
are collapsed and never counted. Differences listed in tests/fixtures/blob-urls-qualified.json are recorded, not
failed."""

import argparse
import ctypes
import json
from pathlib import Path
import re
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, P, I, U, utf8
from binary_values import Binary

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, DETACHED, WRONG_INTERFACE = 0, -1, -2, -3, -6, -9, -10, -11
ABI = 54
SUCCEEDED, LOAD_FAILED, DECODE_FAILED, CANCELLED, INVALIDATED = 0, 1, 2, 3, 4
OUTCOMES = {0: 'succeeded', 1: 'loadFailed', 2: 'decodeFailed', 3: 'cancelled', 4: 'invalidated'}
READ_TEXT, READ_BYTES = 0, 1
RESULT_KINDS = {0: 'null', 1: 'string', 2: 'bytes'}
L = ctypes.c_int64
EVENT_CALLBACK = ctypes.CFUNCTYPE(I, P, P)
COMPLETION = ctypes.CFUNCTYPE(None, P, I, I, I)
HANDLER = ctypes.CFUNCTYPE(None, P, P, ctypes.c_char_p)
UUID = re.compile(r'^blob:(.*)/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$')
TYPES = ['loadstart', 'progress', 'load', 'abort', 'error', 'loadend']
HANG_SECONDS = 20
REPORT_PATH = None


def checksum(data):
    total = 0
    for byte in data:
        total = (total * 33 + byte) & 0xFFFFFFFF
    return total


def describe_bytes(data):
    return {'length': len(data), 'hex': data.hex()} if len(data) <= 64 else {'length': len(data), 'checksum': checksum(data)}


class Host:
    """A host with a document, a resource handler that records and fails every load it receives, and blob helpers."""

    def __init__(self, native, markup='<!doctype html><body><img id=i></body>'):
        self.n = native
        self.host = native.bind('rv_host_create', P, [I, I])(320, 200)
        native.expect(bool(self.host), 'host')
        self.handled = []
        self.handler = HANDLER(self.on_load)
        native.ok('rv_host_set_resource_handler', [P, HANDLER, P], self.host, self.handler, None)
        self.load(markup)
        self.listeners, self.callbacks, self.targets = [], [], []

    def on_load(self, context, load, url):
        self.handled.append(url.decode('utf-8'))
        self.n.call('rv_resource_load_fail', [P], load)

    def load(self, markup):
        self.n.ok('rv_host_load_html', [P, ctypes.c_char_p], self.host, markup.encode('utf-8'))
        self.document = self.n.bind('rv_host_document', P, [P])(self.host)
        self.binary = Binary(self.n, type('CaseLike', (), {'document': self.document})())

    def blob(self, spec):
        parts = []
        for part in spec['parts']:
            if 'text' in part:
                parts.append(part['text'])
            elif 'hex' in part:
                parts.append(bytes.fromhex(part['hex']))
            else:
                parts.append(bytes.fromhex(part['repeat']) * part['count'])
        return self.binary.blob(parts, type=spec['type'] if spec['type'] else None)

    def node(self, identifier):
        text, length = utf8(identifier)
        result = P()
        self.n.ok('rv_dom_document_get_element_by_id', [P, P, I, ctypes.POINTER(P)], self.document, text, length, ctypes.byref(result))
        return result.value

    def object_url(self, blob):
        buffer, length = ctypes.create_string_buffer(256), I()
        self.n.ok('rv_dom_domurl_create_object_url', [P, P, P, I, ctypes.POINTER(I)], self.document, blob, buffer, len(buffer), ctypes.byref(length))
        return buffer.raw[:length.value].decode('utf-8')

    def revoke(self, url):
        text, length = utf8(url)
        return self.n.call('rv_dom_domurl_revoke_object_url', [P, P, I], self.document, text, length)

    def close(self):
        for listener in self.listeners:
            self.n.call('rv_listener_remove', [P], listener)
        for target in self.targets:
            self.n.bind('rv_event_target_release', None, [P])(target)
        self.binary.release_all()
        self.n.bind('rv_host_destroy', None, [P])(self.host)


def cycle(native):
    native.bind('rv_run_loop_cycle', I, [I])(2)


def wait(native, condition, label):
    """Cycles the run loop until condition holds; a hang raises and counts nothing."""
    deadline = time.monotonic() + HANG_SECONDS
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError('hang: ' + label)
        cycle(native)


def drain(native, milliseconds=30):
    native.bind('rv_run_loop_cycle', I, [I])(milliseconds)


class Operation:
    def __init__(self, native):
        self.n, self.outcome, self.token = native, None, ctypes.c_uint64()
        self.callback = COMPLETION(self.done)

    def done(self, context, outcome, width, height):
        self.outcome, self.size = outcome, (width, height)

    def finish(self, label):
        wait(self.n, lambda: self.outcome is not None, label)
        return self.outcome

    def result(self):
        length = L()
        status = self.n.call('rv_blob_read_result', [ctypes.c_uint64, P, L, ctypes.POINTER(L)], self.token, None, 0, ctypes.byref(length))
        if status == UNSUPPORTED:
            return None
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        self.n.ok('rv_blob_read_result', [ctypes.c_uint64, P, L, ctypes.POINTER(L)], self.token, buffer, length.value, ctypes.byref(length))
        return buffer.raw[:length.value]

    def text(self, name):
        buffer, length = ctypes.create_string_buffer(512), I()
        status = self.n.call(name, [ctypes.c_uint64, P, I, ctypes.POINTER(I)], self.token, buffer, len(buffer), ctypes.byref(length))
        return None if status == UNSUPPORTED else buffer.raw[:length.value].decode('utf-8')

    def release(self):
        self.n.ok('rv_resource_release', [ctypes.c_uint64], self.token)


def blob_read(host, blob, mode):
    operation = Operation(host.n)
    host.n.ok('rv_blob_read', [P, P, I, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)], host.host, blob, mode, operation.callback, None, ctypes.byref(operation.token))
    host.n.expect(operation.outcome is None, 'rv_blob_read completes after it returns')
    return operation


def url_read(host, url):
    operation = Operation(host.n)
    data = url.encode('utf-8')
    host.n.ok('rv_blob_url_read', [P, P, I, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)], host.host, data, len(data), operation.callback, None, ctypes.byref(operation.token))
    return operation


def url_read_result(host, url):
    """rv_blob_url_read in the oracle's shape: the type and bytes, or the failure."""
    operation = url_read(host, url)
    outcome = operation.finish('url read ' + url)
    if outcome == SUCCEEDED:
        value = {'ok': True, 'type': operation.text('rv_blob_read_type'), **describe_bytes(operation.result())}
    else:
        value = {'ok': False, 'outcome': OUTCOMES[outcome], 'error': operation.text('rv_blob_read_error')}
    operation.release()
    return value


def image(host, url):
    n = host.n
    element = host.node('i')
    source, source_length = utf8(url)
    n.ok('rv_dom_html_image_element_set_src', [P, P, I], element, source, source_length)
    operation = Operation(n)
    n.ok('rv_image_decode', [P, P, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)], host.host, element, operation.callback, None, ctypes.byref(operation.token))
    outcome = operation.finish('image ' + url)
    operation.release()
    n.bind('rv_node_release', None, [P])(element)
    return {'outcome': 'load' if outcome == SUCCEEDED else 'error', 'width': operation.size[0], 'height': operation.size[1]}


class Reader:
    """A FileReader with a listener per event type that records collapsed event order and the state at each first event."""

    def __init__(self, host, hooks=None):
        self.host, self.n = host, host.n
        target = P()
        self.n.ok('rv_dom_file_reader_create', [P, ctypes.POINTER(P)], host.document, ctypes.byref(target))
        self.target = target.value
        host.targets.append(self.target)
        self.events, self.states, self.hooks, self.loadends = [], {}, hooks or {}, 0
        for kind in TYPES:
            callback = EVENT_CALLBACK(lambda context, event, kind=kind: self.on_event(kind))
            host.callbacks.append(callback)
            listener = self.n.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, EVENT_CALLBACK, P])(self.target, kind.encode(), 0, callback, None)
            self.n.expect(bool(listener), 'FileReader listener')
            host.listeners.append(listener)

    def ready_state(self):
        value = ctypes.c_uint16()
        self.n.ok('rv_dom_file_reader_get_ready_state', [P, ctypes.POINTER(ctypes.c_uint16)], self.target, ctypes.byref(value))
        return value.value

    def result(self):
        kind, length = I(), L()
        status = self.n.call('rv_file_reader_result', [P, ctypes.POINTER(I), P, L, ctypes.POINTER(L)], self.target, ctypes.byref(kind), None, 0, ctypes.byref(length))
        self.n.expect(status in (OK, BUFFER_TOO_SMALL), f'result status {status}')
        data = b''
        if length.value:
            buffer = ctypes.create_string_buffer(length.value)
            self.n.ok('rv_file_reader_result', [P, ctypes.POINTER(I), P, L, ctypes.POINTER(L)], self.target, ctypes.byref(kind), buffer, length.value, ctypes.byref(length))
            data = buffer.raw[:length.value]
        name = RESULT_KINDS[kind.value]
        return name, data

    def error(self):
        buffer, length = ctypes.create_string_buffer(128), I()
        self.n.ok('rv_file_reader_error', [P, P, I, ctypes.POINTER(I)], self.target, buffer, len(buffer), ctypes.byref(length))
        return None if length.value < 0 else buffer.raw[:length.value].decode('utf-8')

    def on_event(self, kind):
        try:
            if not self.events or self.events[-1] != kind:
                self.events.append(kind)
            if kind not in self.states:
                self.states[kind] = {'readyState': self.ready_state(), 'result': self.result()[0], 'error': self.error()}
            if kind == 'loadend':
                self.loadends += 1
            hook = self.hooks.pop(kind, None)
            if hook:
                hook()
                self.events.append('acted')
            return 0
        except Exception as error:
            self.events.append('listenerError: ' + str(error))
            return 1

    def read(self, method, blob, encoding=None):
        """Calls readAs<method>; returns the DOMException name it throws, or None."""
        name = {'readAsArrayBuffer': 'array_buffer', 'readAsBinaryString': 'binary_string', 'readAsText': 'text', 'readAsDataURL': 'data_url'}[method]
        if method == 'readAsText':
            text, length = (None, -1) if encoding is None else utf8(encoding)
            status = self.n.call('rv_dom_file_reader_read_as_text', [P, P, P, I], self.target, blob, text, length)
        else:
            status = self.n.call('rv_dom_file_reader_read_as_' + name, [P, P], self.target, blob)
        self.n.expect(status in (OK, DOM_EXCEPTION), f'{method} status {status}')
        return None if status == OK else self.n.text('rv_last_exception', [I], 0)

    def abort(self):
        self.n.ok('rv_dom_file_reader_abort', [P], self.target)

    def final(self):
        kind, data = self.result()
        result = {'kind': kind}
        if kind == 'string':
            result['value'] = data.decode('utf-8')
        elif kind == 'bytes':
            result.update(describe_bytes(data))
        return {'readyState': self.ready_state(), 'result': result, 'error': self.error()}


def reader_case(host, cases, spec):
    blobs = {}

    def blob(name):
        if name not in blobs:
            blobs[name] = host.blob(cases['blobs'][name])
        return blobs[name]

    outcome = {'threw': None, 'second': None}

    def act():
        if spec['action'] == 'abort':
            reader.abort()
        else:
            thrown = reader.read('readAsText', blob('y'))
            outcome['second'] = thrown or 'ok'

    hooks = {spec['hook']: act} if spec.get('hook') and spec['hook'] != 'sync' else {}
    reader = Reader(host, hooks)
    outcome['threw'] = reader.read(spec['method'], blob(spec['blob']), spec.get('encoding'))
    reader.events.append('return')
    if spec.get('hook') == 'sync':
        act()
        reader.events.append('acted')
    ends = 2 if spec.get('action') == 'readY' and spec.get('hook') == 'loadend' else 1
    wait(host.n, lambda: reader.loadends >= ends, 'reader ' + spec['name'])
    drain(host.n)
    return {'events': reader.events, 'states': reader.states, **outcome, 'final': reader.final()}


def shared(native, cases, report):
    host = Host(native)
    n = native
    report['reader'] = {spec['name']: reader_case(host, cases, spec) for spec in cases['reader']}
    empty = Reader(host)
    fired = []
    empty.on_event = lambda kind: fired.append(kind) or 0
    empty.abort()
    report['readerAbortWhenEmpty'] = {'readyState': empty.ready_state(), 'fired': fired, 'result': None if empty.result()[0] == 'null' else 'set', 'error': empty.error()}
    fresh = Reader(host)
    report['readerInitial'] = {'readyState': fresh.ready_state(), 'result': None if fresh.result()[0] == 'null' else 'set', 'error': fresh.error()}
    report['promises'] = {}
    for spec in cases['promises']:
        operation = blob_read(host, host.blob(cases['blobs'][spec['blob']]), READ_TEXT if spec['mode'] == 'text' else READ_BYTES)
        n.expect(operation.finish('promise ' + spec['name']) == SUCCEEDED, 'promise read succeeded')
        data = operation.result()
        report['promises'][spec['name']] = {'ok': True, 'value': data.decode('utf-8')} if spec['mode'] == 'text' else {'ok': True, **describe_bytes(data)}
        operation.release()
    first, again = host.object_url(host.blob(cases['blobs']['abc'])), host.object_url(host.blob(cases['blobs']['abc']))
    match = UUID.match(first)
    report['format'] = {'matches': bool(match) and bool(UUID.match(again)), 'origin': match.group(1) if match else None, 'distinct': first != again}
    report['urlReads'] = {}
    for spec in cases['urlReads']:
        source = host.blob(cases['blobs'][spec['blob']])
        if spec.get('slice'):
            source = host.binary.slice(source, *spec['slice'])
        report['urlReads'][spec['name']] = url_read_result(host, host.object_url(source) + spec.get('fragment', ''))
    n.expect(host.revoke(first) == OK, 'revoke')
    report['revoked'] = {'read': url_read_result(host, first), 'other': url_read_result(host, again)}
    statuses = [host.revoke(first), host.revoke('not a url'), host.revoke('https://x/')]
    report['revokeNoOp'] = 'ok' if statuses == [OK, OK, OK] else str(statuses)
    report['unknown'] = url_read_result(host, 'blob:null/00000000-0000-4000-8000-000000000000')
    report['images'] = {spec['name']: image(host, host.object_url(host.blob(cases['blobs'][spec['blob']]))) for spec in cases['images']}
    svg = host.object_url(host.blob(cases['blobs']['svg']))
    host.revoke(svg)
    report['imageRevoked'] = image(host, svg)
    report['handlerSawBlob'] = [url for url in host.handled if url.startswith('blob:')]
    n.expect(report['handlerSawBlob'] == [], 'blob: loads never reach the resource handler')
    host.close()


def errors(native, report):
    """Argument, thread and interface errors of the hand-written functions."""
    n = native
    host = Host(native)
    blob = host.blob({'parts': [{'text': 'e'}], 'type': ''})
    operation = Operation(n)
    sig = [P, P, I, COMPLETION, P, ctypes.POINTER(ctypes.c_uint64)]
    n.expect(n.call('rv_blob_read', sig, None, blob, 0, operation.callback, None, ctypes.byref(operation.token)) == NULL_ARGUMENT, 'rv_blob_read NULL host')
    n.expect(n.call('rv_blob_read', sig, host.host, blob, 7, operation.callback, None, ctypes.byref(operation.token)) == UNSUPPORTED, 'rv_blob_read mode')
    for url in [b'https://x/', b'blob', b'']:
        n.expect(n.call('rv_blob_url_read', sig, host.host, url, len(url), operation.callback, None, ctypes.byref(operation.token)) == UNSUPPORTED, 'non-blob URL')
    n.expect(n.call('rv_blob_url_read', sig, host.host, b'\xff', 1, operation.callback, None, ctypes.byref(operation.token)) == NULL_ARGUMENT, 'invalid UTF-8 URL')
    created = P()
    for path in [b'relative.txt', b'', b'.\\x']:
        n.expect(n.call('rv_file_create_from_path', [P, P, I, ctypes.POINTER(P)], host.host, path, len(path), ctypes.byref(created)) == UNSUPPORTED, 'relative path')
    n.expect(n.call('rv_blob_read_result', [ctypes.c_uint64, P, L, ctypes.POINTER(L)], 999999, None, 0, ctypes.byref(L())) == UNSUPPORTED, 'unknown token')
    window = n.bind('rv_host_window_event_target', P, [P])(host.host)
    n.expect(n.call('rv_file_reader_result', [P, ctypes.POINTER(I), P, L, ctypes.POINTER(L)], window, ctypes.byref(I()), None, 0, ctypes.byref(L())) == WRONG_INTERFACE, 'result of a window')
    n.bind('rv_event_target_release', None, [P])(window)
    results = {}

    def other():
        results['read'] = n.call('rv_blob_read', sig, host.host, blob, 0, operation.callback, None, ctypes.byref(operation.token))
        results['url'] = n.call('rv_dom_domurl_create_object_url', [P, P, P, I, ctypes.POINTER(I)], host.document, blob, None, 0, ctypes.byref(I()))
    thread = threading.Thread(target=other)
    thread.start()
    thread.join()
    n.expect(results == {'read': WRONG_THREAD, 'url': WRONG_THREAD}, f'wrong thread {results}')
    host.close()


def file_backed(native, report):
    n = native
    host = Host(native)
    directory = Path(tempfile.mkdtemp(prefix='rv-blob-'))
    path = directory / 'data.txt'
    path.write_bytes(b'file-bytes')
    data = str(path).encode('utf-8')
    created = P()
    n.ok('rv_file_create_from_path', [P, P, I, ctypes.POINTER(P)], host.host, data, len(data), ctypes.byref(created))
    file = host.binary.track(created.value)
    name = n.text('rv_dom_file_get_name', [P], file)
    size = ctypes.c_uint64()
    n.ok('rv_dom_blob_get_size', [P, ctypes.POINTER(ctypes.c_uint64)], file, ctypes.byref(size))
    kind = n.text('rv_dom_blob_get_type', [P], file)
    bytes_status = n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], file, None, 0, ctypes.byref(L()))
    text = blob_read(host, file, READ_TEXT)
    text.finish('file text')
    url = host.object_url(file)
    sliced = blob_read(host, host.binary.slice(file, 1, 3), READ_TEXT)
    sliced.finish('file slice')
    report['file'] = {'name': name, 'size': size.value, 'type': kind, 'text': text.result().decode('utf-8'),
                      'urlRead': url_read_result(host, url), 'slice': sliced.result().decode('utf-8'), 'readBytesStatus': bytes_status}
    text.release()
    sliced.release()
    # Teardown: the file deleted between create and read. The engine closes a read's file stream on a later run-loop turn.
    drain(n, 100)
    path.unlink()
    directory.rmdir()
    reader = Reader(host)
    reader.read('readAsText', file)
    wait(n, lambda: reader.loadends >= 1, 'deleted file reader')
    final = reader.final()
    failed = blob_read(host, file, READ_TEXT)
    outcome = failed.finish('deleted file text')
    report['deleted'] = {'reader': {'events': reader.events, 'readyState': final['readyState'], 'result': None if final['result']['kind'] == 'null' else final['result'], 'error': final['error']},
                         'text': {'ok': outcome == SUCCEEDED, 'name': failed.text('rv_blob_read_error')},
                         'urlRead': url_read_result(host, host.object_url(file))}
    failed.release()
    host.close()


def isolation(native, cases, report):
    """A blob URL of host A in host B, after A's document is replaced, and after A is destroyed."""
    a, b = Host(native), Host(native)
    text = a.object_url(a.blob({'parts': [{'text': 'iso'}], 'type': ''}))
    svg = a.object_url(a.blob(cases['blobs']['svg']))
    result = {'otherRead': url_read_result(b, text), 'otherImage': image(b, svg)['outcome'],
              'selfRead': url_read_result(a, text), 'selfImage': image(a, svg)['outcome']}
    reverse = b.object_url(b.blob({'parts': [{'text': 'back'}], 'type': ''}))
    reverse_svg = b.object_url(b.blob(cases['blobs']['svg']))
    result['reverseRead'] = url_read_result(a, reverse)
    result['reverseImage'] = image(a, reverse_svg)['outcome']
    result['reverseSelfRead'] = url_read_result(b, reverse)
    a.binary.release_all()
    a.load('<!doctype html><body><img id=i></body>')
    result['afterReplaceRead'] = url_read_result(a, text)
    result['afterReplaceImage'] = image(a, svg)['outcome']
    late = a.object_url(a.blob({'parts': [{'text': 'late'}], 'type': ''}))
    result['beforeDestroyOtherRead'] = url_read_result(b, late)
    a.close()
    result['afterDestroyRead'] = url_read_result(b, late)
    b.close()
    report['isolation'] = result


def teardown(native, report):
    """Outstanding reads when the document is replaced and when the host is destroyed."""
    n = native
    host = Host(native)
    big = host.blob({'parts': [{'repeat': '00', 'count': 1 << 20}], 'type': ''})
    url = host.object_url(host.blob({'parts': [{'text': 'child'}], 'type': ''}))
    before = url_read_result(host, url)
    reader = Reader(host)
    reader.read('readAsArrayBuffer', big)
    pending = blob_read(host, big, READ_BYTES)
    host.binary.release_all()
    host.load('<!doctype html><body><img id=i></body>')
    replaced = pending.outcome
    drain(n, 200)
    result = {'before': before, 'after': url_read_result(host, url), 'readerEvents': reader.events, 'readerState': reader.ready_state(),
              'promise': OUTCOMES.get(replaced, 'pending')}
    pending.release()
    blob = host.blob({'parts': [{'repeat': '00', 'count': 1 << 20}], 'type': ''})
    last = Reader(host)
    last.read('readAsArrayBuffer', blob)
    destroyed = blob_read(host, blob, READ_BYTES)
    host.binary.release_all()
    held = last.target
    host.targets.remove(held)
    host.close()
    result['destroyPromise'] = OUTCOMES.get(destroyed.outcome, 'pending')
    drain(n, 100)
    result['destroyReaderEvents'] = last.events
    value = ctypes.c_uint16()
    result['destroyReadyStateStatus'] = n.call('rv_dom_file_reader_get_ready_state', [P, ctypes.POINTER(ctypes.c_uint16)], held, ctypes.byref(value))
    n.bind('rv_event_target_release', None, [P])(held)
    destroyed.release()
    report['teardown'] = result


def compare(native, oracle, report, qualified):
    differences = {}

    def walk(path, expected, actual):
        if isinstance(expected, dict) and isinstance(actual, dict):
            for key in sorted(set(expected) | set(actual)):
                walk(path + [key], expected.get(key, '<absent>'), actual.get(key, '<absent>'))
        elif expected != actual:
            differences['.'.join(map(str, path))] = {'chromium': expected, 'native': actual}

    for key in ['reader', 'readerAbortWhenEmpty', 'readerInitial', 'promises', 'format', 'urlReads', 'revoked', 'revokeNoOp',
                'unknown', 'images', 'imageRevoked', 'file', 'deleted']:
        walk([key], normalize(key, oracle[key]), normalize(key, report[key]))
    # Native hosts are about:blank documents, each with its own opaque origin, like Chromium's two about:blank pages.
    # The http-origin isolation cases have no native counterpart, and the destroy cases no Chromium one.
    for key, shared_keys in [('isolation', ['otherRead', 'otherImage', 'selfRead', 'selfImage', 'afterReplaceRead', 'afterReplaceImage']),
                             ('teardown', ['before', 'after', 'readerEvents', 'readerState', 'promise'])]:
        expected, actual = normalize(key, oracle[key]), normalize(key, report[key])
        walk([key], {k: expected[k] for k in shared_keys}, {k: actual[k] for k in shared_keys})
    native.expect(not report['isolation']['beforeDestroyOtherRead']['ok'], 'another host reads no blob URL of a live host')
    native.expect(not report['isolation']['reverseRead']['ok'] and report['isolation']['reverseImage'] == 'error',
                  'host A reads and loads no blob URL of host B')
    native.expect(report['isolation']['reverseSelfRead']['ok'], 'host B reads its own blob URL')
    native.expect(not report['isolation']['afterDestroyRead']['ok'], 'a destroyed host revokes its blob URLs')
    native.expect(report['teardown']['destroyPromise'] == 'invalidated', 'host destroy invalidates a read in flight')
    native.expect(report['teardown']['destroyReaderEvents'] == [], 'host destroy fires no FileReader event')
    report['differences'] = differences
    unqualified = sorted(set(differences) - set(qualified))
    native.expect(not unqualified, 'unqualified differences: ' + json.dumps({k: differences[k] for k in unqualified}, ensure_ascii=False))
    native.expect(not set(qualified) - set(differences), 'qualified differences that no longer occur: ' + str(sorted(set(qualified) - set(differences))))


def normalize(key, value):
    """Reduces both sides to the compared shape: a read is ok/type/bytes; a failed read is its failure."""
    value = json.loads(json.dumps(value))

    def read(entry):
        if not isinstance(entry, dict) or 'ok' not in entry:
            return entry
        if entry['ok']:
            return {k: entry[k] for k in ('ok', 'type', 'length', 'hex', 'checksum', 'value', 'v') if k in entry}
        return {'ok': False}

    if key in ('urlReads', 'revoked'):
        return {k: read(v) for k, v in value.items()}
    if key == 'unknown':
        return read(value)
    if key == 'isolation':
        return {k: read(v) if isinstance(v, dict) else v for k, v in value.items()}
    if key == 'teardown':
        return {k: read(v) if isinstance(v, dict) else v for k, v in value.items()}
    if key == 'file':
        value['urlRead'] = {'type': value['urlRead'].get('type'), 'text': value['urlRead'].get('text', bytes.fromhex(value['urlRead'].get('hex', '')).decode('utf-8'))}
        value.pop('readBytesStatus', None)
        return value
    if key == 'deleted':
        value['urlRead'] = read(value['urlRead'])
        value['text'] = {'ok': value['text']['ok'], 'name': value['text'].get('name')}
        return value
    return value


def verify(native_directory):
    cases = json.loads((FIXTURES / 'blob-urls-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'blob-urls-oracle.json').read_text(encoding='utf-8'))
    qualified_path = FIXTURES / 'blob-urls-qualified.json'
    qualified = json.loads(qualified_path.read_text(encoding='utf-8'))['differences'] if qualified_path.exists() else {}
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for feature in ['blob-urls', 'dom:FileReader', 'dom-constructor:FileReader', 'dom-binary-values']:
        native.expect(has(feature.encode()) == 1, feature + ' advertised')
    report = {'browser': oracle['browser'], 'platform': sys.platform}
    shared(native, cases, report)
    errors(native, report)
    file_backed(native, report)
    isolation(native, cases, report)
    teardown(native, report)
    try:
        compare(native, oracle, report, qualified)
    finally:
        if REPORT_PATH:
            Path(REPORT_PATH).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    report['qualified'] = sorted(qualified)
    report['assertions'] = native.assertions
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--report')
    args = parser.parse_args()
    global REPORT_PATH
    REPORT_PATH = args.report
    report = verify(args.native_directory)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f"PASS blob_urls: {report['assertions']} assertions, {len(report['qualified'])} qualified", flush=True)


if __name__ == '__main__':
    main()
