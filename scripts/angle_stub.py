# Writes Source/ThirdParty/ANGLE/stub/ANGLEStub.cpp of 0001-angle-stub.patch into a WebKit tree: a stub
# definition for every EGL and GLES 2 and 3 entry point declared by ANGLE's headers on Windows. Run it
# on a new WebKit release when the patch's link fails on an undefined gl* or egl* symbol, then
# re-export the patch with patches.py.
#
#   angle_stub.py --source DIR [--clang PATH]
import argparse, pathlib, re, subprocess, tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--source', required=True)
parser.add_argument('--clang', default='clang-cl', help="clang-cl of pins.json's LLVM release")
args = parser.parse_args()
clang = args.clang
inc = pathlib.Path(args.source) / 'Source/ThirdParty/ANGLE/include'
headers = ['EGL/egl.h', 'EGL/eglext.h', 'GLES2/gl2.h', 'GLES2/gl2ext.h', 'GLES3/gl3.h']

with tempfile.TemporaryDirectory() as temp:
    unit = pathlib.Path(temp) / 'all.cpp'
    unit.write_text(''.join(f'#include <{h}>\n' for h in headers))
    # Preprocessing resolves the headers' platform guards and needs windows.h to exist, not its contents.
    (pathlib.Path(temp) / 'windows.h').write_text('')
    preprocessed = subprocess.run([clang, '/nologo', '/E', '/TP', f'/I{inc}', f'/I{temp}', '/DKHRONOS_STATIC', '/DGL_GLES_PROTOTYPES=1',
                                   '/DEGL_EGL_PROTOTYPES=1', '/DGL_GLEXT_PROTOTYPES', '/DEGL_EGLEXT_PROTOTYPES', str(unit)],
                                  capture_output=True, text=True, check=True).stdout
declared = set(re.findall(r'\b((?:egl|gl)[A-Z]\w*)\s*\(', preprocessed))

prototypes = {}
for header in sorted(f'{d}/{f.name}' for d in ('EGL', 'GLES2', 'GLES3') for f in (inc / d).glob('*.h')):
    text = re.sub(r'\s+', ' ', (inc / header).read_text())
    for m in re.finditer(r'(EGLAPI|GL_APICALL) (.+?) ?(EGLAPIENTRY|GL_APIENTRY) (\w+) ?\((.*?)\);', text):
        if m.group(4) in declared:
            prototypes.setdefault(m.group(4), (m.group(1), m.group(2).strip(), m.group(3), m.group(5).strip()))
missing = sorted(declared - set(prototypes))
assert not missing, missing

pointers = {'EGLDisplay', 'EGLContext', 'EGLSurface', 'EGLSync', 'EGLSyncKHR', 'EGLImage', 'EGLImageKHR', 'EGLStreamKHR', 'EGLDeviceEXT',
            'EGLClientBuffer', 'GLsync', 'GLeglImageOES', '__eglMustCastToProperFunctionPointerType'}
def body(result, name):
    if name == 'eglGetError':
        return ' return EGL_NOT_INITIALIZED; '
    if result == 'void':
        return ''
    return ' return nullptr; ' if '*' in result or result in pointers else ' return 0; '

definitions = []
for api in ('EGLAPI', 'GL_APICALL'):
    for name in sorted(prototypes):
        kind, result, entry, parameters = prototypes[name]
        if kind == api:
            parameters = ', '.join(p.strip() for p in parameters.split(',')) if parameters else 'void'
            definitions.append(f'{result} {entry} {name}({parameters}) {{{body(result, name)}}}')

header_comment = """// EGL and GLES entry points for a WebCore build that runs without a GPU (USE_ANGLE_STUB).
//
// Every EGL call fails: eglGetPlatformDisplayEXT returns EGL_NO_DISPLAY and eglGetError returns
// EGL_NOT_INITIALIZED, so creating the PlatformDisplay logs the EGL error and crashes. A host that
// links this library keeps accelerated compositing and accelerated drawing off. The GL entry
// points do nothing and return zero.
//
// The set is every EGL and GLES 2 and 3 entry point declared by ANGLE's headers on Windows,
// written by Ranvier's patches/angle_stub.py.
"""
includes = ''.join(f'#include <{h}>\n' for h in headers)
text = (header_comment + '\n' + includes + '\n#if defined(__clang__)\n#pragma clang diagnostic ignored "-Wunused-parameter"\n#endif\n\n'
        + 'extern "C" {\n\n' + '\n'.join(definitions) + '\n\n} // extern "C"\n')
target = pathlib.Path(args.source) / 'Source/ThirdParty/ANGLE/stub/ANGLEStub.cpp'
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(text, encoding='utf-8', newline='\n')
print(f'{target}: {len(definitions)} functions, {sum(1 for v in prototypes.values() if v[0] == "EGLAPI")} EGL')
