"""Runs one tests/abi probe N times against a runtime directory and records each run's exit code and PASS line.
usage: repeat_probe.py <probe name> <runtime dir> <count> <output json>"""
import json, subprocess, sys
from pathlib import Path
repo = Path(__file__).resolve().parents[2]
name, runtime, count, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
runs = []
for index in range(count):
    result = subprocess.run([sys.executable, '-I', '-X', 'utf8', str(repo / 'tests/abi' / (name + '.py')), '--native-directory', runtime],
                            capture_output=True, text=True, encoding='utf-8', timeout=600)
    line = next((l for l in result.stdout.splitlines() if l.startswith('PASS')), None)
    runs.append({'run': index + 1, 'exitCode': result.returncode, 'pass': line})
    if result.returncode:
        print(result.stdout[-2000:], result.stderr[-2000:])
report = {'probe': name, 'runtime': runtime, 'count': count, 'allPassed': all(r['exitCode'] == 0 for r in runs),
          'distinctPassLines': sorted({r['pass'] for r in runs if r['pass']}), 'runs': runs}
out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(name, 'runs', count, 'all passed' if report['allPassed'] else 'FAILED', report['distinctPassLines'])
sys.exit(0 if report['allPassed'] and len(report['distinctPassLines']) == 1 else 1)
