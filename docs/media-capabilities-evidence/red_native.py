"""RED survey of media capability queries on a candidate runtime: which MediaCapabilities exports exist, whether
"media-capabilities" is advertised, and what the passive capability catalogue reports for the media facilities and
build options. Writes the JSON named by the second argument."""
import ctypes, json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
sys.path.insert(0, str(here.parents[1] / 'tests/abi'))
from svg_paint_probe import SvgProbe

FACILITY = 4
DIMENSIONS = ['exported', 'implemented', 'enabled', 'permitted', 'available']
CANDIDATE_EXPORTS = [
    'rv_media_decoding_info', 'rv_media_encoding_info', 'rv_media_capabilities_info', 'rv_host_media_decoding_info',
    'rv_host_media_encoding_info', 'rv_dom_media_capabilities_decoding_info', 'rv_dom_media_capabilities_encoding_info',
    'rv_dom_navigator_get_media_capabilities', 'rv_host_media_capabilities']
NAMES = ['video', 'web-audio', 'media-stream', 'media-recorder', 'web-codecs', 'encrypted-media', 'media-capabilities',
         'media-decoding', 'media-encoding', 'build:ENABLE_VIDEO', 'build:ENABLE_WEB_AUDIO', 'build:ENABLE_MEDIA_STREAM',
         'build:ENABLE_WEB_RTC', 'build:ENABLE_WEB_CODECS', 'build:ENABLE_MEDIA_SOURCE', 'build:ENABLE_ENCRYPTED_MEDIA']

out = {}
with SvgProbe(sys.argv[1], 320, 240) as p:
    P, I = p.pointer, p.integer
    lib = p.library
    out['abi'] = p.bind('rv_abi_version', I, [])()
    has = p.bind('rv_abi_has', I, [ctypes.c_char_p])
    out['advertised'] = {n: has(n.encode()) for n in ['media-capabilities', 'image-decode', 'font-load', 'blob-urls']}
    out['exports'] = {n: hasattr(lib, n) for n in CANDIDATE_EXPORTS}
    count = p.bind('rv_capability_count', I, [I])
    name_at = p.bind('rv_capability_name_at', I, [I, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    names = []
    for index in range(count(FACILITY)):
        buffer, length = ctypes.create_string_buffer(256), I()
        name_at(FACILITY, index, buffer, 256, ctypes.byref(length))
        names.append(buffer.value.decode())
    out['facilityNames'] = len(names)
    out['mediaNamesListed'] = [n for n in names if 'media' in n or 'video' in n or 'audio' in n or 'codec' in n or 'RTC' in n]
    fact = p.bind('rv_host_capability_fact', I, [P, I, ctypes.c_char_p, I, ctypes.POINTER(I)])
    facts = {}
    for name in NAMES:
        row = {}
        for d, label in enumerate(DIMENSIONS):
            value = I(99)
            status = fact(p.host, FACILITY, name.encode(), d, ctypes.byref(value))
            row[label] = value.value if status == 0 else 'status ' + str(status)
        facts[name] = row
    out['facts'] = facts
    out['scriptsEnabled'] = p.bind('rv_host_scripts_enabled', I, [P])(p.host)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding='utf-8')
print(json.dumps(out, indent=1))
