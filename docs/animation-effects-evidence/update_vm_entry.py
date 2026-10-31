"""Does rv_host_update attempt a refused VM entry on its own? Arms crashOnDisallowedVMEntry after the page load, then
runs updates in a child process per mode (plain page, page with a KeyframeEffect animation) and step (update armed, or
only the run loop armed after an unarmed update)."""
import ctypes, subprocess, sys
from pathlib import Path
sys.path.insert(0, sys.argv[2])
if len(sys.argv) > 3:
    from form_collections import Native, P, I, OK
    import web_animations as wa
    n = Native(sys.argv[1]); page = wa.Page(n, '<div id="a" style="width:9px;height:9px"></div>')
    if sys.argv[3] == 'animation':
        arena = wa.Arena(); r = P()
        n.ok('rv_dom_element_animate', [P, P, P, ctypes.POINTER(P)], page.element('a'), arena.keyframes([{'props': {'opacity': '0'}}, {'props': {'opacity': '1'}}]),
             arena.options(wa.AnimationOptions, wa.KeyframeAnimationOptions, {'duration': 1000}), ctypes.byref(r))
    if sys.argv[4] == 'cancel':
        # The update and run loop unarmed, then only Animation.cancel armed.
        n.call('rv_host_update', [P], page.host); n.call('rv_run_loop_cycle', [I], 0)
        print('armed', wa.arm_vm_entry_crash(sys.argv[1]), flush=True)
        if sys.argv[3] == 'animation':
            n.call('rv_dom_web_animation_cancel', [P], r.value)
        wa.arm_vm_entry_crash(sys.argv[1], False)
    elif sys.argv[4] == 'cycle':
        # The update unarmed, then only the run loop armed.
        for _ in range(3):
            n.call('rv_host_update', [P], page.host)
            print('armed', wa.arm_vm_entry_crash(sys.argv[1]), flush=True)
            n.call('rv_run_loop_cycle', [I], 0)
            wa.arm_vm_entry_crash(sys.argv[1], False)
    else:
        print('armed', wa.arm_vm_entry_crash(sys.argv[1]), flush=True)
        for _ in range(3):
            n.call('rv_host_update', [P], page.host); n.call('rv_run_loop_cycle', [I], 0)
    print('survived', flush=True)
    sys.exit(0)
for mode in ('plain', 'animation'):
    for step in ('update', 'cycle', 'cancel'):
        r = subprocess.run([sys.executable, '-I', __file__, sys.argv[1], sys.argv[2], mode, step], capture_output=True, text=True)
        print(mode, step, 'exit', r.returncode, r.stdout.strip().replace('\n', ' | '))
