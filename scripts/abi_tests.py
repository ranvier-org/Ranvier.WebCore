# Runs the F# ABI driver (tests/abi) against a staged runtime: the frames and events of every ABI version,
# then the teardown probes. The driver's P/Invoke declarations are checked against host/RanvierWebCoreAbi.h,
# and the generated DOM functions against the checkout's IDL files (gen/domgen.py), first. The staged libraries
# are copied next to the built driver, where .NET finds them on every platform.
#
#   abi_tests.py --stage DIR --source DIR    a directory build.py package staged, and the WebKit checkout
#                                            (the resources test serves its Ahem font)
import argparse, glob, json, os, pathlib, shutil, subprocess, sys, tempfile, time

root = pathlib.Path(__file__).resolve().parents[1]
tests = root / 'tests' / 'abi'

parser = argparse.ArgumentParser()
parser.add_argument('--stage', required=True)
parser.add_argument('--source', required=True)
args = parser.parse_args()


def run(command, **kw):
    command = [str(c) for c in command]
    print('>', subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, check=True, **kw)


def report_crash(started, stage, rid, temp):
    """After the driver died on a signal on macOS: prints .NET's crash report and the system's crash report for
    the process, with the crashed thread's frames symbolized from the package's dSYMs by atos."""
    for report in glob.glob(str(pathlib.Path(temp) / 'dump*.crashreport.json')):
        print('== .NET crash report', report, flush=True)
        print(pathlib.Path(report).read_text(errors='replace')[:20000], flush=True)
    logs = pathlib.Path.home() / 'Library/Logs/DiagnosticReports'
    # ReportCrash writes the report a moment after the process dies.
    for _ in range(30):
        found = [r for r in logs.glob('*.ips') if r.stat().st_mtime >= started] if logs.exists() else []
        if found:
            break
        time.sleep(2)
    symbols = stage / 'symbols' / rid
    for report in found:
        print('== crash report', report.name, flush=True)
        # ReportCrash may still be writing the report: read it until its body parses.
        crash = None
        for _ in range(15):
            header, _, body = report.read_text(errors='replace').partition(chr(10))
            try:
                crash = json.loads(body)
                break
            except ValueError:
                time.sleep(2)
        if crash is None:
            print(body[:4000], flush=True)
            continue
        print(json.dumps({k: crash.get(k) for k in ('exception', 'termination', 'faultingThread', 'asi')}, indent=1)[:4000], flush=True)
        images = crash.get('usedImages', [])
        for index, thread in enumerate(crash.get('threads', [])):
            if not thread.get('triggered') and index != crash.get('faultingThread'):
                continue
            print('-- crashed thread', index, flush=True)
            for frame in thread.get('frames', [])[:60]:
                image = images[frame['imageIndex']] if frame.get('imageIndex', -1) < len(images) else {}
                name = image.get('name') or pathlib.Path(image.get('path', '?')).name
                address = image.get('base', 0) + frame.get('imageOffset', 0)
                symbol = frame.get('symbol', '')
                dwarf = symbols / f'{name}.dSYM' / 'Contents/Resources/DWARF'
                dsym = next(dwarf.glob('*'), None) if dwarf.exists() else None
                if dsym:
                    symbol = subprocess.run(['atos', '-o', str(dsym), '-arch', 'arm64', '-l', hex(image['base']), hex(address)],
                                            capture_output=True, text=True).stdout.strip() or symbol
                print(f'  {name} +{frame.get("imageOffset", 0):#x} {symbol}', flush=True)


run([sys.executable, '-I', tests / 'generate_native.py', 'check'])
run([sys.executable, '-I', root / 'gen' / 'domgen.py', 'check', '--source', args.source])
stage = pathlib.Path(args.stage)
rid = json.loads((stage / 'manifest.json').read_text())['rid']
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp:
    out = pathlib.Path(temp) / 'driver'
    run(['dotnet', 'build', tests / 'RanvierWebCoreAbi.Driver.fsproj', '-c', 'Release', '--nologo', '-v', 'q', '-o', out])
    shutil.copytree(stage / 'runtimes' / rid / 'native', out, dirs_exist_ok=True)
    env = dict(os.environ, RANVIER_WEBKIT_SOURCE=args.source, RANVIER_WEBCORE_OUT=str(pathlib.Path(temp) / 'run'),
               RANVIER_TRACE='1')
    if sys.platform == 'darwin':
        # A native crash writes .NET's crash report, with the native frames of each thread, next to a minidump.
        env.update(DOTNET_DbgEnableMiniDump='1', DOTNET_DbgMiniDumpType='1', DOTNET_EnableCrashReport='1',
                   DOTNET_DbgMiniDumpName=str(pathlib.Path(temp) / 'dump.%d'))
    driver = out / 'RanvierWebCoreAbi.Driver.dll'
    started = time.time()
    try:
        run(['dotnet', driver], env=env)
    except subprocess.CalledProcessError as error:
        if sys.platform == 'darwin' and error.returncode < 0:
            report_crash(started, stage, rid, temp)
        raise
    run(['dotnet', driver], env=dict(env, RANVIER_WEBCORE_PROBE='teardown'))
    run([sys.executable, '-I', tests / 'table_surface.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'element_reflection.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'area_surface.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'cssom_surface.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'keyframe_rules.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'counter_style_rules.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'custom_properties.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'typed_style_values.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'style_property_maps.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'declared_style_maps.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'style_map_entries.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'geometry_values.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'matrix_values.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'css_transforms.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_geometry.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_surfaces.py', '--native-directory', out, '--webkit-source', args.source])
    run([sys.executable, '-I', tests / 'svg_documents.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_view_controls.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_animation_variants.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'detached_cssom_context.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_mathml_surface.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_paint_servers.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_filters.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_clip_mask_marker.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'svg_resources.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'image_decode.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'font_load.py', '--native-directory', out, '--webkit-source', args.source])
    run([sys.executable, '-I', tests / 'svg_tests_lists.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'mathml_surface.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'event_construction.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'focus_input.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'viewport_events.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'form_collections.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'viewport_scroll.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'dialog_popover.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'binary_values.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'caret_hit.py', '--native-directory', out, '--webkit-source', args.source])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'crypto_random.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'screen_metrics.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'url_values.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'url_wpt.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'text_segmentation.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'visual_viewport.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'custom_highlights.py', '--native-directory', out, '--webkit-source', args.source])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'blob_urls.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'abi_layouts.py'])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'aria_relations.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'coordinate_spaces.py', '--native-directory', out])
    run([sys.executable, '-I', tests / 'form_navigation.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'form_submission.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'event_details.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'string_nul.py', '--native-directory', out])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'inspector_diagnostics.py', '--native-directory', out, '--webkit-source', args.source])
    run([sys.executable, '-I', '-X', 'utf8', tests / 'cascade_diagnostics.py', '--native-directory', out])
print('abi tests passed', flush=True)
