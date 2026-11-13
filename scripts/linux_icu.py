# Builds static PIC ICU archives (libicuuc.a, libicui18n.a, libicudata.a) and a static HarfBuzz-ICU
# adapter (libharfbuzz-icu.a) on Linux from the pinned ICU source tarball in pins.json, so
# libRanvierWebCoreHost.so has no runtime dependency on a distribution's versioned libicu*.so.<major>
# or libharfbuzz-icu.so.0.
#
#   linux_icu.py --archive FILE --out DIR [--unfiltered] [--jobs N]
import argparse, hashlib, importlib.util, json, os, pathlib, shutil, subprocess, sys, tarfile, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
_ICU_DATA_SPEC = importlib.util.spec_from_file_location('icu_data', ROOT / 'scripts/icu_data.py')
_ICU_DATA = importlib.util.module_from_spec(_ICU_DATA_SPEC)
_ICU_DATA_SPEC.loader.exec_module(_ICU_DATA)
keep = _ICU_DATA.keep

HB_ICU_HEADER = """\
#ifndef HB_ICU_H
#define HB_ICU_H
#include <hb.h>
#include <unicode/uscript.h>
HB_BEGIN_DECLS
HB_EXTERN hb_script_t hb_icu_script_to_script (UScriptCode script);
HB_EXTERN UScriptCode hb_icu_script_from_script (hb_script_t script);
HB_EXTERN hb_unicode_funcs_t * hb_icu_get_unicode_funcs (void);
HB_END_DECLS
#endif
"""

HB_ICU_SOURCE = """\
#include <hb.h>
#include <hb-icu.h>
#include <unicode/uchar.h>
#include <unicode/unorm2.h>
#include <unicode/uscript.h>
#include <unicode/ustring.h>
#include <unicode/utf16.h>

extern "C" hb_script_t hb_icu_script_to_script(UScriptCode script)
{
    if (script == USCRIPT_INVALID_CODE)
        return HB_SCRIPT_INVALID;
    return hb_script_from_string(uscript_getShortName(script), -1);
}

extern "C" UScriptCode hb_icu_script_from_script(hb_script_t script)
{
    if (script == HB_SCRIPT_INVALID)
        return USCRIPT_INVALID_CODE;
    unsigned int maxScript = 1 + static_cast<unsigned int>(u_getIntPropertyMaxValue(UCHAR_SCRIPT));
    for (unsigned int i = 0; i < maxScript; ++i) {
        if (hb_icu_script_to_script(static_cast<UScriptCode>(i)) == script)
            return static_cast<UScriptCode>(i);
    }
    return USCRIPT_UNKNOWN;
}

static hb_unicode_combining_class_t hb_icu_unicode_combining_class(hb_unicode_funcs_t*, hb_codepoint_t unicode, void*)
{
    return static_cast<hb_unicode_combining_class_t>(u_getCombiningClass(unicode));
}

static hb_unicode_general_category_t hb_icu_unicode_general_category(hb_unicode_funcs_t*, hb_codepoint_t unicode, void*)
{
    switch (u_getIntPropertyValue(unicode, UCHAR_GENERAL_CATEGORY)) {
    case U_UNASSIGNED: return HB_UNICODE_GENERAL_CATEGORY_UNASSIGNED;
    case U_UPPERCASE_LETTER: return HB_UNICODE_GENERAL_CATEGORY_UPPERCASE_LETTER;
    case U_LOWERCASE_LETTER: return HB_UNICODE_GENERAL_CATEGORY_LOWERCASE_LETTER;
    case U_TITLECASE_LETTER: return HB_UNICODE_GENERAL_CATEGORY_TITLECASE_LETTER;
    case U_MODIFIER_LETTER: return HB_UNICODE_GENERAL_CATEGORY_MODIFIER_LETTER;
    case U_OTHER_LETTER: return HB_UNICODE_GENERAL_CATEGORY_OTHER_LETTER;
    case U_NON_SPACING_MARK: return HB_UNICODE_GENERAL_CATEGORY_NON_SPACING_MARK;
    case U_ENCLOSING_MARK: return HB_UNICODE_GENERAL_CATEGORY_ENCLOSING_MARK;
    case U_COMBINING_SPACING_MARK: return HB_UNICODE_GENERAL_CATEGORY_SPACING_MARK;
    case U_DECIMAL_DIGIT_NUMBER: return HB_UNICODE_GENERAL_CATEGORY_DECIMAL_NUMBER;
    case U_LETTER_NUMBER: return HB_UNICODE_GENERAL_CATEGORY_LETTER_NUMBER;
    case U_OTHER_NUMBER: return HB_UNICODE_GENERAL_CATEGORY_OTHER_NUMBER;
    case U_SPACE_SEPARATOR: return HB_UNICODE_GENERAL_CATEGORY_SPACE_SEPARATOR;
    case U_LINE_SEPARATOR: return HB_UNICODE_GENERAL_CATEGORY_LINE_SEPARATOR;
    case U_PARAGRAPH_SEPARATOR: return HB_UNICODE_GENERAL_CATEGORY_PARAGRAPH_SEPARATOR;
    case U_CONTROL_CHAR: return HB_UNICODE_GENERAL_CATEGORY_CONTROL;
    case U_FORMAT_CHAR: return HB_UNICODE_GENERAL_CATEGORY_FORMAT;
    case U_PRIVATE_USE_CHAR: return HB_UNICODE_GENERAL_CATEGORY_PRIVATE_USE;
    case U_SURROGATE: return HB_UNICODE_GENERAL_CATEGORY_SURROGATE;
    case U_DASH_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_DASH_PUNCTUATION;
    case U_START_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_OPEN_PUNCTUATION;
    case U_END_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_CLOSE_PUNCTUATION;
    case U_CONNECTOR_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_CONNECT_PUNCTUATION;
    case U_OTHER_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_OTHER_PUNCTUATION;
    case U_MATH_SYMBOL: return HB_UNICODE_GENERAL_CATEGORY_MATH_SYMBOL;
    case U_CURRENCY_SYMBOL: return HB_UNICODE_GENERAL_CATEGORY_CURRENCY_SYMBOL;
    case U_MODIFIER_SYMBOL: return HB_UNICODE_GENERAL_CATEGORY_MODIFIER_SYMBOL;
    case U_OTHER_SYMBOL: return HB_UNICODE_GENERAL_CATEGORY_OTHER_SYMBOL;
    case U_INITIAL_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_INITIAL_PUNCTUATION;
    case U_FINAL_PUNCTUATION: return HB_UNICODE_GENERAL_CATEGORY_FINAL_PUNCTUATION;
    default: return HB_UNICODE_GENERAL_CATEGORY_UNASSIGNED;
    }
}

static hb_codepoint_t hb_icu_unicode_mirroring(hb_unicode_funcs_t*, hb_codepoint_t unicode, void*)
{
    return u_charMirror(unicode);
}

static hb_script_t hb_icu_unicode_script(hb_unicode_funcs_t*, hb_codepoint_t unicode, void*)
{
    UErrorCode status = U_ZERO_ERROR;
    UScriptCode scriptCode = uscript_getScript(unicode, &status);
    if (U_FAILURE(status))
        return HB_SCRIPT_UNKNOWN;
    return hb_icu_script_to_script(scriptCode);
}

static hb_bool_t hb_icu_unicode_compose(hb_unicode_funcs_t*, hb_codepoint_t a, hb_codepoint_t b, hb_codepoint_t* ab, void* user_data)
{
    const UNormalizer2* normalizer = static_cast<const UNormalizer2*>(user_data);
    UChar32 ret = unorm2_composePair(normalizer, a, b);
    if (ret < 0)
        return false;
    *ab = static_cast<hb_codepoint_t>(ret);
    return true;
}

static hb_bool_t hb_icu_unicode_decompose(hb_unicode_funcs_t*, hb_codepoint_t ab, hb_codepoint_t* a, hb_codepoint_t* b, void* user_data)
{
    const UNormalizer2* normalizer = static_cast<const UNormalizer2*>(user_data);
    UChar decomposed[4];
    UErrorCode err = U_ZERO_ERROR;
    int32_t len = unorm2_getRawDecomposition(normalizer, ab, decomposed, 4, &err);
    if (U_FAILURE(err) || len < 0)
        return false;
    int32_t count = u_countChar32(decomposed, len);
    if (count == 1) {
        U16_GET_UNSAFE(decomposed, 0, *a);
        *b = 0;
        return *a != ab;
    }
    if (count == 2) {
        int32_t idx = 0;
        U16_NEXT_UNSAFE(decomposed, idx, *a);
        U16_NEXT_UNSAFE(decomposed, idx, *b);
    }
    return true;
}

static hb_unicode_funcs_t* create_icu_unicode_funcs()
{
    UErrorCode err = U_ZERO_ERROR;
    const UNormalizer2* nfc = unorm2_getNFCInstance(&err);
    hb_unicode_funcs_t* funcs = hb_unicode_funcs_create(nullptr);
    hb_unicode_funcs_set_combining_class_func(funcs, hb_icu_unicode_combining_class, nullptr, nullptr);
    hb_unicode_funcs_set_general_category_func(funcs, hb_icu_unicode_general_category, nullptr, nullptr);
    hb_unicode_funcs_set_mirroring_func(funcs, hb_icu_unicode_mirroring, nullptr, nullptr);
    hb_unicode_funcs_set_script_func(funcs, hb_icu_unicode_script, nullptr, nullptr);
    if (U_SUCCESS(err) && nfc) {
        hb_unicode_funcs_set_compose_func(funcs, hb_icu_unicode_compose, const_cast<UNormalizer2*>(nfc), nullptr);
        hb_unicode_funcs_set_decompose_func(funcs, hb_icu_unicode_decompose, const_cast<UNormalizer2*>(nfc), nullptr);
    }
    hb_unicode_funcs_make_immutable(funcs);
    return funcs;
}

extern "C" hb_unicode_funcs_t* hb_icu_get_unicode_funcs(void)
{
    static hb_unicode_funcs_t* funcs = create_icu_unicode_funcs();
    return funcs;
}
"""

REQUIRED_ARCHIVES = ('libicuuc.a', 'libicui18n.a', 'libicudata.a', 'libharfbuzz-icu.a')


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def run(command, *, cwd=None, env=None):
    command = [str(part) for part in command]
    print('>', subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def expected_stamp(icu_pin, filtered, cc_line):
    return {
        'version': icu_pin['version'],
        'sha256': icu_pin['sha256'],
        'data_sha256': icu_pin['data_sha256'],
        'filtered': filtered,
        'compiler': cc_line,
        'script_sha256': file_sha256(pathlib.Path(__file__).resolve()),
        'filter_sha256': file_sha256(ROOT / 'scripts/icu_data.py'),
    }


def is_up_to_date(out, stamp):
    stamp_file = out / 'ranvier-icu.json'
    if not stamp_file.exists():
        return False
    try:
        recorded = json.loads(stamp_file.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    if recorded != stamp:
        return False
    if not (out / 'include/unicode/uvernum.h').exists() or not (out / 'include/hb-icu.h').exists():
        return False
    return all((out / 'lib' / name).exists() for name in REQUIRED_ARCHIVES)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', required=True, help='verified ICU source tarball')
    parser.add_argument('--out', required=True, help='install prefix (<work>/tools/icu)')
    parser.add_argument('--unfiltered', action='store_true', help='keep full ICU data (lean flavor)')
    parser.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    args = parser.parse_args()

    pins = json.loads((ROOT / 'pins.json').read_text(encoding='utf-8'))
    icu = pins['icu']
    major = icu['version'].split('_', 1)[0]
    entry = f'icudt{major}'
    filtered = not args.unfiltered

    cc = os.environ.get('CC', 'clang')
    cxx = os.environ.get('CXX', 'clang++')
    ar = os.environ.get('AR', 'ar')
    cc_line = subprocess.run([cxx, '--version'], capture_output=True, text=True, check=True).stdout.splitlines()[0]

    out = pathlib.Path(args.out).resolve()
    stamp = expected_stamp(icu, filtered, cc_line)
    if is_up_to_date(out, stamp):
        print(f'linux_icu: {out} is up to date ({icu["version"]}, filtered={filtered})', flush=True)
        return

    archive = pathlib.Path(args.archive).resolve()
    actual_archive_sha = file_sha256(archive)
    if actual_archive_sha != icu['sha256']:
        sys.exit(f'{archive}: sha256 {actual_archive_sha}, pins.json expects {icu["sha256"]}')

    t0 = time.monotonic()
    work = out.with_name(out.name + '.build')
    stage = out.with_name(out.name + '.stage')
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(stage, ignore_errors=True)
    src = work / 'src'
    bld = work / 'build'
    (bld / 'lib').mkdir(parents=True)
    (bld / 'bin').mkdir(parents=True)

    print(f'linux_icu: extracting {archive.name}', flush=True)
    with tarfile.open(archive) as tar:
        tar.extractall(src, filter='data')

    dat_source = src / icu['data']
    actual_data_sha = file_sha256(dat_source)
    if actual_data_sha != icu['data_sha256']:
        sys.exit(f'{dat_source}: sha256 {actual_data_sha}, pins.json expects {icu["data_sha256"]}')

    common_flags = '-O2 -fPIC -ffunction-sections -fdata-sections -fvisibility=hidden'
    env = dict(
        os.environ,
        CC=cc,
        CXX=cxx,
        CFLAGS=common_flags,
        CXXFLAGS=f'{common_flags} -fvisibility-inlines-hidden',
    )

    run([
        src / 'icu/source/configure',
        f'--prefix={stage}',
        '--enable-static',
        '--disable-shared',
        '--disable-dyload',
        '--disable-tests',
        '--disable-samples',
        '--disable-extras',
        '--disable-icuio',
        '--disable-layoutex',
        '--with-data-packaging=static',
    ], cwd=bld, env=env)

    jobs = f'-j{max(1, args.jobs)}'
    for sub in ('stubdata', 'common', 'i18n', 'tools/toolutil', 'tools/icupkg', 'tools/genccode'):
        run(['make', jobs, '-C', sub], cwd=bld, env=env)
    for sub in ('common', 'i18n'):
        run(['make', '-C', sub, 'install-local'], cwd=bld, env=env)

    icupkg = bld / 'bin/icupkg'
    genccode = bld / 'bin/genccode'
    dwork = bld / 'data-work'
    dwork.mkdir()
    if filtered:
        items = subprocess.run([str(icupkg), '-l', str(dat_source)], capture_output=True, text=True, check=True).stdout.split()
        removed = [item for item in items if not keep(item)]
        (dwork / 'removed.txt').write_text('\n'.join(removed) + '\n', encoding='utf-8')
        dat_input = dwork / dat_source.name
        run([icupkg, '-r', dwork / 'removed.txt', dat_source, dat_input])
        print(f'linux_icu: {dat_source.name} ({dat_source.stat().st_size} bytes), {len(items)} items; '
              f'kept {len(items) - len(removed)}, removed {len(removed)}; filtered {dat_input.stat().st_size} bytes', flush=True)
    else:
        dat_input = dat_source

    run([genccode, '-a', 'gcc', '-e', entry, '-d', dwork, dat_input])
    asm = next(dwork.glob(f'{dat_input.stem}_dat.*'))
    dat_obj = dwork / 'icudata.o'
    run([cc, '-c', '-fPIC', '-DU_HIDE_DATA_SYMBOL', asm, '-o', dat_obj])
    run([ar, 'rcs', stage / 'lib/libicudata.a', dat_obj])

    hb_cflags = [
        flag for flag in subprocess.run(['pkg-config', '--cflags', 'harfbuzz'], capture_output=True, text=True, check=True).stdout.split()
        if flag not in ('-I/usr/include', '-isystem/usr/include')
    ]
    hb_inc = subprocess.run(['pkg-config', '--variable=includedir', 'harfbuzz'], capture_output=True, text=True, check=True).stdout.strip()
    hb_icu_candidates = [pathlib.Path(hb_inc) / 'harfbuzz/hb-icu.h', pathlib.Path(hb_inc) / 'hb-icu.h']
    existing_header = next((candidate for candidate in hb_icu_candidates if candidate.exists()), None)
    if existing_header is not None:
        shutil.copy2(existing_header, stage / 'include/hb-icu.h')
    else:
        (stage / 'include/hb-icu.h').write_text(HB_ICU_HEADER, encoding='utf-8')

    hb_cpp = bld / 'hb_icu.cpp'
    hb_obj = bld / 'hb_icu.o'
    hb_cpp.write_text(HB_ICU_SOURCE, encoding='utf-8')
    run([
        cxx, '-std=c++17', '-O2', '-fPIC', '-ffunction-sections', '-fdata-sections',
        '-fvisibility=hidden', '-fvisibility-inlines-hidden', '-DU_STATIC_IMPLEMENTATION',
        f'-I{stage / "include"}', *hb_cflags, '-c', hb_cpp, '-o', hb_obj,
    ])
    run([ar, 'rcs', stage / 'lib/libharfbuzz-icu.a', hb_obj])

    (stage / 'ranvier-icu.json').write_text(json.dumps(stamp, indent=2) + '\n', encoding='utf-8')
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(out, ignore_errors=True)
    stage.replace(out)
    shutil.rmtree(work, ignore_errors=True)
    sizes = ', '.join(f'{name}={((out / "lib" / name).stat().st_size / 1e6):.2f}MB' for name in REQUIRED_ARCHIVES)
    print(f'linux_icu: built {out} in {time.monotonic() - t0:.1f}s ({sizes})', flush=True)


if __name__ == '__main__':
    main()
