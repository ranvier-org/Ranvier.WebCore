import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('debug_log', type=Path)
parser.add_argument('--label', required=True)
args = parser.parse_args()
lines = args.debug_log.read_text(encoding='utf8', errors='replace').splitlines()
source = ("[entry: '" + args.label + "']", "[text: '" + args.label + "']")
events = [(i, line) for i, line in enumerate(lines) if 'EVENT MANAGER: object:' in line and any(name in line for name in source)]
focus = [i for i, line in events if 'object:state-changed:focused' in line and '(1, 0,' in line]
caret = [i for i, line in events if 'object:text-caret-moved' in line]
speech = [i for i, line in enumerate(lines) if 'SPEECH OUTPUT:' in line and args.label in line]
report = {'label': args.label, 'focused': focus, 'caret': caret, 'spoken': speech,
          'focusBeforeCaret': bool(focus and (not caret or focus[0] < caret[0])), 'labelSpoken': bool(speech)}
print(json.dumps(report))
if not report['focusBeforeCaret'] or not report['labelSpoken']:
    raise SystemExit(1)
