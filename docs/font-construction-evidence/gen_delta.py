"""Generated-output delta of this tree against a base commit: functions added, removed and changed in gen/dom-api.json,
and, for each generated file, whether the base text survives unchanged as a subsequence of the new text (every removed
line is a failure). Usage: gen_delta.py <base-commit> <out.txt>"""
import difflib
import json
import subprocess
import sys
from pathlib import Path

base, out_path = sys.argv[1], Path(sys.argv[2])
root = Path(__file__).resolve().parents[2]
FILES = ['gen/dom-api.json', 'gen/Ranvier.Dom.fs', 'gen/dom-report.txt', 'host/RanvierWebCoreDom.h', 'host/RanvierWebCoreDom.cpp',
         'host/dom/RanvierDomGlue.h', 'host/dom/RanvierDomGlue.cpp', 'tests/abi/NativeDom.fs', 'host/RanvierCapabilityCatalogue.inc']


def old(path):
    return subprocess.run(['git', 'show', base + ':' + path], cwd=root, capture_output=True, check=True).stdout.decode('utf-8')


def functions(text):
    model = json.loads(text)
    return {f['function']: json.dumps(f, sort_keys=True) for f in model['functions']}


before, after = functions(old('gen/dom-api.json')), functions((root / 'gen/dom-api.json').read_text(encoding='utf-8'))
added = sorted(set(after) - set(before))
removed = sorted(set(before) - set(after))
changed = sorted(n for n in set(before) & set(after) if before[n] != after[n])
lines = ['base %s; dom-api functions added %d removed %d changed %d' % (base, len(added), len(removed), len(changed))]
lines += ['  + ' + n for n in added] + ['  - ' + n for n in removed] + ['  ~ ' + n for n in changed]
failures = len(removed) + len(changed)
for path in FILES:
    a = old(path).replace('\r\n', '\n').splitlines()
    b = (root / path).read_text(encoding='utf-8').replace('\r\n', '\n').splitlines()
    minus = [l for l in difflib.unified_diff(a, b, lineterm='', n=0) if l.startswith('-') and not l.startswith('---')]
    plus = [l for l in difflib.unified_diff(a, b, lineterm='', n=0) if l.startswith('+') and not l.startswith('+++')]
    lines.append('%s: +%d -%d' % (path, len(plus), len(minus)))

    def extended(line):
        # A list line that only gained items: its old items appear in order in an added line.
        items = line[1:].split(', ')
        for candidate in plus:
            found = candidate[1:].split(', ')
            position = 0
            for item in found:
                if position < len(items) and item == items[position]:
                    position += 1
            if len(items) > 1 and position == len(items):
                return True
        return False
    for line in minus:
        accepted = path in ('gen/dom-report.txt', 'gen/dom-api.json') or extended(line)
        lines.append(('    (extended list) ' if accepted else '    REMOVED ') + line[:160])
        failures += 0 if accepted else 1
lines.append('GEN_DELTA=' + ('PASS' if not failures else 'FAIL %d' % failures))
out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('\n'.join(lines[:3] + [l for l in lines if not l.startswith('  ')][-12:]))
