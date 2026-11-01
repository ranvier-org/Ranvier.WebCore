"""vm1 test plan steps 2 and 4 for patch 0052 on a candidate runtime (step 1 is vm1's hardware-breakpoint census,
step 3 the full native batch).
usage: vm1_steps.py <runtime dir> [--child pausecancel]
Step 2: in a child process, with crashOnDisallowedVMEntry armed around the two calls, Animation.pause() leaves a pending
pause and cancel() rejects the pending promises; the child reports the states and exits 0, or the armed crash aborts it.
Step 4: three rounds of 1000 animate+cancel (web_animations.growth) and three rounds of 1000 animate+pause+cancel with a
pending pause, private bytes sampled after a run-loop turn and a full collection; the third round stays within 16 MB of
the second."""
import ctypes
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests/abi'))
from form_collections import Native, P, I, OK  # noqa: E402
import web_animations as wa  # noqa: E402
import animation_lifecycle as al  # noqa: E402

runtime = sys.argv[1]


def child():
    n = Native(runtime)
    probe = al.Probe(n, '<div id="a" style="width:9px;height:9px"></div>')
    probe.settle(2)
    a = probe.animate('a', 1000.0)
    probe.until(lambda: not n.integer('rv_dom_web_animation_get_pending', a), 'ready')
    # Armed around the two calls only: a rendering update attempts refused VM entries of its own (vm1 census).
    armed = wa.arm_vm_entry_crash(runtime)
    print('ARMED', armed, flush=True)
    probe.act(a, 'pause')
    pending = bool(n.integer('rv_dom_web_animation_get_pending', a))
    print('PAUSED pending', pending, flush=True)
    probe.act(a, 'cancel')
    print('CANCELLED', flush=True)
    wa.arm_vm_entry_crash(runtime, False)
    probe.settle(4)
    state = probe.state(a)
    print(json.dumps({'armed': armed, 'pendingAfterPause': pending, 'afterCancel': state}), flush=True)
    print('PAUSE_CANCEL_SURVIVED', flush=True)


if len(sys.argv) > 2 and sys.argv[2] == '--child':
    child()
    raise SystemExit(0)

result = subprocess.run([sys.executable, '-I', '-X', 'utf8', __file__, runtime, '--child'], capture_output=True, text=True, timeout=300)
step2 = {'exitCode': result.returncode, 'survived': 'PAUSE_CANCEL_SURVIVED' in result.stdout,
         'stdout': result.stdout.strip().splitlines()[-6:], 'stderrTail': result.stderr.strip().splitlines()[-3:]}

n = Native(runtime)
page = wa.Page(n, '<div id="d" style="width:20px;height:20px"></div>')
animate_cancel = wa.growth(n, page)
element, arena = page.element('d'), wa.Arena()
keyframes = arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}])
options = arena.options(wa.AnimationOptions, wa.KeyframeAnimationOptions, 1000)
animate_fn = n.bind('rv_dom_element_animate', I, [P, P, P, ctypes.POINTER(P)])
pause = n.bind('rv_dom_web_animation_pause', I, [P])
cancel = n.bind('rv_dom_web_animation_cancel', I, [P])
pending = n.bind('rv_dom_web_animation_get_pending', I, [P, ctypes.POINTER(I)])
release = n.bind('rv_event_target_release', None, [P])
collect = n.bind('rv_collect_garbage', None, [])


def pause_cancel_round():
    statuses, pending_pauses = set(), 0
    for _ in range(wa.GROWTH_ROUND):
        animation, flag = P(), I()
        statuses.add(animate_fn(element, keyframes, options, ctypes.byref(animation)))
        statuses.add(pause(animation))
        statuses.add(pending(animation, ctypes.byref(flag)))
        pending_pauses += bool(flag.value)
        statuses.add(cancel(animation))
        release(animation)
    n.bind('rv_run_loop_cycle', I, [I])(20)
    collect()
    return statuses, pending_pauses, wa.private_bytes()


rounds = [pause_cancel_round() for _ in range(3)]
samples = [r[2] for r in rounds]
pause_cancel = {'samples': samples, 'pendingPauses': [r[1] for r in rounds], 'statusesOk': all(r[0] == {OK} for r in rounds),
                'round': wa.GROWTH_ROUND, 'bound': wa.GROWTH_BOUND, 'flat': samples[2] - samples[1] < wa.GROWTH_BOUND}
page.guard('vm1 growth')
report = {'runtime': runtime, 'step2ArmedPauseCancel': step2, 'step4AnimateCancel': animate_cancel, 'step4PauseCancel': pause_cancel,
          'assertions': n.assertions}
print(json.dumps(report, indent=1))
