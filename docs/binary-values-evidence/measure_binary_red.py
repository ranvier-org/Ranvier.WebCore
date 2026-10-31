"""H11 RED: what the Native29/ABI37 runtime exposes for Blob, File, FileList and FileReader."""
import ctypes, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tests' / 'abi'))
from form_collections import Native, Case, EntryValue, P, I, utf8, FILE_ARM

def main(directory, out):
    n = Native(directory)
    names = ['rv_dom_blob_create', 'rv_dom_blob_get_size', 'rv_dom_blob_get_type', 'rv_dom_blob_slice', 'rv_dom_blob_release',
             'rv_dom_file_create', 'rv_dom_file_get_name', 'rv_dom_file_get_last_modified', 'rv_dom_file_list_get_length',
             'rv_dom_file_list_item', 'rv_dom_html_input_element_get_files', 'rv_dom_html_input_element_set_files',
             'rv_blob_read_bytes', 'rv_file_list_create', 'rv_dom_file_reader_create', 'rv_dom_dom_form_data_append_1',
             'rv_dom_dom_form_data_set_1']
    exports = {name: hasattr(n.library, name) for name in names}
    has = n.bind('rv_abi_has', I, [ctypes.c_char_p])
    features = {f: has(f.encode()) for f in ['dom-binary-values', 'dom:Blob', 'dom:File', 'dom:FileList', 'dom:FileReader', 'dom:DOMFormData']}
    case = Case(n, '<form id=f><input id=i type=file name=upload></form>')
    data = n.handle('rv_dom_dom_form_data_create', [P, P, P], case.document, case.node('f'), None, nullable=False)
    text, length = utf8('upload')
    result = EntryValue()
    n.ok('rv_dom_dom_form_data_get', [P, P, I, ctypes.POINTER(EntryValue)], data, text, length, ctypes.byref(result))
    entry = {'present': result.present, 'tag': result.tag, 'fileTag': result.tag == FILE_ARM, 'arm0IsNull': result.arm0 is None}
    n.bind('rv_dom_union_file_or_usv_string_nullable_release', None, [ctypes.POINTER(EntryValue)])(ctypes.byref(result))
    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
    case.close()
    report = {'runtime': str(directory), 'abiVersion': n.bind('rv_abi_version', I, [])(), 'exports': exports,
              'features': features, 'emptyFileInputEntry': entry,
              'hostBlobRegistry': 'host/RanvierWebCoreAbi.cpp RvBlobRegistry is a stub: registers nothing, blobSize 0, blobType empty',
              'assertions': n.assertions}
    Path(out).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

main(sys.argv[1], sys.argv[2])
