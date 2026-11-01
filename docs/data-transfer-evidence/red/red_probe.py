"""RED probe for I07/T09/T04 against a batch-1 runtime: what the DataTransfer object model lacks on the native ABI.
usage: python -I red_probe.py <runtime dir> <native tree> <out.json>"""
import ctypes
import hashlib
import json
import os
from pathlib import Path
import sys

runtime, tree, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve(), Path(sys.argv[3])
sys.path.insert(0, str(tree / 'tests/abi'))
from utf8_inputs import bind as bind_utf8  # noqa: E402

P, I = ctypes.c_void_p, ctypes.c_int32
CB = ctypes.CFUNCTYPE(I, P, P)
READ = ctypes.CFUNCTYPE(None, P, P)
WRITE = ctypes.CFUNCTYPE(None, P, ctypes.c_char_p, ctypes.c_char_p, I)
os.add_dll_directory(str(runtime))
lib = ctypes.CDLL(str(runtime / 'RanvierWebCoreHost.dll'))
webcore = ctypes.CDLL(str(runtime / 'WebCore.dll'))
assertions = 0


def expect(condition, label):
    global assertions
    assertions += 1
    if not condition:
        raise AssertionError(label)


def fn(name, result, arguments):
    return bind_utf8(lib, name, result, arguments)


def text(name, target):
    buffer, length = ctypes.create_string_buffer(8192), I()
    status = fn(name, I, [P, P, I, ctypes.POINTER(I)])(target, buffer, len(buffer), ctypes.byref(length))
    if status != 0:
        return {'status': status}
    return None if length.value < 0 else buffer.raw[:length.value].decode('utf-8')


def exported(name):
    return hasattr(lib, name) or hasattr(webcore, name)


result = {'runtime': str(runtime), 'abi': fn('rv_abi_version', I, [])()}
expect(result['abi'] == 54, 'batch-1 ABI 54')
hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in runtime.iterdir() if p.suffix == '.dll'}
result['runtimeSha256'] = {k: hashes[k] for k in ['RanvierWebCoreHost.dll', 'WebCore.dll', 'JavaScriptCore.dll']}

# 1. The DataTransfer object model has no export.
wanted = ['rv_dom_drag_event_get_data_transfer', 'rv_dom_clipboard_event_get_clipboard_data', 'rv_dom_input_event_get_data_transfer',
          'rv_dom_data_transfer_get_types', 'rv_dom_data_transfer_get_data', 'rv_dom_data_transfer_set_data',
          'rv_dom_data_transfer_get_files', 'rv_dom_data_transfer_get_items', 'rv_dom_data_transfer_get_drop_effect',
          'rv_dom_data_transfer_get_effect_allowed', 'rv_dom_data_transfer_set_drag_image', 'rv_dom_data_transfer_item_list_get_length',
          'rv_dom_data_transfer_item_get_kind', 'rv_dom_data_transfer_item_get_as_file', 'rv_dom_data_transfer_create',
          'rv_dom_drag_event_create', 'rv_dom_clipboard_event_create']
existing = ['rv_host_drag', 'rv_drag_data_add', 'rv_clipboard_offer', 'rv_drag_item_value', 'rv_drag_image',
            'rv_dom_input_event_get_target_ranges', 'rv_dom_file_create', 'rv_file_list_create']
result['missingExports'] = {name: exported(name) for name in wanted}
result['existingExports'] = {name: exported(name) for name in existing}
for name in wanted:
    expect(not exported(name), name + ' is absent')
for name in existing:
    expect(exported(name), name + ' is present')
has = fn('rv_abi_has', I, [ctypes.c_char_p])
result['capabilities'] = {key: has(key.encode()) for key in
                          ['clipboard', 'drop', 'drag-out', 'dom:DataTransfer', 'dom:DataTransferItem', 'dom:DataTransferItemList',
                           'dom:DragEvent', 'dom:ClipboardEvent', 'dom:InputEvent', 'dom-type-query:Event']}
for key in ['dom:DataTransfer', 'dom:DataTransferItem', 'dom:DataTransferItemList']:
    expect(result['capabilities'][key] == 0, key + ' not advertised')
# Files reach a drag or a paste only as strings: the payload builders take a type and a string, and no File.
result['payloadBuilders'] = {'rv_drag_data_add': '(RvDragData*, const char* type, const char* data)',
                             'rv_clipboard_offer': '(RvClipboardRequest*, const char* type, const char* data)',
                             'fileBuilders': {name: exported(name) for name in ['rv_drag_data_add_file', 'rv_clipboard_offer_file', 'rv_drag_file']}}
for name, present in result['payloadBuilders']['fileBuilders'].items():
    expect(not present, name + ' is absent')

# 2. A paste into contenteditable: beforeinput carries the HTML payload only in dataTransfer, which the ABI cannot read.
host = fn('rv_host_create', P, [I, I])(320, 200)
expect(fn('rv_host_load_html', I, [P, ctypes.c_char_p])(host, b'<div id=e contenteditable>ab<b>cd</b>ef</div><div id=t>drop</div>') == 0, 'load')
element = fn('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])(host, b'e')
target = fn('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])(host, b't')
events = []


class RangeSeq(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', P)]


def listen(node, kind, cancel=False):
    def callback(context, event):
        record = {'type': kind, 'interface': text('rv_dom_event_get_interface_name', event)}
        if record['interface'] == 'InputEvent':
            record['inputType'] = text('rv_dom_input_event_get_input_type', event)
            record['data'] = text('rv_dom_input_event_get_data', event)
            ranges = RangeSeq()
            status = fn('rv_dom_input_event_get_target_ranges', I, [P, ctypes.POINTER(RangeSeq)])(event, ctypes.byref(ranges))
            record['targetRanges'] = ranges.count if status == 0 else {'status': status}
            if status == 0:
                fn('rv_dom_sequence_static_range_release', None, [ctypes.POINTER(RangeSeq)])(ctypes.byref(ranges))
        if cancel:
            fn('rv_dom_event_prevent_default', I, [P])(event)
        events.append(record)
        return 0
    holder = CB(callback)
    keep.append(holder)
    return fn('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CB, P])(node, kind.encode(), 0, holder, None)


keep = []
offered = [(b'text/plain', b'XY'), (b'text/html', b'<i>X</i>Y'), (b'image/png', b'not-a-string-type')]
offer = fn('rv_clipboard_offer', I, [P, ctypes.c_char_p, ctypes.c_char_p])
offer_status = []


def read(context, request):
    for type_, data in offered:
        offer_status.append(offer(request, type_, data))


reader, writer = READ(read), WRITE(lambda c, t, d, f: None)
expect(fn('rv_host_set_clipboard', I, [P, I, WRITE, READ, P])(host, 0, writer, reader, None) == 0, 'App clipboard style')
listeners = [listen(element, kind) for kind in ['paste', 'beforeinput', 'input']]
expect(fn('rv_element_focus', I, [P])(element) in (0, 1), 'focus')
expect(fn('rv_host_edit', I, [P, I])(host, 4) == 1, 'select all')  # RV_EDIT_SELECT_ALL
pasted = fn('rv_host_edit', I, [P, I])(host, 2)  # RV_EDIT_PASTE
result['paste'] = {'status': pasted, 'offerStatus': offer_status, 'events': list(events),
                   'html': text('rv_dom_element_get_inner_html', element)}
expect(pasted == 1, 'paste ran')
before = [e for e in events if e['type'] == 'beforeinput']
expect(len(before) == 1 and before[0]['inputType'] == 'insertFromPaste', 'beforeinput insertFromPaste')
expect(before[0]['data'] is None, 'contenteditable paste data is null: the payload lives in dataTransfer only')
expect(offer_status == [0, 0, 0], 'an image type offered as a string is accepted silently')

# 3. A drop: the DragEvent fires, and its dataTransfer, files and effects have no accessor.
events.clear()
expect(fn('rv_host_set_drag', I, [P, I])(host, 0) == 0, 'App drag style')
listeners += [listen(target, 'dragover', cancel=True), listen(target, 'drop', cancel=True)]
data = fn('rv_drag_data_create', P, [])()
expect(fn('rv_drag_data_add', I, [P, ctypes.c_char_p, ctypes.c_char_p])(data, b'text/uri-list', b'file:///C:/photo.png') == 0, 'uri')
fn('rv_host_update', I, [P])(host)
x, y = 10, 40
over = fn('rv_host_drag', I, [P, I, I, I, I, P, I])(host, 0, x, y, 7, data, 0)
drop = fn('rv_host_drag', I, [P, I, I, I, I, P, I])(host, 2, x, y, 7, data, 0)
fn('rv_drag_data_release', None, [P])(data)
result['drop'] = {'overOperation': over, 'dropOperation': drop, 'events': list(events)}
# The runtime type query names a DragEvent MouseEvent and a ClipboardEvent Event: neither interface is in gen/dom.json.
expect([e['interface'] for e in events if e['type'] == 'drop'] == ['MouseEvent'], 'a DragEvent reports MouseEvent')
expect([e['interface'] for e in result['paste']['events'] if e['type'] == 'paste'] == ['Event'], 'a ClipboardEvent reports Event')

for listener in listeners:
    fn('rv_listener_remove', None, [P])(listener)
for node in (element, target):
    fn('rv_node_release', None, [P])(node)
fn('rv_host_destroy', None, [P])(host)

# 4. The engine hides pasteboard files on every non-Cocoa port: no app-supplied file reaches dataTransfer.files.
source = Path('C:/wk/src/Source/WebCore/dom/DataTransfer.cpp')
lines = source.read_text(encoding='utf-8').splitlines()
start = next(i for i, line in enumerate(lines) if line.startswith('bool DataTransfer::allowsFileAccess() const'))
result['engineFileAccess'] = {'file': 'Source/WebCore/dom/DataTransfer.cpp', 'sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                              'lines': f'{start + 1}-{start + 13}', 'text': lines[start:start + 13]}
expect('    return false;' in lines[start:start + 13], 'Windows allowsFileAccess returns false')
result['assertions'] = assertions
out.write_text(json.dumps(result, indent=1), encoding='utf-8')
print('RED probe', assertions, 'assertions; missing', sum(not v for v in result['missingExports'].values()), 'of', len(wanted))
