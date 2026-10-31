"""Records whether a form submission unloads the host document: page lifecycle events on the window, the document
capture listeners' events on a second submission, and the submissions the handler receives."""
import ctypes
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/abi'))
from svg_paint_probe import SvgProbe
from form_submission import SubmissionRunner, FIXTURES
from dialog_popover import CALLBACK

P, I = ctypes.c_void_p, ctypes.c_int32
runtime = Path(sys.argv[1])
cases = json.loads((FIXTURES / 'form-submission-cases.json').read_text(encoding='utf-8'))
with SvgProbe(str(runtime), 800, 600) as probe:
    runner = SubmissionRunner(probe)
    runner.load(cases['markup'], cases['eventTypes'])
    lifecycle, callbacks = [], []
    window = probe.bind('rv_host_window_event_target', P, [P])(probe.host)
    add = probe.bind('rv_event_target_add_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])
    for kind in ['pagehide', 'unload', 'beforeunload']:
        callback = CALLBACK(lambda context, event, kind=kind: lifecycle.append(kind) or 0)
        callbacks.append(callback)
        add(window, kind.encode(), 1, callback, None)
    handler = runner.install_handler()
    steps = []
    for step in [{'op': 'requestSubmit', 'id': 'g', 'submitter': 'go'}, {'op': 'flush'},
                 {'op': 'requestSubmit', 'id': 'p'}, {'op': 'flush'}]:
        events, submissions = len(runner.events), len(runner.submissions)
        result = runner.step(step)
        steps.append({'op': step['op'], 'id': step.get('id'), 'status': result.get('status'), 'lifecycle': list(lifecycle),
                      'events': [event['type'] for event in runner.events[events:]],
                      'submissions': [s['method'] + ' ' + s['url'] for s in runner.submissions[submissions:]]})
hashes = {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest() for name in ['WebCore.dll', 'RanvierWebCoreHost.dll']}
print(json.dumps({'runtime': runtime.as_posix(), 'sha256': hashes, 'handler': handler, 'steps': steps}, indent=2))
