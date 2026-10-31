"""RED for A09 on the A01 runtime (waapi-candidate-3): custom effect exports and the capability are absent."""
import ctypes, json, sys
from pathlib import Path
runtime = Path(sys.argv[1])
lib = ctypes.CDLL(str(runtime / 'RanvierWebCoreHost.dll'))
has = lib.rv_abi_has; has.argtypes = [ctypes.c_char_p]; has.restype = ctypes.c_int32
ver = lib.rv_abi_version; ver.restype = ctypes.c_int32
out = {'abi': ver(), 'features': {f: has(f.encode()) for f in ('animation-custom-effects', 'dom:CustomEffect', 'dom:DocumentTimeline', 'dom:WebAnimation')}}
out['symbols'] = {}
for name in ('rv_custom_effect_callback_create', 'rv_custom_effect_callback_release', 'rv_dom_custom_effect_create',
             'rv_dom_document_timeline_animate', 'rv_dom_document_timeline_create', 'rv_dom_element_animate'):
    try:
        getattr(lib, name); out['symbols'][name] = True
    except AttributeError:
        out['symbols'][name] = False
print(json.dumps(out, indent=1))
