"""Run all private composition fault modes, preserving each process result."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native-directory', required=True)
parser.add_argument('--reports', required=True, type=Path)
args = parser.parse_args()
args.reports.mkdir(parents=True, exist_ok=True)
modes = [stage + '-' + action for stage in ('first', 'middle', 'final')
         for action in ('stop', 'value', 'replace', 'destroy', 'compose')]
modes += [stage + '-mismatch' for stage in ('restored', 'deleted', 'rebuilt', 'missing')]
modes += ['deleted-stop', 'rebuilt-stop']
results = []
for mode in modes:
    command = [sys.executable, '-I', str(Path(__file__).with_name('phase_faults.py')),
               '--native-directory', args.native_directory, '--mode', mode,
               '--report', str(args.reports / (mode + '.json'))]
    try:
        child = subprocess.run(command, capture_output=True, timeout=30)
        code = child.returncode
        (args.reports / (mode + '.log')).write_bytes(child.stdout + child.stderr)
    except subprocess.TimeoutExpired as error:
        code = -999
        (args.reports / (mode + '.log')).write_bytes((error.stdout or b'') + (error.stderr or b'') + b'\nTIMEOUT\n')
    print(mode, code, flush=True)
    results.append({'mode': mode, 'exit': code})
(args.reports / 'summary.json').write_text(json.dumps(results, indent=2))
raise SystemExit(1 if any(row['exit'] for row in results) else 0)
