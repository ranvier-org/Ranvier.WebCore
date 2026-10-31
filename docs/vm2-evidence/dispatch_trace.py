"""Where revised patch 0052's checkpoint dispatch runs: hardware execute breakpoints (vm1's hwtrace) on
MicrotaskQueue::performMicrotaskCheckpoint and RunLoop::performWork while tests/abi/event_loop_latency.py and vm1's cancel and
pause+cancel scenarios run in this process. For every checkpoint whose stack holds RunLoop::performWork, the report
records whether rv_run_loop_cycle is below it and how many performWork frames the stack holds (1: no re-entry).
usage: dispatch_trace.py <runtime dir with pdbs> <out json>"""
import json
from pathlib import Path
import sys

runtime, out = sys.argv[1], Path(sys.argv[2])
repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, 'C:/wk/vm1-artifacts/probe')
sys.path.insert(0, str(repo / 'tests/abi'))
import hwtrace  # noqa: E402

from form_collections import Native  # noqa: E402
n = Native(runtime)
tracer = hwtrace.Tracer(runtime + ';C:/wk/build-win-slim/bin')
targets = [('checkpoint', 'WebCore!WebCore::MicrotaskQueue::performMicrotaskCheckpoint'),
           ('performWork', 'JavaScriptCore!WTF::RunLoop::performWork')]
tracer.arm([(label, tracer.address(name)) for label, name in targets])
import event_loop_latency  # noqa: E402
tracer.mark('event_loop_latency')
event_loop_latency.verify(runtime, None)
import web_animations as wa  # noqa: E402
import animation_lifecycle as al  # noqa: E402
for scenario in ['cancel', 'pausecancel']:
    tracer.mark(scenario)
    probe = al.Probe(n, '<div id="a" style="width:9px;height:9px"></div>')
    probe.settle(2)
    a = probe.animate('a', 1000.0)
    probe.until(lambda: not n.integer('rv_dom_web_animation_get_pending', a), 'ready')
    if scenario == 'pausecancel':
        probe.act(a, 'pause')
    probe.act(a, 'cancel')
    probe.settle(4)
tracer.enabled = False
summary = {}
for label, extra, stack, mark in tracer.hits:
    if label != 'checkpoint':
        continue
    names = [tracer.name(address) for address in stack]
    work = sum('RunLoop::performWork' in name for name in names)
    key = (tracer.marks[mark - 1] if mark else '-') + (' | dispatched' if work else ' | other')
    item = summary.setdefault(key, {'count': 0, 'underRunLoopCycle': 0, 'maxPerformWorkFrames': 0, 'callers': {}})
    item['count'] += 1
    item['underRunLoopCycle'] += any('rv_run_loop_cycle' in name for name in names)
    item['maxPerformWorkFrames'] = max(item['maxPerformWorkFrames'], work)
    caller = next((name for name in names[1:] if 'performMicrotaskCheckpoint' not in name and 'hwtrace' not in name), '?')
    item['callers'][caller] = item['callers'].get(caller, 0) + 1
out.write_text(json.dumps({'runtime': runtime, 'checkpoints': summary}, indent=1), encoding='utf-8')
print(json.dumps(summary, indent=1))
