import ctypes, os, sys, json
d = sys.argv[1]
os.add_dll_directory(d)
lib = ctypes.CDLL(os.path.join(d, 'RanvierWebCoreHost.dll'))
has = lib.rv_abi_has; has.argtypes = [ctypes.c_char_p]; has.restype = ctypes.c_int32
out = {'abi': lib.rv_abi_version(), 'has': {f: has(f.encode()) for f in ['blob-urls', 'dom:FileReader', 'dom-constructor:FileReader']},
       'exports': {n: hasattr(lib, n) for n in ['rv_dom_domurl_create_object_url', 'rv_dom_file_reader_create', 'rv_blob_read', 'rv_blob_url_read', 'rv_file_create_from_path', 'rv_file_reader_result']}}
print(json.dumps(out))
