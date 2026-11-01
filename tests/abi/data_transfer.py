"""I07/T09/T04 DataTransfer probe against an actual runtime directory. Replays tests/fixtures/data-transfer-cases.json
through the generated DataTransfer, DataTransferItemList, DataTransferItem, DragEvent, ClipboardEvent and InputEvent
members and the hand-written drop, clipboard, drag-out and range-replacement exports, and compares each snapshot with
the Chromium oracle tests/fixtures/data-transfer-oracle.json. Every difference must be listed in
tests/fixtures/data-transfer-qualified.json. It also checks the store mode of each event phase, permission denial,
reserved and unavailable formats, the null, thread and interface errors, and files held past rv_host_destroy."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/fixtures'
P, I, U = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, BUFFER_TOO_SMALL, UNSUPPORTED, WRONG_INTERFACE = 0, -1, -2, -3, -6, -9, -11
WRONG_HOST = -12
ABI = 59
MOUSE_MOVE, MOUSE_DOWN, MOUSE_UP, BUTTON_LEFT, BUTTON_NONE = 0, 1, 2, 0, -1
DRAG_OVER, DRAG_LEAVE, DRAG_DROP, DRAG_APP = 0, 1, 2, 0
CLIPBOARD_APP, EDIT_COPY, EDIT_CUT, EDIT_PASTE, EDIT_PASTE_PLAIN, EDIT_SELECT_ALL = 0, 0, 1, 2, 3, 4
BYTES_ARM = 1
EVENT = ctypes.CFUNCTYPE(I, P, P)
READ = ctypes.CFUNCTYPE(None, P, P)
WRITE = ctypes.CFUNCTYPE(None, P, ctypes.c_char_p, P, I, I)
WRITE_FILE = ctypes.CFUNCTYPE(None, P, P, I)
DRAG_START = ctypes.CFUNCTYPE(None, P, P, I, I, I)


class Span(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Strings(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(Span))]


class Ranges(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(P))]


class ByteSpan(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class Part(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', ByteSpan), ('arm1', P), ('arm2', ByteSpan)]


class Parts(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(Part))]


class StringInput(ctypes.Structure):
    _fields_ = [('present', I), ('data', P), ('length', I)]


class FilePropertyBag(ctypes.Structure):
    _fields_ = [('size', U), ('type', StringInput), ('endings', I), ('last_modified', P)]


class InputEventInit(ctypes.Structure):
    _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('detail', I), ('data', StringInput),
                ('is_composing', I), ('input_type', StringInput)]


class Probe:
    def __init__(self, directory):
        directory = Path(directory).resolve()
        if sys.platform == 'win32':
            os.add_dll_directory(str(directory))
        name = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
        self.library = ctypes.CDLL(str(directory / name))
        self.assertions = 0
        self.keep = []

    def expect(self, condition, label):
        self.assertions += 1
        if not condition:
            raise AssertionError(label)

    def fn(self, name, result, arguments):
        return bind_utf8(self.library, name, result, arguments)

    def call(self, name, arguments, *values):
        return self.fn(name, I, arguments)(*values)

    def ok(self, name, arguments, *values):
        status = self.call(name, arguments, *values)
        self.expect(status == OK, f'{name}: status {status}')

    def text(self, name, arguments, *values):
        buffer, length = ctypes.create_string_buffer(16384), I()
        self.ok(name, arguments + [P, I, ctypes.POINTER(I)], *values, buffer, len(buffer), ctypes.byref(length))
        return None if length.value < 0 else buffer.raw[:length.value].decode('utf-8')

    def handle(self, name, arguments, *values):
        result = P()
        self.ok(name, arguments + [ctypes.POINTER(P)], *values, ctypes.byref(result))
        return result.value

    def buffer(self, data):
        holder = ctypes.create_string_buffer(data, max(len(data), 1))
        self.keep.append(holder)
        return holder

    # Files of H11.
    def file(self, document, name, data, content_type):
        bits = self.buffer(data)
        items = (Part * 1)()
        items[0].present, items[0].tag, items[0].arm0 = 1, BYTES_ARM, ByteSpan(ctypes.cast(bits, P), len(data))
        parts = Parts(1, 1, items)
        kind = self.buffer(content_type.encode())
        bag = FilePropertyBag(ctypes.sizeof(FilePropertyBag), StringInput(1, ctypes.cast(kind, P), len(content_type)), 0, None)
        self.keep += [items, parts, bag]
        return self.handle('rv_dom_file_create', [P, P, Utf8, P], document, ctypes.byref(parts), name, ctypes.byref(bag))

    def blob(self, document):
        return self.handle('rv_dom_blob_create', [P, P, P], document, None, None)

    def describe_file(self, file):
        size = ctypes.c_uint64()
        self.ok('rv_dom_blob_get_size', [P, ctypes.POINTER(ctypes.c_uint64)], file, ctypes.byref(size))
        return [self.text('rv_dom_file_get_name', [P], file), self.text('rv_dom_blob_get_type', [P], file), size.value]

    def file_bytes(self, file):
        length = ctypes.c_int64()
        status = self.call('rv_blob_read_bytes', [P, P, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64)], file, None, 0, ctypes.byref(length))
        self.expect(status in (OK, BUFFER_TOO_SMALL), 'blob size query')
        data = ctypes.create_string_buffer(max(length.value, 1))
        self.ok('rv_blob_read_bytes', [P, P, ctypes.c_int64, ctypes.POINTER(ctypes.c_int64)], file, data, length.value, ctypes.byref(length))
        return data.raw[:length.value]

    # DataTransfer snapshots, in the shape the Chromium oracle writes.
    def strings(self, name, target, document):
        sequence = Strings()
        self.ok(name, [P, P, ctypes.POINTER(Strings)], target, document, ctypes.byref(sequence))
        values = [ctypes.string_at(sequence.items[i].data, sequence.items[i].length).decode('utf-8') if sequence.items[i].length > 0 else ''
                  for i in range(sequence.count)]
        self.fn('rv_dom_sequence_dom_string_release', None, [ctypes.POINTER(Strings)])(ctypes.byref(sequence))
        return values

    def get_data(self, transfer, document, kind):
        return self.text('rv_dom_data_transfer_get_data', [P, P, Utf8], transfer, document, kind)

    def files(self, transfer, document, keep=None):
        files = self.handle('rv_dom_data_transfer_get_files', [P, P], transfer, document)
        self.expect(bool(files), 'files is never null')
        length = U()
        self.ok('rv_dom_file_list_get_length', [P, ctypes.POINTER(U)], files, ctypes.byref(length))
        result = []
        for index in range(length.value):
            file = self.handle('rv_dom_file_list_item', [P, U], files, index)
            result.append(self.describe_file(file))
            if keep is not None:
                keep.append(file)
            else:
                self.fn('rv_dom_blob_release', None, [P])(file)
        self.fn('rv_dom_file_list_release', None, [P])(files)
        return result

    def items(self, transfer, document):
        items = self.handle('rv_dom_data_transfer_get_items', [P, P], transfer, document)
        length = I()
        self.ok('rv_dom_data_transfer_item_list_get_length', [P, ctypes.POINTER(I)], items, ctypes.byref(length))
        result = []
        for index in range(length.value):
            item = self.handle('rv_dom_data_transfer_item_list_item', [P, U], items, index)
            result.append([self.text('rv_dom_data_transfer_item_get_kind', [P], item), self.text('rv_dom_data_transfer_item_get_type', [P], item)])
            self.fn('rv_dom_data_transfer_item_release', None, [P])(item)
        self.fn('rv_dom_data_transfer_item_list_release', None, [P])(items)
        return result

    def snapshot(self, transfer, document):
        if not transfer:
            return None
        return {'types': self.strings('rv_dom_data_transfer_get_types', transfer, document),
                'text': self.get_data(transfer, document, 'text/plain'), 'html': self.get_data(transfer, document, 'text/html'),
                'uri': self.get_data(transfer, document, 'text/uri-list'), 'files': self.files(transfer, document),
                'items': self.items(transfer, document), 'dropEffect': self.text('rv_dom_data_transfer_get_drop_effect', [P], transfer),
                'effectAllowed': self.text('rv_dom_data_transfer_get_effect_allowed', [P], transfer)}

    def write_attempt(self, transfer, document):
        """Whether setData, items.add and clearData change the store: true only in read/write mode."""
        before = self.strings('rv_dom_data_transfer_get_types', transfer, document)
        self.ok('rv_dom_data_transfer_set_data', [P, P, Utf8, Utf8], transfer, document, 'text/x-probe', 'w')
        items = self.handle('rv_dom_data_transfer_get_items', [P, P], transfer, document)
        added = self.handle('rv_dom_data_transfer_item_list_add_2', [P, P, Utf8, Utf8], items, document, 'w2', 'text/uri-list')
        if added:
            self.fn('rv_dom_data_transfer_item_release', None, [P])(added)
        self.fn('rv_dom_data_transfer_item_list_release', None, [P])(items)
        after = self.strings('rv_dom_data_transfer_get_types', transfer, document)
        return {'setData': 'text/x-probe' in after and 'text/x-probe' not in before, 'itemsAdd': bool(added)}


def event_record(n, event, document, getter, extra=None):
    transfer = n.handle(getter, [P], event) if getter else None
    record = {'interface': n.text('rv_dom_event_get_interface_name', [P], event), 'dt': n.snapshot(transfer, document)}
    if extra:
        record.update(extra(event))
    return record, transfer


def run(directory, evidence):
    n = Probe(directory)
    spec = json.loads((FIXTURES / 'data-transfer-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'data-transfer-oracle.json').read_text(encoding='utf-8'))
    qualified = json.loads((FIXTURES / 'data-transfer-qualified.json').read_text(encoding='utf-8'))
    n.expect(n.fn('rv_abi_version', I, [])() == ABI, f'ABI {ABI}')
    has = n.fn('rv_abi_has', I, [ctypes.c_char_p])
    for name in ['dom:DataTransfer', 'dom:DataTransferItemList', 'dom:DataTransferItem', 'dom:DragEvent', 'dom:ClipboardEvent',
                 'clipboard-files', 'range-replacement', 'dom-constructor:DataTransfer', 'dom-constructor:InputEvent']:
        n.expect(has(name.encode()) == 1, name + ' advertised')
    n.expect(has(b'data-transfer-files') == (0 if sys.platform.startswith('linux') else 1), 'data-transfer-files where drops carry files')
    results = {}
    host_create = n.fn('rv_host_create', P, [I, I])
    host_destroy = n.fn('rv_host_destroy', None, [P])
    load = n.fn('rv_host_load_html', I, [P, Utf8])
    get = n.fn('rv_document_get_element_by_id', P, [P, Utf8])
    release_node = n.fn('rv_node_release', None, [P])
    listen = n.fn('rv_node_add_event_listener', P, [P, Utf8, I, EVENT, P])
    remove = n.fn('rv_listener_remove', None, [P])
    mouse = n.fn('rv_host_mouse', I, [P, I, I, I, I, I, I])
    drag = n.fn('rv_host_drag', I, [P, I, I, I, I, P, I])
    edit = n.fn('rv_host_edit', I, [P, I])
    release_transfer = n.fn('rv_dom_data_transfer_release', None, [P])
    release_blob = n.fn('rv_dom_blob_release', None, [P])

    host = host_create(*spec['viewport'])
    n.expect(bool(host), 'host')
    n.expect(load(host, spec['markup']) == OK, 'load')
    document = n.fn('rv_host_document', P, [P])(host)
    n.fn('rv_host_update', I, [P])(host)
    target, editable, source, image = (get(host, name) for name in ('t', 'e', 's', 'img'))
    for node in (target, editable, source, image):
        n.expect(bool(node), "element " + str([target, editable, source, image]))
    held, listeners, log = [], [], []

    def on(node, kind, getter, cancel=False, extra=None, during=None):
        def callback(context, event):
            record, transfer = event_record(n, event, document, getter, extra)
            record['type'] = kind
            if during and transfer:
                record.update(during(transfer))
            if transfer:
                held.append((kind, transfer))
            if cancel:
                n.ok('rv_dom_event_prevent_default', [P], event)
            log.append(record)
            return 0
        holder = EVENT(callback)
        n.keep.append(holder)
        listeners.append(listen(node, kind, 0, holder, None))

    def after():
        result = {kind: n.snapshot(transfer, document) for kind, transfer in held}
        for _, transfer in held:
            release_transfer(transfer)
        held.clear()
        return result

    def inputs(event):
        ranges = Ranges()
        n.ok('rv_dom_input_event_get_target_ranges', [P, ctypes.POINTER(Ranges)], event, ctypes.byref(ranges))
        offsets = []
        for index in range(ranges.count):
            start, end = U(), U()
            n.ok('rv_dom_abstract_range_get_start_offset', [P, ctypes.POINTER(U)], ranges.items[index], ctypes.byref(start))
            n.ok('rv_dom_abstract_range_get_end_offset', [P, ctypes.POINTER(U)], ranges.items[index], ctypes.byref(end))
            offsets.append([start.value, end.value])
        n.fn('rv_dom_sequence_static_range_release', None, [ctypes.POINTER(Ranges)])(ctypes.byref(ranges))
        return {'inputType': n.text('rv_dom_input_event_get_input_type', [P], event),
                'data': n.text('rv_dom_input_event_get_data', [P], event), 'ranges': offsets}

    # 1. Constructed: the object model alone.
    transfer = n.handle('rv_dom_data_transfer_create', [P], document)
    constructed = {'initial': {'dropEffect': n.text('rv_dom_data_transfer_get_drop_effect', [P], transfer),
                               'effectAllowed': n.text('rv_dom_data_transfer_get_effect_allowed', [P], transfer),
                               'types': n.strings('rv_dom_data_transfer_get_types', transfer, document)}}
    for value in ('bogus', 'link'):
        n.ok('rv_dom_data_transfer_set_drop_effect', [P, Utf8], transfer, value)
        n.ok('rv_dom_data_transfer_set_effect_allowed', [P, Utf8], transfer, 'copyMove' if value == 'link' else value)
        constructed[value] = [n.text('rv_dom_data_transfer_get_drop_effect', [P], transfer), n.text('rv_dom_data_transfer_get_effect_allowed', [P], transfer)]
    for kind, value in (('Text', 'a'), ('text/html', '<b>h</b>'), ('application/x-custom', 'c')):
        n.ok('rv_dom_data_transfer_set_data', [P, P, Utf8, Utf8], transfer, document, kind, value)
    constructed['types'] = n.strings('rv_dom_data_transfer_get_types', transfer, document)
    constructed['text'] = n.get_data(transfer, document, 'text/plain')
    constructed['url'] = n.get_data(transfer, document, 'URL')
    items = n.handle('rv_dom_data_transfer_get_items', [P, P], transfer, document)
    z = n.file(document, 'z.txt', b'zz', 'text/plain')
    item = n.handle('rv_dom_data_transfer_item_list_add_1', [P, P], items, z)
    n.expect(bool(item), 'items.add(file) returns an item')
    same = n.handle('rv_dom_data_transfer_item_get_as_file', [P], item)
    n.expect(same == z, 'getAsFile returns the added File itself')
    release_blob(same)
    n.fn('rv_dom_data_transfer_item_release', None, [P])(item)
    constructed['afterFile'] = {'types': n.strings('rv_dom_data_transfer_get_types', transfer, document),
                                'items': n.items(transfer, document), 'files': [f[0] for f in n.files(transfer, document)]}
    duplicate = n.call('rv_dom_data_transfer_item_list_add_2', [P, P, Utf8, Utf8, ctypes.POINTER(P)], items, document, 'dup', 'text/plain', ctypes.byref(P()))
    constructed['dup'] = n.text('rv_last_exception', [I], 0) if duplicate == DOM_EXCEPTION else 'no throw'
    n.ok('rv_dom_data_transfer_item_list_remove', [P, U], items, 0)
    constructed['removed'] = n.strings('rv_dom_data_transfer_get_types', transfer, document)
    n.ok('rv_dom_data_transfer_clear_data', [P, Utf8], transfer, 'text/html')
    constructed['cleared'] = n.strings('rv_dom_data_transfer_get_types', transfer, document)
    n.ok('rv_dom_data_transfer_clear_data', [P, Utf8], transfer, None)
    constructed['clearAll'] = {'types': n.strings('rv_dom_data_transfer_get_types', transfer, document), 'files': len(n.files(transfer, document))}
    n.ok('rv_dom_data_transfer_item_list_clear', [P], items)
    constructed['itemsClear'] = {'types': n.strings('rv_dom_data_transfer_get_types', transfer, document), 'files': len(n.files(transfer, document))}
    n.fn('rv_dom_data_transfer_item_list_release', None, [P])(items)
    release_transfer(transfer)
    results['constructed'] = constructed

    # 2. A drop of strings and files: protected while over the target, read-only at drop, unreadable afterwards.
    case = spec['drop']
    n.ok('rv_host_set_drag', [P, I], host, DRAG_APP)
    data = n.fn('rv_drag_data_create', P, [])()
    for kind, value in case['strings']:
        n.ok('rv_drag_data_add', [P, ctypes.c_char_p, Utf8], data, kind.encode(), value)
    sources = []
    for name, content, kind in case['files']:
        file = n.file(document, name, content.encode('utf-8'), kind)
        sources.append(file)
        n.ok('rv_drag_data_add_file', [P, P], data, file)
    for kind in ('dragenter', 'dragover', 'dragleave', 'drop'):
        on(target, kind, 'rv_dom_drag_event_get_data_transfer', cancel=kind != 'dragleave',
           during=(lambda dt: {'write': n.write_attempt(dt, document)}) if kind in ('dragover', 'drop') else None)
    x, y = case['point']
    over = drag(host, DRAG_OVER, x, y, case['allowed'], data, 0)
    dropped = drag(host, DRAG_DROP, x, y, case['allowed'], data, 0)
    n.fn('rv_drag_data_release', None, [P])(data)
    results['drop'] = {'over': over, 'dropped': dropped, 'log': list(log), 'after': after()}
    log.clear()
    for listener in listeners:
        remove(listener)
    listeners.clear()

    # Files read from the drop stay valid after the event and past the host: read them again at the end.
    files_handle = []
    drop_files, drop_types = [], []

    def keep_files(context, event):
        dt = n.handle('rv_dom_drag_event_get_data_transfer', [P], event)
        drop_files.extend(n.files(dt, document, files_handle))
        drop_types.extend(n.strings('rv_dom_data_transfer_get_types', dt, document))
        release_transfer(dt)
        n.ok('rv_dom_event_prevent_default', [P], event)
        return 0
    keeper = EVENT(keep_files)
    n.keep.append(keeper)
    accept = EVENT(lambda c, e: n.call('rv_dom_event_prevent_default', [P], e) and 0)
    n.keep.append(accept)
    listeners.append(listen(target, 'dragover', 0, accept, None))
    listeners.append(listen(target, 'drop', 0, keeper, None))
    data = n.fn('rv_drag_data_create', P, [])()
    for file in sources:
        n.ok('rv_drag_data_add_file', [P, P], data, file)
    drag(host, DRAG_DROP, x, y, case['allowed'], data, 0)
    n.fn('rv_drag_data_release', None, [P])(data)
    for listener in listeners:
        remove(listener)
    listeners.clear()
    if sys.platform.startswith('linux'):
        # KNOWN BUG https://github.com/ranvier-org/Ranvier.WebCore/issues/156: DataTransfer::allowsFileAccess() is false for every GTK/WPE drag.
        n.expect(drop_files == [] and 'Files' not in drop_types, 'linux drop exposes no files: ' + str(drop_types))
    else:
        n.expect(drop_files == [[name, kind, len(content.encode())] for name, content, kind in case['files']], 'files kept from the drop')

    # Reserved and unavailable formats are explicit.
    data = n.fn('rv_drag_data_create', P, [])()
    reserved = {'dragFiles': n.call('rv_drag_data_add', [P, ctypes.c_char_p, Utf8], data, b'fIlEs', 'x'),
                'dragBlob': n.call('rv_drag_data_add_file', [P, P], data, n.blob(document)),
                'dragNull': n.call('rv_drag_data_add_file', [P, P], data, None)}
    n.fn('rv_drag_data_release', None, [P])(data)

    # 3. Paste: strings and an image file, the beforeinput payload, and denial.
    case = spec['paste']
    n.ok('rv_host_set_clipboard', [P, I, WRITE, READ, P], host, CLIPBOARD_APP, WRITE(), READ(), None)
    image_file = n.file(document, case['file'][0], bytes.fromhex(case['file'][2]), case['file'][1])
    mode = {'deny': False}
    offer_status = []

    def read(context, request):
        if mode['deny']:
            offer_status.append(n.call('rv_clipboard_deny', [P], request))
            return
        for kind, value in case['strings']:
            offer_status.append(n.call('rv_clipboard_offer', [P, ctypes.c_char_p, Utf8], request, kind.encode(), value))
        offer_status.append(n.call('rv_clipboard_offer_file', [P, P], request, image_file))
        offer_status.append(n.call('rv_clipboard_offer', [P, ctypes.c_char_p, Utf8], request, b'Files', 'x'))
        offer_status.append(n.call('rv_clipboard_offer_file', [P, P], request, n.blob(document)))
    copied = []

    def write(context, kind, value, length, first):
        copied.append(['string', kind.decode(), ctypes.string_at(value, length).decode('utf-8'), first])

    def write_file(context, file, first):
        copied.append(['file', *n.describe_file(file), first])
    reader, writer, file_writer = READ(read), WRITE(write), WRITE_FILE(write_file)
    n.keep += [reader, writer, file_writer]
    n.ok('rv_host_set_clipboard', [P, I, WRITE, READ, P], host, CLIPBOARD_APP, writer, reader, None)
    n.ok('rv_host_set_clipboard_file_write', [P, WRITE_FILE, P], host, file_writer, None)
    on(editable, 'paste', 'rv_dom_clipboard_event_get_clipboard_data', during=lambda dt: {'write': n.write_attempt(dt, document)})
    on(editable, 'beforeinput', 'rv_dom_input_event_get_data_transfer', extra=inputs)
    on(editable, 'input', 'rv_dom_input_event_get_data_transfer', extra=inputs)
    n.ok('rv_element_focus', [P], editable)
    n.expect(edit(host, EDIT_SELECT_ALL) == 1, 'select all')
    pasted = edit(host, EDIT_PASTE)
    results['paste'] = {'status': pasted, 'offers': list(offer_status), 'log': list(log), 'after': after(),
                        'html': n.text('rv_dom_element_get_inner_html', [P], editable)}
    log.clear()
    mode['deny'] = True
    offer_status.clear()
    denied = edit(host, EDIT_PASTE)
    results['deny'] = {'status': denied, 'exception': n.text('rv_last_exception', [I], 0) if denied == DOM_EXCEPTION else None,
                       'offers': list(offer_status), 'events': [e['type'] for e in log],
                       'html': n.text('rv_dom_element_get_inner_html', [P], editable)}
    log.clear()
    for listener in listeners:
        remove(listener)
    listeners.clear()

    # 4. Copy: the page's strings and files reach the app, in read/write mode.
    case = spec['copy']
    copy_file = n.file(document, case['file'][0], case['file'][2].encode(), case['file'][1])

    def on_copy(context, event):
        dt = n.handle('rv_dom_clipboard_event_get_clipboard_data', [P], event)
        n.ok('rv_dom_data_transfer_set_data', [P, P, Utf8, Utf8], dt, document, 'text/plain', case['text'])
        items = n.handle('rv_dom_data_transfer_get_items', [P, P], dt, document)
        added = n.handle('rv_dom_data_transfer_item_list_add_1', [P, P], items, copy_file)
        n.expect(bool(added), 'copy items.add(file)')
        n.fn('rv_dom_data_transfer_item_release', None, [P])(added)
        n.fn('rv_dom_data_transfer_item_list_release', None, [P])(items)
        log.append({'type': 'copy', 'interface': n.text('rv_dom_event_get_interface_name', [P], event), 'dt': n.snapshot(dt, document)})
        held.append(('copy', dt))
        n.ok('rv_dom_event_prevent_default', [P], event)
        return 0
    copier = EVENT(on_copy)
    n.keep.append(copier)
    listeners.append(listen(editable, 'copy', 0, copier, None))
    copied.clear()
    status = edit(host, EDIT_COPY)
    results['copy'] = {'status': status, 'log': list(log), 'after': after(), 'written': list(copied)}
    log.clear()
    for listener in listeners:
        remove(listener)
    listeners.clear()

    # 5. A drag out of the page: page files, setDragImage, and the drag fed back as a drop.
    case = spec['dragOut']

    def on_start(context, event):
        dt = n.handle('rv_dom_drag_event_get_data_transfer', [P], event)
        n.ok('rv_dom_data_transfer_set_data', [P, P, Utf8, Utf8], dt, document, 'text/plain', case['text'])
        items = n.handle('rv_dom_data_transfer_get_items', [P, P], dt, document)
        added = n.handle('rv_dom_data_transfer_item_list_add_1', [P, P], items, copy_file)
        n.fn('rv_dom_data_transfer_item_release', None, [P])(added)
        n.fn('rv_dom_data_transfer_item_list_release', None, [P])(items)
        n.ok('rv_dom_data_transfer_set_drag_image', [P, P, I, I], dt, image, *case['imageOffset'])
        n.ok('rv_dom_data_transfer_set_effect_allowed', [P, Utf8], dt, 'copyLink')
        release_transfer(dt)
        return 0
    starter = EVENT(on_start)
    n.keep.append(starter)
    listeners.append(listen(source, 'dragstart', 0, starter, None))
    started = []

    def drag_started(context, handle, px, py, allowed):
        started.append((handle, px, py, allowed))
    callback = DRAG_START(drag_started)
    n.keep.append(callback)
    n.ok('rv_host_set_drag_start', [P, DRAG_START, P], host, callback, None)
    (x0, y0), (x1, y1) = case['from'], case['to']
    mouse(host, MOUSE_MOVE, x0, y0, BUTTON_NONE, 0, 0)
    mouse(host, MOUSE_DOWN, x0, y0, BUTTON_LEFT, 1, 0)
    mouse(host, MOUSE_MOVE, x0 + 5, y0 + 5, BUTTON_LEFT, 0, 0)
    mouse(host, MOUSE_MOVE, x1, y1, BUTTON_LEFT, 0, 0)
    n.expect(len(started) == 1, 'one drag started')
    handle = started[0][0]
    count = n.call('rv_drag_file_count', [P], handle)
    out_file = n.handle('rv_drag_file', [P, I], handle, 0)
    width, height, ox, oy = I(), I(), I(), I()
    image_status = n.call('rv_drag_image', [P, P, I, ctypes.POINTER(I), ctypes.POINTER(I), ctypes.POINTER(I), ctypes.POINTER(I)],
                          handle, None, 0, ctypes.byref(width), ctypes.byref(height), ctypes.byref(ox), ctypes.byref(oy))
    out_items = []
    for index in range(n.call('rv_drag_item_count', [P], handle)):
        out_items.append([n.text('rv_drag_item_type', [P, I], handle, index), n.text('rv_drag_item_value', [P, I], handle, index)])
    fed = []

    def on_fed(context, event):
        dt = n.handle('rv_dom_drag_event_get_data_transfer', [P], event)
        fed.append(n.snapshot(dt, document))
        release_transfer(dt)
        n.ok('rv_dom_event_prevent_default', [P], event)
        return 0
    feeder = EVENT(on_fed)
    n.keep.append(feeder)
    listeners.append(listen(target, 'drop', 0, feeder, None))
    listeners.append(listen(target, 'dragover', 0, feeder, None))
    back = n.fn('rv_drag_data', P, [P])(handle)
    tx, ty = spec['drop']['point']
    fed_operation = drag(host, DRAG_DROP, tx, ty, started[0][3], back, 0)
    n.fn('rv_drag_data_release', None, [P])(back)
    n.ok('rv_drag_end', [P, I, I, I], handle, tx, ty, fed_operation)
    mouse(host, MOUSE_UP, tx, ty, BUTTON_LEFT, 1, 0)
    results['dragOut'] = {'allowed': started[0][3], 'files': count, 'file': n.describe_file(out_file), 'items': out_items,
                          'image': [image_status, width.value, height.value, ox.value, oy.value], 'fed': fed, 'fedOperation': fed_operation}
    release_blob(out_file)
    for listener in listeners:
        remove(listener)
    listeners.clear()

    # 6. T04: a replacement edit, cancelled and applied, with its target range and transfer payload.
    case = spec['replace']
    n.ok('rv_dom_element_set_inner_html', [P, Utf8], editable, case['html'])
    text_node = n.handle('rv_dom_node_get_first_child', [P], editable)
    replace = {}
    for cancel in (True, False):
        log.clear()
        on(editable, 'beforeinput', 'rv_dom_input_event_get_data_transfer', cancel=cancel, extra=inputs)
        on(editable, 'input', 'rv_dom_input_event_get_data_transfer', extra=inputs)
        live = n.handle('rv_dom_document_create_range', [P], document)
        n.ok('rv_dom_range_set_start', [P, P, U], live, text_node, case['range'][0])
        n.ok('rv_dom_range_set_end', [P, P, U], live, text_node, case['range'][1])
        status = n.call('rv_host_replace_range', [P, P, Utf8], host, live, case['text'])
        replace['cancelled' if cancel else 'applied'] = {'status': status, 'log': list(log), 'after': after(),
                                                         'html': n.text('rv_dom_element_get_inner_html', [P], editable)}
        n.fn('rv_dom_abstract_range_release', None, [P])(live)
        for listener in listeners:
            remove(listener)
        listeners.clear()
    release_node(text_node)
    # A second replacement without listeners, a range of another host's document, and an InputEvent constructed
    # natively, which has no dataTransfer.
    def live_range(owner_document, node, start, end):
        value = n.handle('rv_dom_document_create_range', [P], owner_document)
        n.ok('rv_dom_range_set_start', [P, P, U], value, node, start)
        n.ok('rv_dom_range_set_end', [P, P, U], value, node, end)
        return value
    text_node = n.handle('rv_dom_node_get_first_child', [P], editable)
    second = live_range(document, text_node, 0, 5)
    replace['second'] = {'status': n.call('rv_host_replace_range', [P, P, Utf8], host, second, 'HELLO'),
                         'html': n.text('rv_dom_element_get_inner_html', [P], editable)}
    other = host_create(64, 64)
    load(other, '<p id=o>x</p>')
    other_document = n.fn('rv_host_document', P, [P])(other)
    other_node = get(other, 'o')
    foreign_text = n.handle('rv_dom_node_get_first_child', [P], other_node)
    foreign = live_range(other_document, foreign_text, 0, 1)
    replace['foreign'] = n.call('rv_host_replace_range', [P, P, Utf8], host, foreign, 'y')
    release_node(other_document)
    for value in (foreign, second):
        n.fn('rv_dom_abstract_range_release', None, [P])(value)
    for node in (foreign_text, other_node, text_node):
        release_node(node)
    host_destroy(other)
    kind = n.buffer(b'insertText')
    event_init = InputEventInit(ctypes.sizeof(InputEventInit), 1, 1, 0, 0, StringInput(0, None, 0), 0, StringInput(1, ctypes.cast(kind, P), 10))
    constructed_event = n.handle('rv_dom_input_event_create', [P, Utf8, ctypes.POINTER(InputEventInit)], document, 'beforeinput', ctypes.byref(event_init))
    replace['constructedEvent'] = {'inputType': n.text('rv_dom_input_event_get_input_type', [P], constructed_event),
                                   'dataTransfer': n.handle('rv_dom_input_event_get_data_transfer', [P], constructed_event)}
    results['replace'] = replace

    # 7. Errors.
    errors = {
        'dragEventOnInputEvent': n.call('rv_dom_drag_event_get_data_transfer', [P, ctypes.POINTER(P)], constructed_event, ctypes.byref(P())),
        'nullTransfer': n.call('rv_dom_data_transfer_get_types', [P, P, ctypes.POINTER(Strings)], None, document, ctypes.byref(Strings())),
        'nullContext': n.call('rv_dom_data_transfer_get_types', [P, P, ctypes.POINTER(Strings)], n.handle('rv_dom_data_transfer_create', [P], document), None, ctypes.byref(Strings())),
        'replaceNull': n.call('rv_host_replace_range', [P, P, Utf8], host, None, 'x'),
        'offerNull': n.call('rv_clipboard_offer_file', [P, P], None, image_file),
        'denyNull': n.call('rv_clipboard_deny', [P], None),
        'fileWriteNull': n.call('rv_host_set_clipboard_file_write', [P, WRITE_FILE, P], None, WRITE_FILE(), None),
        'dragFileNull': n.call('rv_drag_file', [P, I, ctypes.POINTER(P)], None, 0, ctypes.byref(P())),
        'dragFileCountNull': n.call('rv_drag_file_count', [P], None),
    }
    n.fn('rv_event_release', None, [P])(constructed_event)
    thread_status = {}

    def off_thread():
        thread_status['replace'] = n.call('rv_host_replace_range', [P, P, Utf8], host, ctypes.c_void_p(1), 'x')
        thread_status['create'] = n.call('rv_dom_data_transfer_create', [P, ctypes.POINTER(P)], document, ctypes.byref(P()))
        thread_status['dragFile'] = n.call('rv_drag_data_add_file', [P, P], ctypes.c_void_p(1), ctypes.c_void_p(1))
    worker = threading.Thread(target=off_thread)
    worker.start()
    worker.join()
    errors['thread'] = thread_status
    results['errors'] = errors
    results['reserved'] = reserved

    for node in (target, editable, source, image):
        release_node(node)
    release_node(document)
    host_destroy(host)
    # Files outlive the host.
    results['pastHost'] = [n.describe_file(file) + [n.file_bytes(file).decode('utf-8', 'replace')] for file in files_handle]
    for file in files_handle + sources + [image_file, copy_file, z]:
        release_blob(file)

    if os.environ.get('DATA_TRANSFER_DUMP'):
        Path(os.environ['DATA_TRANSFER_DUMP']).write_text(json.dumps(results, indent=1), encoding='utf-8')
    compare(n, results, spec, oracle, qualified)
    if evidence:
        Path(evidence).write_text(json.dumps({'results': results, 'assertions': n.assertions}, indent=1), encoding='utf-8')
    print(f'DATA_TRANSFER_PROBE=PASS {n.assertions} assertions')


def at(value, path):
    for key in path.split('.'):
        value = value[int(key)] if isinstance(value, list) else value[key]
    return value


def differences(native, chromium, prefix):
    """The dotted paths of the leaves, or of the shortest unequal subtrees, where the two differ."""
    if isinstance(native, dict) and isinstance(chromium, dict) and native.keys() == chromium.keys():
        return [path for key in native for path in differences(native[key], chromium[key], prefix + '.' + key)]
    if isinstance(native, list) and isinstance(chromium, list) and len(native) == len(chromium):
        return [path for index in range(len(native)) for path in differences(native[index], chromium[index], prefix + '.' + str(index))]
    return [] if native == chromium else [prefix]


def compare(n, results, spec, oracle, qualified):
    # An entry with "platforms" applies only there; every other entry applies on every platform.
    platform = 'linux' if sys.platform.startswith('linux') else sys.platform
    applicable = [item for item in qualified['differences'] if platform in item.get('platforms', [platform])]
    recorded = {item['path']: item for item in applicable}
    found = []
    for case in ('constructed', 'drop', 'paste'):
        native = {key: value for key, value in results[case].items() if key in oracle[case]}
        found += differences(native, oracle[case], case)
    unqualified = [path for path in found if path not in recorded]
    for path in unqualified:
        print('UNQUALIFIED', json.dumps({'path': path, 'native': at(results, path), 'chromium': at(oracle, path), 'reason': ''}))
    n.expect(not unqualified, 'every difference from Chromium is qualified')
    for path, item in recorded.items():
        n.expect(path in found, path + ' is still a difference')
        n.expect(at(results, path) == item['native'] and at(oracle, path) == item['chromium'], path + ' keeps its recorded values')
        n.expect(bool(item.get('reason')), path + ' has a reason')
    # Store modes per phase, as the spec's drag data store modes define them.
    drop = {e['type']: e for e in results['drop']['log']}
    for phase in ('dragenter', 'dragover', 'dragleave'):
        if phase in drop:
            n.expect(drop[phase]['dt']['text'] == '' and drop[phase]['dt']['files'] == [], phase + ' is protected')
    n.expect(drop['dragover']['write'] == {'setData': False, 'itemsAdd': False}, 'dragover cannot write')
    n.expect(drop['drop']['write'] == {'setData': False, 'itemsAdd': False}, 'drop is read-only')
    n.expect(drop['drop']['dt']['text'] == spec['drop']['strings'][0][1], 'drop reads its data')
    paste = {e['type']: e for e in results['paste']['log']}
    n.expect(paste['paste']['write'] == {'setData': False, 'itemsAdd': False}, 'paste is read-only')
    copy = results['copy']
    n.expect(copy['status'] == 1, 'copy ran')
    n.expect(copy['log'][0]['dt']['text'] == spec['copy']['text'], 'copy is read/write')
    for case in ('drop', 'paste', 'copy'):
        for kind, snapshot in results[case]['after'].items():
            if kind in ('beforeinput', 'input'):
                n.expect(snapshot == paste[kind]['dt'], kind + ' dataTransfer stays readable while held')
            else:
                n.expect(snapshot['types'] == [] and snapshot['text'] == '' and snapshot['files'] == [], case + ' ' + kind + ' unreadable afterwards')
    n.expect(copy['written'] == [['string', 'text/plain', spec['copy']['text'], 1], ['file', spec['copy']['file'][0], spec['copy']['file'][1], len(spec['copy']['file'][2]), 0]],
             'copy writes the page string, then its file')
    n.expect(results['paste']['offers'] == [OK, OK, OK, UNSUPPORTED, WRONG_INTERFACE], 'paste offers: strings, file, reserved Files, a Blob')
    deny = results['deny']
    n.expect(deny['status'] == DOM_EXCEPTION and deny['exception'] and 'NotAllowedError' in deny['exception'], 'denied paste is NotAllowedError')
    n.expect(deny['events'] == [] and deny['html'] == results['paste']['html'] and deny['offers'] == [OK], 'denied paste fires and inserts nothing')
    n.expect(results['reserved'] == {'dragFiles': UNSUPPORTED, 'dragBlob': WRONG_INTERFACE, 'dragNull': NULL_ARGUMENT}, 'drag payload errors')
    out = results['dragOut']
    n.expect(out['files'] == 1 and out['file'][0] == spec['copy']['file'][0], 'drag-out carries the page file')
    n.expect(['text/plain', spec['dragOut']['text']] in out['items'], 'drag-out carries the page string')
    n.expect(out['image'][0] == BUFFER_TOO_SMALL and out['image'][1:3] == spec['dragOut']['imageSize']
             and out['image'][3:] == spec['dragOut']['imageOffset'], 'drag-out image is the setDragImage element at its offset')
    n.expect(out['allowed'] == 5, 'effectAllowed copyLink allows copy and link')
    n.expect(out['fedOperation'] == 1 and out['fed'][-1]['files'] == [out['file']], 'the drag fed back drops the page file')
    replace = results['replace']
    cancelled, applied = replace['cancelled'], replace['applied']
    n.expect(cancelled['status'] == 0 and cancelled['html'] == spec['replace']['html'], 'cancelled replacement changes nothing')
    n.expect([e['type'] for e in cancelled['log']] == ['beforeinput'], 'cancelled replacement fires beforeinput only')
    n.expect(applied['status'] == 1 and applied['html'] == spec['replace']['expected'], 'replacement applied')
    n.expect([e['type'] for e in applied['log']] == ['beforeinput', 'input'], 'beforeinput then input')
    for record in cancelled['log'] + applied['log']:
        n.expect(record['inputType'] == 'insertReplacementText' and record['data'] is None, 'insertReplacementText with null data')
        n.expect(record['dt']['types'][:2] == ['text/plain', 'text/html'] and record['dt']['text'] == spec['replace']['text'], 'replacement payload')
    n.expect(applied['log'][0]['ranges'] == [spec['replace']['range']], 'beforeinput target range is the replaced range')
    n.expect(applied['after']['beforeinput'] == applied['log'][0]['dt'], 'beforeinput payload valid while held')
    n.expect(replace['second'] == {'status': 1, 'html': spec['replace']['secondExpected']}, 'a replacement without listeners applies')
    n.expect(replace['foreign'] == WRONG_HOST, 'a range of another document is refused with RV_ERR_WRONG_HOST')
    n.expect(replace['constructedEvent'] == {'inputType': 'insertText', 'dataTransfer': None}, 'constructed InputEvent')
    errors = results['errors']
    n.expect(errors['dragEventOnInputEvent'] == WRONG_INTERFACE, 'DragEvent getter on an InputEvent')
    n.expect(errors['nullTransfer'] == NULL_ARGUMENT and errors['nullContext'] == NULL_ARGUMENT, 'null transfer and context')
    for key in ('replaceNull', 'offerNull', 'denyNull', 'fileWriteNull', 'dragFileNull', 'dragFileCountNull'):
        n.expect(errors[key] == NULL_ARGUMENT, key)
    n.expect(errors['thread'] == {'replace': WRONG_THREAD, 'create': WRONG_THREAD, 'dragFile': WRONG_THREAD}, 'off-thread calls')
    n.expect([f[:3] for f in results['pastHost']] == [[name, kind, len(content.encode())] for name, content, kind in spec['drop']['files']]
             and [f[3] for f in results['pastHost']] == [content for _, content, _ in spec['drop']['files']], 'dropped files outlive the host')
    n.expect(len(recorded) == len(applicable), 'qualified paths are unique')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    arguments = parser.parse_args()
    run(arguments.native_directory, arguments.evidence)
