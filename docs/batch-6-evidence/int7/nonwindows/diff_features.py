"""ENABLE_* values per build (an undefined macro is 0, as ENABLE() reads it) and the features each other build enables
that macOS leaves off. usage: diff_features.py"""
import json, re
from pathlib import Path
def load(name):
    values = {}
    for line in Path(name).read_text().splitlines():
        m = re.match(r'#define (ENABLE_[A-Z0-9_]+) (.*)$', line)
        if m:
            values[m.group(1)] = m.group(2).strip()
    return values
builds = {'windows-x64': load('win-features.txt'), 'linux-x64': load('linux-x64-features.txt'), 'osx-arm64': load('osx-arm64-features.txt')}
on = lambda b, k: builds[b].get(k, '0') not in ('0', '')
names = sorted(set().union(*builds.values()))
report = {'counts': {b: sum(on(b, k) for k in names) for b in builds},
          'onWindowsOffMac': [k for k in names if on('windows-x64', k) and not on('osx-arm64', k)],
          'onLinuxOffMac': [k for k in names if on('linux-x64', k) and not on('osx-arm64', k)],
          'onMacOffWindows': [k for k in names if on('osx-arm64', k) and not on('windows-x64', k)],
          'onMacOffLinux': [k for k in names if on('osx-arm64', k) and not on('linux-x64', k)]}
Path('feature-diff.json').write_text(json.dumps(report, indent=1) + '\n')
for k, v in report.items():
    print(k, v if k == 'counts' else f'{len(v)}: ' + ' '.join(x.removeprefix('ENABLE_') for x in v))
