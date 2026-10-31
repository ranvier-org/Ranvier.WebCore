"""Regenerates the Chromium oracle N times into a scratch directory and compares each with the committed oracle,
exactly. Usage: oracle_repeat.py <scratch dir> <count>"""
import json, os, subprocess, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[2]
scratch, count = Path(sys.argv[1]), int(sys.argv[2])
scratch.mkdir(parents=True, exist_ok=True)
name = os.environ.get('ORACLE_NAME', 'web-animations')
expected = json.loads((repo / 'tests/fixtures' / (name + '-oracle.json')).read_text(encoding='utf-8'))
same = 0
for run in range(1, count + 1):
    out = scratch / ('oracle-' + str(run) + '.json')
    result = subprocess.run(['node', str(repo / 'tests/abi' / (name.replace('-', '_') + '_browser.mjs'))], env=dict(os.environ, ORACLE_OUT=str(out)), capture_output=True, text=True)
    if result.returncode:
        print('run ' + str(run) + ': FAILED ' + (result.stderr or result.stdout)[-600:].replace(chr(10), ' | '), flush=True)
        continue
    match = json.loads(out.read_text(encoding='utf-8')) == expected
    same += match
    print('run ' + str(run) + ': ' + ('identical' if match else 'DIFFERENT'), flush=True)
print('ORACLE_REPEAT identical=' + str(same) + '/' + str(count))
sys.exit(0 if same == count else 1)
