"""Checks ABI struct layouts reported by a C compiler against ctypes, header fields, and F# interop declarations."""

import ctypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
P, I, D, U = ctypes.c_void_p, ctypes.c_int32, ctypes.c_double, ctypes.c_uint32


class RvDomUtf8StringInput(ctypes.Structure):
    _fields_ = [('present', I), ('data', P), ('length', I)]


# Each struct: its ctypes fields, the expected size and offsets, and the F# type name with its field names.
LAYOUTS = {
    'RvHostErrorRecord': ([('operation', I), ('source', I), ('status', I), ('native_code', I)],
                          16, [0, 4, 8, 12], 'HostErrorRecord'),
    'RvHostTraceEvent': ([('phase', I), ('source', I), ('start_ns', ctypes.c_uint64),
                          ('duration_ns', ctypes.c_uint64), ('sequence', ctypes.c_uint64)],
                         32, [0, 4, 8, 16, 24], 'HostTraceEvent'),
    'RvImageDataLayout': ([('size', I), ('width', U), ('height', U), ('colorSpace', I), ('pixelFormat', I),
                           ('bytesPerPixel', I), ('rowBytes', ctypes.c_int64), ('byteLength', ctypes.c_int64)],
                          40, [0, 4, 8, 12, 16, 20, 24, 32], None),
    'RvImageBitmapOptions': ([('size', I), ('crop', I), ('sx', I), ('sy', I), ('sw', I), ('sh', I),
                              ('imageOrientation', I), ('premultiplyAlpha', I), ('colorSpaceConversion', I),
                              ('resizeWidth', U), ('resizeHeight', U), ('resizeQuality', I)],
                             48, [0, 4, 8, 12, 16, 20, 24, 28, 32, 36, 40, 44], None),
    'RvDomKeyframeAnimationOptions': ([('size', U), ('delay', D), ('end_delay', D), ('fill', I),
                                       ('iteration_start', D), ('iterations', D), ('duration', P), ('direction', I),
                                       ('easing', RvDomUtf8StringInput), ('iteration_composite', I), ('composite', I),
                                       ('pseudo_element', RvDomUtf8StringInput), ('id', RvDomUtf8StringInput),
                                       ('timeline', P), ('range_start', P), ('range_end', P)],
                                      168, [0, 8, 16, 24, 32, 40, 48, 56, 64, 88, 92, 96, 120, 144, 152, 160],
                                      'RvDomKeyframeAnimationOptions'),
    'RvFormSubmission': ([('size', U), ('method', P), ('url', P), ('target', P), ('content_type', P), ('body', P),
                          ('body_length', I), ('form', P), ('submitter', P)], 72,
                         [0, 8, 16, 24, 32, 40, 48, 56, 64], 'FormSubmission'),
    'RvTextSegments': ([('count', I), ('starts', P), ('word_like', P), ('locale', P)], 32, [0, 8, 16, 24], 'TextSegments'),
    'RvEventInit': ([('size', I), ('bubbles', I), ('cancelable', I), ('composed', I), ('detail', I), ('modifiers', I),
                     ('screenX', D), ('screenY', D), ('clientX', D), ('clientY', D), ('button', I), ('buttons', I), ('key', P),
                     ('code', P), ('location', I), ('repeat', I), ('isComposing', I), ('relatedTarget', P), ('customDetailJson', P)],
                    112, [0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 56, 60, 64, 72, 80, 84, 88, 96, 104], 'EventInit'),
    'RvResizeEntry': ([('size', I), ('hasDevicePixel', I), ('target', P), ('contentX', D), ('contentY', D), ('contentWidth', D),
                       ('contentHeight', D), ('contentInlineSize', D), ('contentBlockSize', D), ('borderInlineSize', D),
                       ('borderBlockSize', D), ('devicePixelInlineSize', D), ('devicePixelBlockSize', D)], 96,
                      [0, 4, 8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88], 'ResizeEntry'),
    'RvIntersectionEntry': ([('size', I), ('isIntersecting', I), ('target', P), ('time', D), ('hasRootBounds', I), ('reserved', I),
                             ('rootX', D), ('rootY', D), ('rootWidth', D), ('rootHeight', D), ('boundsX', D), ('boundsY', D),
                             ('boundsWidth', D), ('boundsHeight', D), ('intersectionX', D), ('intersectionY', D),
                             ('intersectionWidth', D), ('intersectionHeight', D), ('intersectionRatio', D)], 136,
                            [0, 4, 8, 16, 24, 28, 32, 40, 48, 56, 64, 72, 80, 88, 96, 104, 112, 120, 128], 'IntersectionEntry'),
    'RvNotificationOptions': ([('size', I), ('dir', I), ('silent', I), ('body_length', I), ('tag_length', I), ('lang_length', I),
                               ('icon_length', I), ('reserved', I), ('body', P), ('tag', P), ('lang', P), ('icon', P)], 64,
                              [0, 4, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56], 'NotificationOptions'),
    # Views mirrors RvWindowMetrics as WindowMetrics in Ranvier.View.WebCore/Viewport.fs; its fixture checks the mirror.
    'RvWindowMetrics': ([('size', I), ('innerWidth', I), ('innerHeight', I), ('outerWidth', I), ('outerHeight', I),
                         ('devicePixelRatio', D)], 32, [0, 4, 8, 12, 16, 24], None),
    'RvMediaVideoConfiguration': ([('size', I), ('content_type', P), ('content_type_length', I), ('width', U), ('height', U),
                                   ('bitrate', ctypes.c_uint64), ('framerate', D), ('alpha_channel', I), ('hdr_metadata_type', I),
                                   ('color_gamut', I), ('transfer_function', I)], 64, [0, 8, 16, 20, 24, 32, 40, 48, 52, 56, 60], None),
    'RvMediaAudioConfiguration': ([('size', I), ('content_type', P), ('content_type_length', I), ('channels', P), ('channels_length', I),
                                   ('bitrate', ctypes.c_int64), ('samplerate', ctypes.c_int64), ('spatial_rendering', I)], 64,
                                  [0, 8, 16, 24, 32, 40, 48, 56], None),
    'RvSnapshotOptions': ([('size', I), ('color_space', I), ('scale', D), ('crop', I), ('encoding', I), ('x', D), ('y', D),
                           ('width', D), ('height', D), ('quality', D)], 64, [0, 4, 8, 16, 20, 24, 32, 40, 48, 56], None),
}


def native_probe_source():
    lines = [
        '#include <stddef.h>',
        '#include <stdio.h>',
        '#include "RanvierWebCoreAbi.h"',
        '#include "RanvierWebCoreDom.h"',
        'int main(void) {',
    ]
    for name, (fields, _, _, _) in LAYOUTS.items():
        offsets = ', '.join(f'(size_t)offsetof({name}, {field})' for field, _ in fields)
        lines.append(f'    printf("{name}|%zu|", sizeof({name}));')
        formats = ', '.join('%zu' for _ in fields)
        lines.append(f'    printf("{formats}\\n", {offsets});')
    lines.extend(['    return 0;', '}'])
    return '\n'.join(lines) + '\n'


def parse_native_layouts(output):
    layouts = {}
    for line in output.splitlines():
        name, size, *offsets = line.split('|')
        layouts[name] = (int(size), [int(value) for value in offsets[0].split(',')])
    return layouts


def check_native_layouts(actual):
    for name, (fields, size, offsets, _) in LAYOUTS.items():
        assert name in actual, name + ' in compiler probe'
        native_size, native_offsets = actual[name]
        assert native_size == size, f'{name} compiler size {native_size}, expected {size}'
        assert native_offsets == offsets, f'{name} compiler offsets {native_offsets}, expected {offsets}'


def cleanup_probe_directory(directory):
    directory = Path(directory)
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if directory.is_symlink():
        raise ValueError(f'refusing to remove a linked ABI probe directory: {directory}')
    resolved = directory.resolve(strict=True)
    if resolved.parent != temporary_root or not resolved.name.startswith('ranvier-abi-layout-'):
        raise ValueError(f'refusing to remove non-owned ABI probe directory: {directory}')

    attempts = 4
    for attempt in range(attempts):
        try:
            shutil.rmtree(resolved)
            return
        except PermissionError as error:
            if attempt + 1 == attempts:
                raise PermissionError(
                    f'could not remove owned ABI probe directory after {attempts} attempts; '
                    f'diagnostics retained at {resolved}'
                ) from error
            time.sleep(0.05 * (attempt + 1))


def run_native_probe():
    compiler = next((shutil.which(name) for name in ('cc', 'gcc', 'clang', 'clang-cl', 'cl') if shutil.which(name)), None)
    assert compiler, 'a C compiler (cc, gcc, or clang) is required for native ABI layout checks'
    directory = Path(tempfile.mkdtemp(prefix='ranvier-abi-layout-'))
    try:
        source = Path(directory) / 'abi_layout_probe.c'
        executable = Path(directory) / ('abi_layout_probe.exe' if sys.platform == 'win32' else 'abi_layout_probe')
        source.write_text(native_probe_source(), encoding='utf-8')
        environment = os.environ.copy()
        if os.name == 'nt' and not environment.get('PROCESSOR_ARCHITECTURE'):
            environment['PROCESSOR_ARCHITECTURE'] = 'AMD64'
        if Path(compiler).name.lower() in ('cl', 'cl.exe', 'clang-cl', 'clang-cl.exe'):
            command = [compiler, '/nologo', '/std:c11', '/I' + str(ROOT / 'host'), str(source), '/Fe:' + str(executable)]
        else:
            command = [compiler, '-std=c11', '-I', str(ROOT / 'host'), str(source), '-o', str(executable)]
        print(f'ABI probe compile command: {command!r}', flush=True)
        compile_result = subprocess.run(
            command, capture_output=True, text=True, check=False, env=environment, cwd=directory,
        )
        print(f'ABI probe compile exit={compile_result.returncode}', flush=True)
        if compile_result.stdout:
            print('ABI probe compile stdout:\n' + compile_result.stdout, flush=True)
        if compile_result.stderr:
            print('ABI probe compile stderr:\n' + compile_result.stderr, flush=True)
        assert compile_result.returncode == 0, 'native ABI probe compile failed'

        run_command = [str(executable)]
        print(f'ABI probe run command: {run_command!r}', flush=True)
        run_result = subprocess.run(run_command, capture_output=True, text=True, check=False, cwd=directory)
        print(f'ABI probe run exit={run_result.returncode}', flush=True)
        if run_result.stdout:
            print('ABI probe stdout:\n' + run_result.stdout, flush=True)
        if run_result.stderr:
            print('ABI probe stderr:\n' + run_result.stderr, flush=True)
        assert run_result.returncode == 0, 'native ABI probe failed'

        actual = parse_native_layouts(run_result.stdout)
        check_native_layouts(actual)
        print(f'PASS native ABI layout probe: {len(actual)} structs validated', flush=True)
        return actual
    finally:
        cleanup_probe_directory(directory)


def main():
    assert ctypes.sizeof(ctypes.c_void_p) == 8, 'a 64-bit platform'
    header = (ROOT / 'host/RanvierWebCoreAbi.h').read_text(encoding='utf-8')
    dom_header = (ROOT / 'host/RanvierWebCoreDom.h').read_text(encoding='utf-8')
    native = (ROOT / 'tests/abi/Native.fs').read_text(encoding='utf-8')
    native_dom = (ROOT / 'tests/abi/NativeDom.fs').read_text(encoding='utf-8')
    checks = 0
    for name, (fields, size, offsets, fsharp) in LAYOUTS.items():
        source = dom_header if name == 'RvDomKeyframeAnimationOptions' else header
        body = re.search(r'typedef struct ' + name + r' \{(.*?)\} ' + name + ';', source, re.S)
        assert body, name + ' in the header'
        declared = re.findall(r'^\s*[\w\s\*]+?[\s\*](\w+);', re.sub(r'/\*.*?\*/', '', body.group(1), flags=re.S), re.M)
        assert declared == [f for f, _ in fields], name + ' header fields ' + str(declared)
        struct = type(name, (ctypes.Structure,), {'_fields_': fields})
        assert ctypes.sizeof(struct) == size, name + ' size ' + str(ctypes.sizeof(struct))
        assert [getattr(struct, f).offset for f, _ in fields] == offsets, name + ' offsets'
        checks += 3
        if fsharp:
            source = native_dom if name == 'RvDomKeyframeAnimationOptions' else native
            block = re.search(r'type ' + fsharp + r' =\s*\n((?:\s+val mutable .*\n)+)', source)
            assert block, fsharp + ' in Native.fs'
            assert len(re.findall(r'val mutable', block.group(1))) == len(fields), fsharp + ' field count'
            checks += 1
    run_native_probe()
    checks += 2 * sum(len(layout[0]) + 1 for layout in LAYOUTS.values())
    print(f'PASS abi_layouts: {checks} assertions', flush=True)


if __name__ == '__main__':
    sys.exit(main())
