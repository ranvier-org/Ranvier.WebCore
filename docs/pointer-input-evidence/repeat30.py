"""Runs touch_input, pen_input and pointer_lock 30 times each on a frozen candidate runtime and writes repeat30.json:
every run's exit code and assertion count. usage: repeat30.py <runtime dir>"""
import json, re, subprocess, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[2]
runtime = sys.argv[1]
out = {}
for name in ['touch_input', 'pen_input', 'pointer_lock']:
    runs = []
    for index in range(30):
        result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi' / (name + '.py')), '--native-directory', runtime],
                                capture_output=True, text=True, timeout=300)
        match = re.search(r'PASS[^\n]*?(\d+) assertions', result.stdout)
        runs.append({'exit': result.returncode, 'assertions': int(match.group(1)) if match else None})
    counts = sorted({run['assertions'] for run in runs})
    out[name] = {'runs': 30, 'passed': sum(run['exit'] == 0 for run in runs), 'counts': counts}
    print(name, out[name], flush=True)
(Path(__file__).resolve().parent / 'repeat30.json').write_text(json.dumps({'runtime': runtime, 'probes': out}, indent=2) + '\n', encoding='utf-8')
assert all(item['passed'] == 30 and len(item['counts']) == 1 for item in out.values())
