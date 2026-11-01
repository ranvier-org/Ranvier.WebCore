"""Regenerates the Chromium oracle N times into a scratch directory and compares each with the committed oracle, per
observer within each segment and without times. Usage: oracle_repeat.py <scratch dir> <count>"""
import json, os, subprocess, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[2]
scratch, count = Path(sys.argv[1]), int(sys.argv[2])
scratch.mkdir(parents=True, exist_ok=True)


def canonical(oracle):
    def entry(e):
        return {k: v for k, v in e.items() if k != 'time'}

    def delivery(d):
        es = d['entries']
        return {'o': d['o'], 'entries': {k: [entry(e) for e in v] for k, v in es.items()} if isinstance(es, dict) else [entry(e) for e in es]}
    return {key: {name: {'statuses': s['statuses'], 'segments': [sorted((delivery(d) for d in seg), key=lambda d: d['o']) for seg in s['segments']]}
                  for name, s in oracle[key].items()} for key in ['scenarios', 'qualified']}


expected = canonical(json.loads((repo / 'tests/fixtures/intersection-observation-oracle.json').read_text(encoding='utf-8')))
same = 0
for run in range(1, count + 1):
    out = scratch / ('oracle-' + str(run) + '.json')
    subprocess.run(['node', str(repo / 'tests/abi/intersection_observation_browser.mjs')], env=dict(os.environ, ORACLE_OUT=str(out)), check=True, capture_output=True)
    match = canonical(json.loads(out.read_text(encoding='utf-8'))) == expected
    same += match
    print('run ' + str(run) + ': ' + ('identical' if match else 'DIFFERENT'), flush=True)
print('ORACLE_REPEAT identical=' + str(same) + '/' + str(count))
sys.exit(0 if same == count else 1)
