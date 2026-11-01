# Runs the probes of a staged runtime, the checks the native job of .github/workflows/build.yml runs after smoke.py
# (docs/CI.md, "Probes"). Every probe runs, in the order of PROBES, whatever the earlier ones did; the run exits 1
# when any probe failed or timed out.
#
#   probes.py run --rid RID --flavor FLAVOR --work DIR     run the probes that apply to the runtime
#             [--logs DIR] [--only TEXT] [--timeout S]      (logs default to <work>/probe-logs; --no-dump on
#             [--no-dump]                                   Linux makes the probe interpreters non-dumpable)
#   probes.py list [--rid RID --flavor FLAVOR]              print the probes, as workflow steps would state them
#
# Each probe's output goes to the job log inside a ::group:: and to <logs>/<NN>-<name>.log. A probe of several
# commands runs them in order and stops at the first that fails. "python" in a command is this interpreter.
import argparse, json, os, pathlib, re, shlex, signal, subprocess, sys, threading, time

root = pathlib.Path(__file__).resolve().parents[1]
TIMEOUT = 600

# Placeholders of the commands, with the workflow expressions they stand for.
EXPRESSIONS = {'work': '${{ env.RANVIER_WORK }}', 'flavor': '${{ env.FLAVOR }}', 'rid': '${{ matrix.rid }}'}
NATIVE = '{work}/out/{flavor}/runtimes/{rid}/native'


def probe(name, *commands, rid=None, flavor=('slim', 'gpu'), timeout=TIMEOUT, env=None):
    """A probe: common contracts run on slim and GPU; explicit flavors restrict a probe, and None matches all."""
    return {'name': name, 'commands': [command.replace('{native}', NATIVE) for command in commands],
            'rid': rid, 'flavor': flavor, 'timeout': timeout, 'env': dict(env or {})}


PROBES = [
    *[probe('Verify Linux same-document transition snapshot pixels',
            'python -I tests/gpu/linux_view_transition_pixels.py --native-directory {native}',
            rid=rid, flavor='gpu',
            env={'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'})
      for rid in ['linux-x64', 'linux-arm64']],
    *[probe('Verify Linux shared EGLImage frames and retained lifetimes',
            'python -I tests/gpu/linux_egl.py {native}/libRanvierWebCoreHost.so',
            'python -I tests/gpu/linux_egl.py {native}/libRanvierWebCoreHost.so --context-lifecycle',
            rid=rid, flavor='gpu',
            env={'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'})
      for rid in ['linux-x64', 'linux-arm64']],
    probe('Verify Windows shared D3D11 frames and bounded lifetimes',
          'python -I scripts/sdl_runtime.py --out {work}/tools/sdl3',
          'python -I tests/gpu/run.py --native {native} --sdl {work}/tools/sdl3/SDL3.dll --teardown all',
          rid='win-x64', flavor='gpu', timeout=1200),
    probe('Exercise typed DOM transport against the packaged native host',
          'python -I tests/generator/native_types.py --native-dir {native}', rid='win-x64'),
    probe('Verify document-scoped CSS support queries',
          'python -I tests/abi/css_supports.py --native-directory {native}'),
    probe('Verify live computed styles and pseudo-elements',
          'python -I tests/abi/computed_style.py --native-directory {native}'),
    probe('Verify fragment rectangle lists and retained snapshots',
          'python -I tests/abi/fragment_rectangles.py --native-directory {native}'),
    probe('Verify paused animation effects after keyframe edits',
          'python -I tests/abi/keyframe_rules.py --native-directory {native}'),
    probe('Verify counter style name and rendered marker edits',
          'python -I tests/abi/counter_style_rules.py --native-directory {native}'),
    probe('Verify retained CSSOM settings context and isolated descriptor edits',
          'python -I tests/abi/detached_cssom_context.py --native-directory {native}'),
    probe('Verify custom property registration and interpolation',
          'python -I tests/abi/custom_properties.py --native-directory {native}'),
    probe('Verify typed CSS value parsing and owned segments',
          'python -I tests/abi/typed_style_values.py --native-directory {native}'),
    probe('Verify typed style maps',
          'python -I tests/abi/style_property_maps.py --native-directory {native}'),
    probe('Verify declared typed map mutation isolation',
          'python -I tests/abi/declared_style_maps.py --native-directory {native}'),
    probe('Verify typed style map entry snapshots',
          'python -I tests/abi/style_map_entries.py --native-directory {native}'),
    probe('Verify geometry values and retained mutable points',
          'python -I tests/abi/geometry_values.py --native-directory {native}'),
    probe('Verify matrix values and transformations',
          'python -I tests/abi/matrix_values.py --native-directory {native}'),
    probe('Verify typed CSS transform components',
          'python -I tests/abi/css_transforms.py --native-directory {native}'),
    probe('Verify SVG shapes, text and SMIL timing',
          'python -I tests/abi/svg_surfaces.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify SVG gradients, patterns and stops',
          'python -I tests/abi/svg_paint_servers.py --native-directory {native}'),
    probe('Verify every SVG filter primitive and light source',
          'python -I tests/abi/svg_filters.py --native-directory {native}'),
    probe('Verify SVG clipping, masks and markers',
          'python -I tests/abi/svg_clip_mask_marker.py --native-directory {native}'),
    probe('Verify SVG reuse, content and resource loads',
          'python -I tests/abi/svg_resources.py --native-directory {native}'),
    probe('Verify image decode readiness without JavaScript',
          'python -I tests/abi/image_decode.py --native-directory {native}'),
    probe('Verify listener removal for cancellation signals',
          'python -I tests/abi/listener_signal_removal.py --native-directory {native}'),
    probe('Verify screen wake locks',
          'python -I tests/abi/wake_locks.py --native-directory {native}'),
    probe('Verify notifications through an application presenter',
          'python -I tests/abi/notifications.py --native-directory {native}'),
    probe('Verify font readiness without JavaScript',
          'python -I tests/abi/font_load.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify FontFaceSet status, check, load, ready and events without JavaScript',
          'python -I tests/abi/font_readiness.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify FontFace construction from bytes and URLs and FontFaceSet registration without JavaScript',
          'python -I tests/abi/font_construction.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify delayed image decode readiness and drawing',
          'python -I tests/abi/image_readiness.py --native-directory {native}'),
    probe('Verify SVGTests lists after attribute removal',
          'python -I tests/abi/svg_tests_lists.py --native-directory {native}'),
    probe('Verify typed MathML elements, styling and focus',
          'python -I tests/abi/mathml_surface.py --native-directory {native}'),
    probe('Verify typed and custom event construction and standalone targets',
          'python -I tests/abi/event_construction.py --native-directory {native}'),
    probe('Verify the window event target, activation, touch capacity and pointer capture',
          'python -I tests/abi/focus_input.py --native-directory {native}'),
    probe('Verify touch frames, touch lists and touch pointer events',
          'python -I tests/abi/touch_input.py --native-directory {native}'),
    probe('Verify pen and mouse pointer fidelity and pen capture',
          'python -I tests/abi/pen_input.py --native-directory {native}'),
    probe('Verify pointer lock requests, relative movement and loss',
          'python -I tests/abi/pointer_lock.py --native-directory {native}'),
    probe('Verify event-loop tasks run on the next run-loop turn after a timer-driven style resolution',
          'python -I tests/abi/event_loop_latency.py --native-directory {native}'),
    probe('Verify window metrics, visibility, media queries and viewport event order',
          'python -I tests/abi/viewport_events.py --native-directory {native}'),
    probe('Verify form collections, FormData and submit events against the Chromium oracle',
          'python -I -X utf8 tests/abi/form_collections.py --native-directory {native}'),
    probe('Verify fractional viewport and element scrolling against the Chromium oracle',
          'python -I -X utf8 tests/abi/viewport_scroll.py --native-directory {native}'),
    probe('Verify dialogs, popovers and command invokers against the Chromium oracle',
          'python -I -X utf8 tests/abi/dialog_popover.py --native-directory {native}'),
    probe('Verify Blob, File and FileList values against the Chromium oracle',
          'python -I -X utf8 tests/abi/binary_values.py --native-directory {native}'),
    probe('Verify caret hit testing against the Chromium oracle',
          'python -I -X utf8 tests/abi/caret_hit.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify crypto.getRandomValues and crypto.randomUUID against the Chromium oracle',
          'python -I -X utf8 tests/abi/crypto_random.py --native-directory {native}'),
    probe('Verify the app-set screen and orientation against the Chromium oracle',
          'python -I -X utf8 tests/abi/screen_metrics.py --native-directory {native}'),
    probe('Verify that a zero-millisecond run-loop cycle returns without waiting',
          'python -I -X utf8 tests/abi/run_loop_cycle.py --native-directory {native}'),
    probe('Verify URL, URLSearchParams and URLPattern against the Chromium oracle',
          'python -I -X utf8 tests/abi/url_values.py --native-directory {native}'),
    probe('Verify the WPT URL and URLPattern corpus against the Chromium record',
          'python -I -X utf8 tests/abi/url_wpt.py --native-directory {native}'),
    probe('Verify grapheme, word, sentence and line segmentation against the Chromium oracle',
          'python -I -X utf8 tests/abi/text_segmentation.py --native-directory {native}'),
    probe('Verify the C layouts of the ABI structs against ctypes and the F# interop',
          'python -I tests/abi/abi_layouts.py'),
    probe('Verify coordinate-space conversion against the Chromium oracle',
          'python -I -X utf8 tests/abi/coordinate_spaces.py --native-directory {native}'),
    probe('Verify Web Animations discovery and identity against the Chromium oracle',
          'python -I -X utf8 tests/abi/web_animation_discovery.py --native-directory {native}'),
    probe('Verify Web Animations commitStyles against the Chromium oracle',
          'python -I -X utf8 tests/abi/web_animation_commit.py --native-directory {native}'),
    probe('Verify Web Animations effect inspection and mutation against the Chromium oracle',
          'python -I -X utf8 tests/abi/web_animation_effects.py --native-directory {native}'),
    probe('Verify Web Animations creation against the Chromium oracle',
          'python -I -X utf8 tests/abi/web_animations.py --native-directory {native}'),
    *[probe('Verify default compositor root reattachment',
            'python -I -X utf8 tests/gpu/compositor_reattach.py --native-directory {native}',
            rid=rid, flavor='gpu',
            env={'EGL_PLATFORM': 'surfaceless', 'LIBGL_ALWAYS_SOFTWARE': '1'} if rid.startswith('linux-') else {})
      for rid in ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64']],
    probe('Verify the Web Animations lifecycle and promises against the Chromium oracle',
          'python -I -X utf8 tests/abi/animation_lifecycle.py --native-directory {native}'),
    probe('Verify typed animation and transition events against the Chromium oracle',
          'python -I -X utf8 tests/abi/animation_events.py --native-directory {native}'),
    probe('Verify animation timelines against the Chromium oracle',
          'python -I -X utf8 tests/abi/animation_timelines.py --native-directory {native}'),
    probe('Verify Web Animations custom effects against the Chromium oracle',
          'python -I -X utf8 tests/abi/custom_effects.py --native-directory {native}'),
    probe('Verify same-document view transitions and the slim compositing gate',
          'python -I -X utf8 tests/abi/view_transitions.py --native-directory {native}', flavor=None),
    probe('Verify ARIA element reflection and accessibility relations against the Chromium oracle',
          'python -I -X utf8 tests/abi/aria_relations.py --native-directory {native}'),
    probe('Verify the visual viewport, page scale and obscured insets against the Chromium oracle',
          'python -I -X utf8 tests/abi/visual_viewport.py --native-directory {native}'),
    probe('Verify custom highlight registries, ordered highlights and their painted ranges against the Chromium oracle',
          'python -I -X utf8 tests/abi/custom_highlights.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify blob URLs, blob reads and FileReader against the Chromium oracle',
          'python -I -X utf8 tests/abi/blob_urls.py --native-directory {native}'),
    probe('Verify resize observation box options, entries and delivery order against the Chromium oracle',
          'python -I -X utf8 tests/abi/resize_observation.py --native-directory {native}'),
    probe('Verify intersection observation roots, margins, entries and takeRecords against the Chromium oracle',
          'python -I -X utf8 tests/abi/intersection_observation.py --native-directory {native}'),
    probe('Verify media capability queries, their delivery and teardown against the Chromium oracle',
          'python -I -X utf8 tests/abi/media_capabilities.py --native-directory {native}'),
    probe('Verify snapshot scale, crop, color space, encodings and delivery',
          'python -I -X utf8 tests/abi/snapshot_options.py --native-directory {native}'),
    probe('Verify form submission keeps the host document',
          'python -I tests/abi/form_navigation.py --native-directory {native}'),
    probe('Verify form submission reporting against the Chromium oracle',
          'python -I -X utf8 tests/abi/form_submission.py --native-directory {native}'),
    probe('Verify event detail adapters against the Chromium oracle',
          'python -I -X utf8 tests/abi/event_details.py --native-directory {native}'),
    probe('Verify DOM node, event and matrix value factories against the Chromium oracle',
          'python -I -X utf8 tests/abi/value_factories.py --native-directory {native}'),
    probe('Verify U+0000 round trips of generated string inputs against the Chromium oracle',
          'python -I -X utf8 tests/abi/string_nul.py --native-directory {native}'),
    probe('Verify U+0000 round trips of hand-written string inputs against the Chromium oracle',
          'python -I -X utf8 tests/abi/host_string_nul.py --native-directory {native}'),
    probe('Verify the DataTransfer object model, drag and clipboard payloads and range replacement against the Chromium oracle',
          'python -I -X utf8 tests/abi/data_transfer.py --native-directory {native}'),
    probe('Verify the native inspector diagnostics against the Chromium box-model oracle',
          'python -I -X utf8 tests/abi/inspector_diagnostics.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify the native cascade diagnostics against the shared conformance fixture',
          'python -I -X utf8 tests/abi/cascade_diagnostics.py --native-directory {native}'),
    probe("Verify media query evaluation and the host's media preferences against the shared conformance fixture",
          'python -I -X utf8 tests/abi/media_queries.py --native-directory {native}'),
    probe('Verify the canvas 2D context lifecycle against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_context.py --native-directory {native}'),
    probe('Verify canvas paths and hit testing against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_paths.py --native-directory {native}'),
    probe('Verify canvas state, transforms and compositing against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_state.py --native-directory {native}'),
    probe('Verify canvas paints against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_paints.py --native-directory {native}'),
    probe('Verify canvas text and TextMetrics against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_text.py --native-directory {native} --webkit-source {work}/src'),
    probe('Verify canvas pixel operations against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_pixels.py --native-directory {native}'),
    probe('Verify canvas export and image bitmaps against the Chromium oracle',
          'python -I -X utf8 tests/abi/canvas_export.py --native-directory {native}'),
    probe('Verify passive capability catalogue and live host observations',
          'python -I tests/abi/capabilities.py --native-directory {native}', flavor=None),
    probe('Verify explicit current SVG document view selection',
          'python -I tests/abi/svg_view_selection.py --native-directory {native}', flavor=None),
    probe('Verify SVG document parsing, guards and transitions',
          'python -I tests/abi/svg_documents.py --native-directory {native}'),
    probe('Verify SVG view coordinates and paint',
          'python -I tests/abi/svg_view_controls.py --native-directory {native}'),
    probe('Verify concrete SVG animation effects',
          'python -I tests/abi/svg_animation_variants.py --native-directory {native}'),
    probe('Verify table element surfaces',
          'python -I tests/abi/table_surface.py --native-directory {native}'),
    probe('Verify reflected element attributes',
          'python -I tests/abi/element_reflection.py --native-directory {native}'),
    probe('Verify area element surfaces',
          'python -I tests/abi/area_surface.py --native-directory {native}'),
    probe('Verify CSSOM rule surfaces',
          'python -I tests/abi/cssom_surface.py --native-directory {native}'),
    probe('Verify SVG geometry and value bindings',
          'python -I tests/abi/svg_geometry.py --native-directory {native}'),
    probe('Verify shared SVG/MathML members',
          'python -I tests/abi/svg_mathml_surface.py --native-directory {native}'),
    probe('Build Windows UI Automation OS clients',
          'python -I tests/uia/run.py --stage {work}/out/{flavor} --build-dir {work}/build-{flavor} --build-only', rid='win-x64',
          timeout=1200),
    probe('Exercise Windows UI Automation and teardown',
          'python -I tests/uia/check_exports.py {native}',
          *[f'python -I tests/uia/run.py --stage {{work}}/out/{{flavor}} --run-only --teardown {mode}'
            for mode in ['explicit', 'host', 'window', 'sync', 'overflow']], rid='win-x64'),
    probe('Build and exercise the accessibility cache lifetime probe',
          'python -I tests/uia/run.py --stage {work}/out/{flavor} --build-dir {work}/build-{flavor} --cache-probe --build-only',
          'python -I tests/uia/run.py --stage {work}/out/{flavor} --cache-probe --run-only --teardown cache', rid='win-x64',
          timeout=1200),
]


def condition(entry):
    """The probe's condition as a workflow `if:` states it, or None for a probe that always runs."""
    parts = []
    if entry['rid']:
        parts.append(f"matrix.rid == '{entry['rid']}'")
    if entry['flavor']:
        parts.append(f"env.FLAVOR == '{entry['flavor']}'")
    return ' && '.join(parts) or None


def applies(entry, rid, flavor):
    flavors = entry['flavor']
    return entry['rid'] in (None, rid) and (flavors is None or flavor in (
        flavors if isinstance(flavors, (tuple, list)) else (flavors,)))


def workflow_text(command):
    """The command as a workflow step writes it: a word with a placeholder is quoted, in the expressions' terms."""
    words = []
    for word in shlex.split(command):
        if '{' in word:
            word = '"' + word.format(**EXPRESSIONS) + '"'
        words.append(word)
    return ' '.join(words)


def argv(command, values, no_dump=False):
    """The command's arguments for the runtime: placeholders filled in, and "python" this interpreter. With no_dump,
    the interpreter makes itself non-dumpable before it runs the script, so a crash writes no core dump."""
    words = [word.format(**values) for word in shlex.split(command)]
    if words[0] != 'python':
        return words
    if not no_dump:
        return [sys.executable, *words[1:]]
    # execve resets the dumpable flag, so the probe's own interpreter clears it: prctl(PR_SET_DUMPABLE, 0).
    at = next(index for index, word in enumerate(words) if word.endswith('.py'))
    flags = words[1:at]
    boot = ('import ctypes, os, runpy, sys; ctypes.CDLL(None).prctl(4, 0); sys.argv = sys.argv[1:]; '
            + ('' if '-I' in flags else 'sys.path.insert(0, os.path.dirname(os.path.abspath(sys.argv[0]))); ')
            + "runpy.run_path(sys.argv[0], run_name='__main__')")
    return [sys.executable, *flags, '-c', boot, *words[at:]]


def kill(process):
    """Ends the process and its descendants."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)], capture_output=True)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def execute(command, log, deadline, env=None):
    """Runs the command, copying its output to the job log and to the log file. Returns its exit code, or None when
    it outlived the deadline and was killed."""
    log.write(f'> {subprocess.list2cmdline(command)}\n'.encode())
    sys.stdout.write(f'> {subprocess.list2cmdline(command)}\n')
    sys.stdout.flush()
    options = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session': True}
    process = subprocess.Popen(command, cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, env=dict(os.environ, **(env or {})), **options)

    def copy():
        for line in iter(process.stdout.readline, b''):
            log.write(line)
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    reader = threading.Thread(target=copy, daemon=True)
    reader.start()
    try:
        code = process.wait(timeout=max(deadline - time.monotonic(), 0))
    except subprocess.TimeoutExpired:
        kill(process)
        process.wait()
        code = None
    # A descendant that keeps the pipe open would otherwise hold the reader past the probe.
    reader.join(timeout=10)
    if not reader.is_alive():
        process.stdout.close()
    return code


def run(args):
    values = {'work': str(pathlib.Path(args.work)), 'flavor': args.flavor, 'rid': args.rid}
    logs = pathlib.Path(args.logs or pathlib.Path(args.work) / 'probe-logs')
    logs.mkdir(parents=True, exist_ok=True)
    selected = [(index, entry) for index, entry in enumerate(PROBES, 1)
                if applies(entry, args.rid, args.flavor) and (not args.only or args.only in json.dumps(entry))]
    results = []
    for index, entry in selected:
        stem = re.sub(r'[^a-z0-9]+', '-', entry['name'].lower()).strip('-')[:60]
        path = logs / f'{index:02d}-{stem}.log'
        timeout = args.timeout or entry['timeout']
        print(f"::group::{entry['name']}", flush=True)
        start = time.monotonic()
        deadline = start + timeout
        outcome = 'PASS'
        with open(path, 'wb') as log:
            for command in entry['commands']:
                code = execute(argv(command, values, args.no_dump), log, deadline, entry.get('env'))
                if code is None:
                    outcome = f'FAIL (timed out after {timeout} s)'
                elif code:
                    outcome = f'FAIL (exit code {code})'
                if outcome != 'PASS':
                    log.write(f'{outcome}\n'.encode())
                    break
        seconds = time.monotonic() - start
        print('::endgroup::', flush=True)
        print(f"{outcome[:4]} {seconds:7.1f} s  {entry['name']}", flush=True)
        if outcome != 'PASS':
            print(f"::error title=Probe failed::{entry['name']}: {outcome[5:]}; log {path.name}", flush=True)
        results.append((entry['name'], outcome, seconds, path.name))
    failed = [result for result in results if result[1] != 'PASS']
    lines = [f'{outcome[:4]} {seconds:7.1f} s  {name}' + (f'  {outcome[5:]}, {log}' if outcome != 'PASS' else '')
             for name, outcome, seconds, log in results]
    print(f'\nProbes: {len(results) - len(failed)} passed, {len(failed)} failed, of {len(results)}', flush=True)
    print('\n'.join(lines), flush=True)
    (logs / 'summary.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as out:
            out.write(f'### Probes: {len(results) - len(failed)} passed, {len(failed)} failed\n\n'
                      '| Result | Seconds | Probe |\n|---|---:|---|\n')
            out.writelines(f'| {outcome} | {seconds:.1f} | {name} |\n' for name, outcome, seconds, _ in results)
    return 1 if failed else 0


def list_probes(args):
    for entry in PROBES:
        if args.rid and args.flavor and not applies(entry, args.rid, args.flavor):
            continue
        print(json.dumps({'name': entry['name'], 'if': condition(entry),
                          'run': [workflow_text(command) for command in entry['commands']], 'timeout': entry['timeout'],
                          'env': entry.get('env', {})}))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    r = sub.add_parser('run')
    r.add_argument('--rid', required=True)
    r.add_argument('--flavor', required=True)
    r.add_argument('--work', required=True, help='the work directory: the staged runtime is <work>/out/<flavor>')
    r.add_argument('--logs', help='the directory for the probe logs (default: <work>/probe-logs)')
    r.add_argument('--only', help='run only the probes whose name or commands contain the text')
    r.add_argument('--timeout', type=float, help='seconds each probe may take, in place of its own limit')
    r.add_argument('--no-dump', action='store_true',
                   help='Linux: the probe interpreters are not dumpable (WSL writes a core of every crash to Windows)')
    listing = sub.add_parser('list')
    listing.add_argument('--rid')
    listing.add_argument('--flavor')
    args = parser.parse_args(argv)
    return {'run': run, 'list': list_probes}[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
