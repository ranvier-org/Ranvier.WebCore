"""Checks the C layouts of the structs RanvierWebCoreAbi.h passes by pointer against ctypes and the field lists of the
F# interop (tests/abi/Native.fs), on a 64-bit platform. host/RanvierWebCoreAbi.cpp static_asserts the same sizes and
offsets in the host build."""

import ctypes
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
P, I, D, U = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double, ctypes.c_uint32

# Each struct: its ctypes fields, the expected size and offsets, and the F# type name with its field names.
LAYOUTS = {
    'RvFormSubmission': ([('size', U), ('method', P), ('url', P), ('target', P), ('content_type', P), ('body', P),
                          ('body_length', I), ('form', P), ('submitter', P)], 72,
                         [0, 8, 16, 24, 32, 40, 48, 56, 64], 'FormSubmission'),
    'RvTextSegments': ([('count', I), ('starts', P), ('word_like', P), ('locale', P)], 32, [0, 8, 16, 24], 'TextSegments'),
    'RvEventInit': ([('size', I), ('bubbles', I), ('cancelable', I), ('composed', I), ('detail', I), ('modifiers', I),
                     ('screenX', D), ('screenY', D), ('clientX', D), ('clientY', D), ('button', I), ('buttons', I), ('key', P),
                     ('code', P), ('location', I), ('repeat', I), ('isComposing', I), ('relatedTarget', P), ('customDetailJson', P)],
                    112, [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 56, 60, 64, 72, 80, 84, 88, 96, 104], 'EventInit'),
    # Views mirrors RvWindowMetrics as WindowMetrics in Ranvier.View.WebCore/Viewport.fs; its fixture checks the mirror.
    'RvWindowMetrics': ([('size', I), ('innerWidth', I), ('innerHeight', I), ('outerWidth', I), ('outerHeight', I),
                         ('devicePixelRatio', D)], 32, [0, 4, 8, 12, 16, 24], None),
}


def main():
    assert ctypes.sizeof(ctypes.c_void_p) == 8, 'a 64-bit platform'
    header = (ROOT / 'host/RanvierWebCoreAbi.h').read_text(encoding='utf-8')
    native = (ROOT / 'tests/abi/Native.fs').read_text(encoding='utf-8')
    checks = 0
    for name, (fields, size, offsets, fsharp) in LAYOUTS.items():
        body = re.search(r'typedef struct ' + name + r' \{(.*?)\} ' + name + ';', header, re.S)
        assert body, name + ' in the header'
        declared = re.findall(r'^\s*[\w\s\*]+?[\s\*](\w+);', re.sub(r'/\*.*?\*/', '', body.group(1), flags=re.S), re.M)
        assert declared == [f for f, _ in fields], name + ' header fields ' + str(declared)
        struct = type(name, (ctypes.Structure,), {'_fields_': fields})
        assert ctypes.sizeof(struct) == size, name + ' size ' + str(ctypes.sizeof(struct))
        assert [getattr(struct, f).offset for f, _ in fields] == offsets, name + ' offsets'
        checks += 3
        if fsharp:
            block = re.search(r'type ' + fsharp + r' =\s*\n((?:\s+val mutable .*\n)+)', native)
            assert block, fsharp + ' in Native.fs'
            assert len(re.findall(r'val mutable', block.group(1))) == len(fields), fsharp + ' field count'
            checks += 1
    print(f'PASS abi_layouts: {checks} assertions', flush=True)


if __name__ == '__main__':
    sys.exit(main())
