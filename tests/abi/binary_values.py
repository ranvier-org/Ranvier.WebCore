"""H11 binary value probe against an actual runtime directory. Replays the Chromium oracle
tests/fixtures/binary-values-oracle.json through the generated Blob, File and FileList members, rv_blob_read_bytes and
rv_file_list_create: blob parts, type normalization, line endings, slicing, File metadata, FileList through a file
input and FormData File entries. It also checks the null, thread, interface and capacity errors, and blobs, files and
lists held past rv_host_destroy."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from form_collections import Native, Case, EntryValue, EntryValues, Entries, P, I, U, utf8, span_text
from utf8_inputs import StringInput, string_input

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
OK, NULL_ARGUMENT, WRONG_THREAD, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -6, -9, -11
ABI = 54
BYTES_ARM, BLOB_ARM, STRING_ARM = 1, 2, 3
FILE_ARM = 1
TRANSPARENT, NATIVE = 0, 1
INT64_MAX = 0x7FFFFFFFFFFFFFFF
L = ctypes.c_int64


class ByteSpan(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Part(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', ByteSpan), ('arm1', P), ('arm2', ByteSpan)]


class Parts(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(Part))]


class BlobPropertyBag(ctypes.Structure):
    _fields_ = [('size', U), ('type', StringInput), ('endings', I)]


class FilePropertyBag(ctypes.Structure):
    _fields_ = [('size', U), ('type', StringInput), ('endings', I), ('last_modified', ctypes.POINTER(L))]


def native_endings(data):
    """The bytes of endings "native": every CR, LF and CRLF becomes the platform's line ending."""
    ending = b'\r\n' if sys.platform == 'win32' else b'\n'
    return data.replace(b'\r\n', b'\n').replace(b'\r', b'\n').replace(b'\n', ending)


class Binary:
    def __init__(self, native, case):
        self.n, self.case, self.document = native, case, case.document
        self.keep, self.handles = [], []

    def parts(self, values):
        """A BlobPart sequence: bytes for a BufferSource, str for a USVString (UTF-8), an int for a blob handle."""
        if values is None:
            return None
        items = (Part * max(len(values), 1))()
        for item, value in zip(items, values):
            item.present = 1
            if isinstance(value, (bytes, bytearray)):
                buffer = ctypes.create_string_buffer(bytes(value), max(len(value), 1))
                self.keep.append(buffer)
                item.tag, item.arm0 = BYTES_ARM, ByteSpan(ctypes.cast(buffer, P) if value else None, len(value))
            elif isinstance(value, str):
                data = value.encode('utf-8')
                buffer = ctypes.create_string_buffer(data, len(data) + 1)
                self.keep.append(buffer)
                item.tag, item.arm2 = STRING_ARM, ByteSpan(ctypes.cast(buffer, P), len(data))
            else:
                item.tag, item.arm1 = BLOB_ARM, value
        sequence = Parts(present=1, count=len(values), items=items if values else None)
        self.keep += [items, sequence]
        return ctypes.byref(sequence)

    def track(self, handle):
        if handle:
            self.handles.append(handle)
        return handle

    def blob(self, values=(), type=None, endings=None, status=OK):
        options = None
        if type is not None or endings is not None:
            options = BlobPropertyBag(size=ctypes.sizeof(BlobPropertyBag), type=string_input(type),
                                      endings=TRANSPARENT if endings is None else endings)
        result = P()
        actual = self.n.call('rv_dom_blob_create', [P, P, ctypes.POINTER(BlobPropertyBag), ctypes.POINTER(P)], self.document,
                             self.parts(None if values is None else list(values)), ctypes.byref(options) if options else None, ctypes.byref(result))
        self.n.expect(actual == status, f'Blob constructor status {actual}')
        return self.track(result.value)

    def file(self, values, name, type=None, last_modified=None, endings=None):
        holder = None if last_modified is None else L(last_modified)
        options = FilePropertyBag(size=ctypes.sizeof(FilePropertyBag), type=string_input(type),
                                  endings=TRANSPARENT if endings is None else endings,
                                  last_modified=None if holder is None else ctypes.pointer(holder))
        text, length = utf8(name)
        result = P()
        self.n.ok('rv_dom_file_create', [P, P, P, I, ctypes.POINTER(FilePropertyBag), ctypes.POINTER(P)], self.document,
                  self.parts(list(values)), text, length, ctypes.byref(options), ctypes.byref(result))
        self.n.expect(bool(result.value), 'File constructor result')
        return self.track(result.value)

    def slice(self, blob, start=0, end=INT64_MAX, content_type=''):
        text, length = utf8(content_type)
        result = P()
        self.n.ok('rv_dom_blob_slice', [P, L, L, P, I, ctypes.POINTER(P)], blob, start, end, text, length, ctypes.byref(result))
        return self.track(result.value)

    def read(self, blob):
        n = self.n
        length = L(-1)
        status = n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, None, 0, ctypes.byref(length))
        n.expect(status in (OK, BUFFER_TOO_SMALL), f'size query status {status}')
        n.expect(status == OK if length.value == 0 else status == BUFFER_TOO_SMALL, 'size query reports the byte count')
        buffer = ctypes.create_string_buffer(max(length.value, 1))
        written = L(-1)
        n.ok('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, buffer, length.value, ctypes.byref(written))
        n.expect(written.value == length.value, 'read length')
        return buffer.raw[:written.value]

    def describe(self, blob):
        n = self.n
        size = ctypes.c_uint64()
        n.ok('rv_dom_blob_get_size', [P, ctypes.POINTER(ctypes.c_uint64)], blob, ctypes.byref(size))
        data = self.read(blob)
        n.expect(len(data) == size.value, 'Blob.size equals the bytes read')
        result = {'size': size.value, 'type': n.text('rv_dom_blob_get_type', [P], blob), 'bytes': data.hex()}
        buffer, length = ctypes.create_string_buffer(4096), I()
        status = n.call('rv_dom_file_get_name', [P, P, I, ctypes.POINTER(I)], blob, buffer, len(buffer), ctypes.byref(length))
        if status == OK:
            result['name'] = buffer.raw[:length.value].decode('utf-8')
            modified = L()
            n.ok('rv_dom_file_get_last_modified', [P, ctypes.POINTER(L)], blob, ctypes.byref(modified))
            result['lastModified'] = modified.value
        else:
            n.expect(status == WRONG_INTERFACE, 'File.name of a Blob')
        return result

    def release_all(self):
        for handle in self.handles:
            self.n.bind('rv_dom_blob_release', None, [P])(handle)
        self.handles = []


def same(native, actual, expected, label, drop=()):
    expected = {k: v for k, v in expected.items() if k not in drop}
    actual = {k: v for k, v in actual.items() if k not in drop}
    native.expect(actual == expected, f'{label}: {actual} != {expected}')


def values(native, oracle, report):
    cases = oracle['cases']
    case = Case(native, '<form id=f><input id=i type=file name=upload></form>')
    b = Binary(native, case)
    try:
        inner = b.blob(['ab'])
        report['parts'] = b.describe(b.blob(['héllo', bytes([0, 1, 255]), inner, '�x'], type='Text/Plain'))
        same(native, report['parts'], cases['parts'], 'parts')
        report['empty'] = b.describe(b.blob(None))
        same(native, report['empty'], cases['empty'], 'absent parts')
        report['emptyParts'] = b.describe(b.blob([], type='a/b'))
        same(native, report['emptyParts'], cases['emptyParts'], 'empty parts')
        report['view'] = b.describe(b.blob([bytes([1, 2, 3, 4, 5])[1:4]]))
        same(native, report['view'], cases['view'], 'view bytes')
        report['emptyBytes'] = b.describe(b.blob([b'', '']))
        same(native, report['emptyBytes'], cases['empty'], 'empty byte and string parts')
        report['types'] = {}
        for key, expected in cases['types'].items():
            type_ = json.loads(key)
            report['types'][key] = native.text('rv_dom_blob_get_type', [P], b.blob([], type=type_))
            native.expect(report['types'][key] == expected, f'type {key}')
        source = bytes.fromhex(cases['endings']['transparent'])
        report['endings'] = {'transparent': b.read(b.blob(['a\nb\r\nc\rd'], endings=TRANSPARENT)).hex(),
                             'native': b.read(b.blob(['a\nb\r\nc\rd'], endings=NATIVE)).hex(),
                             'platform': sys.platform}
        native.expect(report['endings']['transparent'] == cases['endings']['transparent'], 'endings transparent')
        native.expect(report['endings']['native'] == native_endings(source).hex(), 'endings native on this platform')
        if sys.platform == 'win32':
            native.expect(report['endings']['native'] == cases['endings']['native'], 'endings native against Windows Chromium')
        digits = b.blob(['0123456789'], type='text/plain')
        report['slices'] = []
        for expected in cases['slices']:
            args = expected['args']
            if any(isinstance(a, float) and not float(a).is_integer() for a in args):
                continue  # [Clamp] conversion of a JavaScript number; the ABI takes int64 arguments.
            start = args[0] if len(args) > 0 and args[0] is not None else 0
            end = args[1] if len(args) > 1 and args[1] is not None else INT64_MAX
            content_type = args[2] if len(args) > 2 else ''
            actual = {'args': args, **b.describe(b.slice(digits, start, end, content_type))}
            report['slices'].append(actual)
            same(native, actual, expected, f'slice {args}')
        report['sliceOfSlice'] = b.describe(b.slice(b.slice(digits, 2, 8), 1, -1))
        same(native, report['sliceOfSlice'], cases['sliceOfSlice'], 'slice of slice')
        report['slicedFileIsBlob'] = 'name' not in b.describe(b.slice(b.file(['abc'], 'f'), 0, 2))
        native.expect(report['slicedFileIsBlob'], 'a File slice is a Blob')
        report['file'] = b.describe(b.file(['abc'], 'a/b.txt', type='TEXT/X', last_modified=1234))
        same(native, report['file'], cases['file'], 'File')
        report['fileNegative'] = b.describe(b.file([], 'n', last_modified=-5))
        same(native, report['fileNegative'], cases['fileNegative'], 'negative lastModified')
        before = int(time.time() * 1000)
        now = b.describe(b.file([], 'now'))
        report['fileDefaultLastModifiedNow'] = before - 1000 <= now['lastModified'] <= int(time.time() * 1000) + 1000
        native.expect(report['fileDefaultLastModifiedNow'] == cases['fileDefaultLastModifiedNow'], 'default lastModified is now')
        report['fileOfFile'] = b.describe(b.file([b.file(['xy'], 'inner', last_modified=1)], 'outer', last_modified=2))
        same(native, report['fileOfFile'], cases['fileOfFile'], 'File of a File')
        big = bytes((i * 31 + 7) & 255 for i in range(1 << 20))
        back = b.read(b.blob([big]))
        checksum = 0
        for value in back:
            checksum = (checksum * 33 + value) & 0xFFFFFFFF
        report['big'] = {'size': len(back), 'checksum': checksum}
        native.expect(report['big'] == cases['big'], 'one MiB checksum')
        forms(native, case, b, cases, report)
        errors(native, case, b, report)
    finally:
        b.release_all()
        case.close()


def entry_file(native, b, value):
    native.expect(value.tag == FILE_ARM and bool(value.arm0), 'File entry carries a handle')
    return b.describe(value.arm0), value.arm0


def forms(native, case, b, cases, report):
    n = native
    form, input_ = case.node('f'), case.node('i')
    files = P()
    n.ok('rv_dom_html_input_element_get_files', [P, ctypes.POINTER(P)], input_, ctypes.byref(files))
    length = U()
    n.ok('rv_dom_file_list_get_length', [P, ctypes.POINTER(U)], files.value, ctypes.byref(length))
    data = n.handle('rv_dom_dom_form_data_create', [P, P, P], case.document, form, None, nullable=False)
    name, name_length = utf8('upload')
    result = EntryValue()
    n.ok('rv_dom_dom_form_data_get', [P, P, I, ctypes.POINTER(EntryValue)], data, name, name_length, ctypes.byref(result))
    entry, _ = entry_file(n, b, result)
    n.bind('rv_dom_union_file_or_usv_string_nullable_release', None, [ctypes.POINTER(EntryValue)])(ctypes.byref(result))
    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
    entry.pop('lastModified')
    report['emptyFileInput'] = {'files': length.value, 'entry': entry, 'isFile': True}
    expected = dict(cases['emptyFileInput'])
    expected.pop('lastModifiedNow')
    same(n, report['emptyFileInput'], expected, 'empty file input entry')
    n.bind('rv_dom_file_list_release', None, [P])(files.value)

    one = b.file(['one'], 'one.txt', type='text/plain', last_modified=10)
    two = b.file([bytes([9, 8])], 'two.bin', last_modified=20)
    array = (P * 2)(one, two)
    created = P()
    n.ok('rv_file_list_create', [P, I, ctypes.POINTER(P)], array, 2, ctypes.byref(created))
    n.ok('rv_dom_html_input_element_set_files', [P, P], input_, created.value)
    n.bind('rv_dom_file_list_release', None, [P])(created.value)
    files = P()
    n.ok('rv_dom_html_input_element_get_files', [P, ctypes.POINTER(P)], input_, ctypes.byref(files))
    n.expect(files.value == created.value, 'input.files is the assigned FileList')
    n.ok('rv_dom_file_list_get_length', [P, ctypes.POINTER(U)], files.value, ctypes.byref(length))
    items = []
    for index in range(3):
        item = P()
        n.ok('rv_dom_file_list_item', [P, U, ctypes.POINTER(P)], files.value, index, ctypes.byref(item))
        items.append(b.track(item.value))
    again = P()
    n.ok('rv_dom_file_list_item', [P, U, ctypes.POINTER(P)], files.value, 0, ctypes.byref(again))
    b.track(again.value)
    n.bind('rv_dom_file_list_release', None, [P])(files.value)
    report['fileList'] = {'length': length.value, 'item0': b.describe(items[0]), 'item1': b.describe(items[1]),
                          'item2': items[2], 'same': again.value == items[0]}
    same(n, report['fileList'], cases['fileList'], 'FileList')
    n.expect(items[0] == one and items[1] == two, 'FileList items keep the files given')

    data = n.handle('rv_dom_dom_form_data_create', [P, P, P], case.document, form, None, nullable=False)
    entries = Entries()
    n.ok('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, case.document, ctypes.byref(entries))
    report['formFromInput'] = []
    for i in range(entries.count):
        described, handle = entry_file(n, b, entries.items[i].value)
        n.expect(handle == [one, two][i], 'form entry keeps the File identity')
        report['formFromInput'].append({'name': span_text(entries.items[i].key), 'value': described})
    n.bind('rv_dom_sequence_pair_usv_string_and_union_file_or_usv_string_release', None, [ctypes.POINTER(Entries)])(ctypes.byref(entries))
    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
    n.expect(report['formFromInput'] == cases['formFromInput'], 'FormData from a file input')

    data = n.handle('rv_dom_dom_form_data_create', [P, P, P], case.document, None, None, nullable=False)
    plain = b.blob(['p'], type='text/p')

    def add(op, key, blob, filename):
        text, text_length = utf8(key)
        file_text, file_length = (None, -1) if filename is None else utf8(filename)
        n.ok(f'rv_dom_dom_form_data_{op}_3', [P, P, I, P, P, I], data, text, text_length, blob, file_text, file_length)

    add('append', 'a', plain, None)
    add('append', 'b', plain, 'named.txt')
    add('append', 'c', one, None)
    add('append', 'd', one, 'renamed')
    add('set', 'e', b.blob([]), None)
    report['formData'] = {}
    modified = {}
    for key in 'abcde':
        text, text_length = utf8(key)
        result = EntryValue()
        n.ok('rv_dom_dom_form_data_get', [P, P, I, ctypes.POINTER(EntryValue)], data, text, text_length, ctypes.byref(result))
        described, handle = entry_file(n, b, result)
        modified[key] = described.pop('lastModified')
        report['formData'][key] = {**described, 'isFile': True, 'sameAsInput': handle == one}
        n.bind('rv_dom_union_file_or_usv_string_nullable_release', None, [ctypes.POINTER(EntryValue)])(ctypes.byref(result))
    report['formData']['convertedLastModifiedNow'] = abs(modified['a'] - int(time.time() * 1000)) < 60000
    report['formData']['copiedLastModified'] = modified['d']
    values = EntryValues()
    text, text_length = utf8('a')
    n.ok('rv_dom_dom_form_data_get_all', [P, P, I, ctypes.POINTER(EntryValues)], data, text, text_length, ctypes.byref(values))
    n.expect(values.count == 1 and values.items[0].tag == FILE_ARM and bool(values.items[0].arm0), 'getAll File handle')
    n.bind('rv_dom_sequence_file_or_usv_string_release', None, [ctypes.POINTER(EntryValues)])(ctypes.byref(values))
    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
    n.expect(report['formData'] == cases['formData'], f"FormData File entries: {report['formData']}")


def errors(native, case, b, report):
    n = native
    blob = b.blob(['abc'])
    length = L(-1)
    buffer = ctypes.create_string_buffer(2)
    n.expect(n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, buffer, 2, ctypes.byref(length)) == BUFFER_TOO_SMALL and length.value == 3, 'short buffer')
    n.expect(n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], None, buffer, 2, ctypes.byref(length)) == NULL_ARGUMENT, 'NULL blob')
    n.expect(n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, None, 2, ctypes.byref(length)) == NULL_ARGUMENT, 'NULL buffer with capacity')
    n.expect(n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, buffer, -1, ctypes.byref(length)) == NULL_ARGUMENT, 'negative capacity')
    n.expect(n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, buffer, 2, None) == NULL_ARGUMENT, 'NULL length')
    array = (P * 1)(blob)
    n.expect(n.call('rv_file_list_create', [P, I, ctypes.POINTER(P)], array, 1, ctypes.byref(P())) == WRONG_INTERFACE, 'FileList of a Blob')
    n.expect(n.call('rv_file_list_create', [P, I, ctypes.POINTER(P)], (P * 1)(None), 1, ctypes.byref(P())) == NULL_ARGUMENT, 'FileList of NULL')
    n.expect(n.call('rv_file_list_create', [P, I, ctypes.POINTER(P)], None, 1, ctypes.byref(P())) == NULL_ARGUMENT, 'NULL files with a count')
    empty = P()
    n.ok('rv_file_list_create', [P, I, ctypes.POINTER(P)], None, 0, ctypes.byref(empty))
    count = U(9)
    n.ok('rv_dom_file_list_get_length', [P, ctypes.POINTER(U)], empty.value, ctypes.byref(count))
    n.expect(count.value == 0, 'empty FileList')
    n.bind('rv_dom_file_list_release', None, [P])(empty.value)
    n.expect(n.call('rv_dom_file_get_last_modified', [P, ctypes.POINTER(L)], blob, ctypes.byref(L())) == WRONG_INTERFACE, 'lastModified of a Blob')
    form = case.node('f')
    n.expect(n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], form, None, None, ctypes.byref(P())) == WRONG_INTERFACE, 'Blob with an element context')
    bad = bytes([0xed, 0xa0, 0x80])
    holder = ctypes.create_string_buffer(bad, 4)
    item = (Part * 1)()
    item[0].present, item[0].tag, item[0].arm2 = 1, STRING_ARM, ByteSpan(ctypes.cast(holder, P), 3)
    sequence = Parts(present=1, count=1, items=item)
    status = n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], case.document, ctypes.byref(sequence), None, ctypes.byref(P()))
    n.expect(status == NULL_ARGUMENT, f'invalid UTF-8 string part rejected: {status}')
    item[0].tag, item[0].arm0 = BYTES_ARM, ByteSpan(None, 2)
    n.expect(n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], case.document, ctypes.byref(sequence), None, ctypes.byref(P())) == NULL_ARGUMENT, 'NULL bytes with a length')
    item[0].arm0 = ByteSpan(None, -1)
    n.expect(n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], case.document, ctypes.byref(sequence), None, ctypes.byref(P())) == NULL_ARGUMENT, 'negative byte length')
    item[0].tag = 9
    n.expect(n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], case.document, ctypes.byref(sequence), None, ctypes.byref(P())) == UNSUPPORTED, 'unknown part tag')
    options = BlobPropertyBag(size=ctypes.sizeof(BlobPropertyBag), type=string_input(None), endings=7)
    n.expect(n.call('rv_dom_blob_create', [P, P, ctypes.POINTER(BlobPropertyBag), ctypes.POINTER(P)], case.document, None, ctypes.byref(options), ctypes.byref(P())) == UNSUPPORTED, 'endings out of range')
    outcome = {}

    def worker():
        outcome['read'] = n.call('rv_blob_read_bytes', [P, P, L, ctypes.POINTER(L)], blob, buffer, 2, ctypes.byref(L()))
        outcome['list'] = n.call('rv_file_list_create', [P, I, ctypes.POINTER(P)], None, 0, ctypes.byref(P()))
        outcome['create'] = n.call('rv_dom_blob_create', [P, P, P, ctypes.POINTER(P)], case.document, None, None, ctypes.byref(P()))
        outcome['size'] = n.call('rv_dom_blob_get_size', [P, ctypes.POINTER(ctypes.c_uint64)], blob, ctypes.byref(ctypes.c_uint64()))

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    n.expect(all(status == WRONG_THREAD for status in outcome.values()), f'wrong thread {outcome}')
    report['errors'] = 'checked'


def held_past_destroy(native, report):
    n = native
    case = Case(n, '<input id=i type=file>')
    b = Binary(n, case)
    blob = b.blob(['kept'], type='text/plain')
    file = b.file([blob], 'kept.txt', last_modified=7)
    part = b.slice(file, 1, 3)
    created = P()
    n.ok('rv_file_list_create', [P, I, ctypes.POINTER(P)], (P * 1)(file), 1, ctypes.byref(created))
    n.ok('rv_dom_html_input_element_set_files', [P, P], case.node('i'), created.value)
    case.close()
    report['heldPastDestroy'] = {'blob': b.describe(blob), 'file': b.describe(file), 'slice': b.describe(part)}
    count = U()
    n.ok('rv_dom_file_list_get_length', [P, ctypes.POINTER(U)], created.value, ctypes.byref(count))
    n.expect(count.value == 1, 'FileList held past destroy')
    n.bind('rv_dom_file_list_release', None, [P])(created.value)
    expected = {'blob': {'size': 4, 'type': 'text/plain', 'bytes': b'kept'.hex()},
                'file': {'size': 4, 'type': '', 'bytes': b'kept'.hex(), 'name': 'kept.txt', 'lastModified': 7},
                'slice': {'size': 2, 'type': '', 'bytes': b'ep'.hex()}}
    n.expect(report['heldPastDestroy'] == expected, f"held past destroy: {report['heldPastDestroy']}")
    b.release_all()


def verify(native_directory):
    oracle = json.loads((FIXTURES / 'binary-values-oracle.json').read_text(encoding='utf-8'))
    native = Native(native_directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for feature in ['dom-binary-values', 'dom:Blob', 'dom:File', 'dom:FileList']:
        native.expect(has(feature.encode()) == 1, feature + ' advertised')
    report = {'browser': oracle['browser'], 'platform': sys.platform}
    values(native, oracle, report)
    held_past_destroy(native, report)
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
    print(f"PASS binary_values: {report['assertions']} assertions", flush=True)


if __name__ == '__main__':
    main()
