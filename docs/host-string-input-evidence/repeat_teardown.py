"""Runs the teardown driver N times with RANVIER_TEARDOWN_ONLY set to one probe's name, and records each run's records
and whether every document and target was collected.
usage: repeat_teardown.py <driver dir> <filter> <count> <output json>"""
import json
import os
import subprocess
import sys
from pathlib import Path

driver, name, count, out = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
runs = []
for index in range(count):
    folder = out.parent / ('teardown-repeat-' + str(index + 1))
    folder.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, RANVIER_WEBKIT_SOURCE='C:/wk/src', RANVIER_WEBCORE_OUT=str(folder), RANVIER_WEBCORE_PROBE='teardown',
               RANVIER_TEARDOWN_ONLY=name)
    result = subprocess.run(['dotnet', str(driver / 'RanvierWebCoreAbi.Driver.dll')], env=env, capture_output=True, timeout=900)
    records = json.loads((folder / 'teardown-probes.json').read_text()) if result.returncode == 0 else []
    runs.append({'run': index + 1, 'exitCode': result.returncode, 'records': len(records),
                 'allCollected': bool(records) and all(r['documentRefsAfterCollection'] == -1 and r['targetRefsAfterCollection'] == -1
                                                       for r in records)})
report = {'filter': 'RANVIER_TEARDOWN_ONLY=' + name, 'driver': str(driver), 'runs': runs,
          'allPassed': all(r['exitCode'] == 0 and r['allCollected'] for r in runs),
          'distinctRecordCounts': sorted({r['records'] for r in runs})}
out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('teardown', name, 'runs', count, 'all passed' if report['allPassed'] else 'FAILED', report['distinctRecordCounts'])
sys.exit(0 if report['allPassed'] and len(report['distinctRecordCounts']) == 1 else 1)
