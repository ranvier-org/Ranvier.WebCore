"""Complete the documented rendering update after changing compositing mode."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('static_text_control',Path(__file__).with_name('static_text220.py'))
control=importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
control.BEFORE='require(rv_host_set_accelerated_compositing(host.get(), RV_COMPOSITING_ALWAYS) == RV_OK, "force real compositor");'
control.AFTER=control.BEFORE+'\n    require(rv_host_update(host.get()) == RV_OK, "update enabled compositor before first acquisition");'
control.LABEL='post-mode-rendering-update'
control.SCOPE='One required rendering update after the mode change, before first acquisition; no frames discarded or extra paints.'

if __name__=='__main__':
    control.replay.run_cases=control.experiment
    raise SystemExit(control.replay.main())
