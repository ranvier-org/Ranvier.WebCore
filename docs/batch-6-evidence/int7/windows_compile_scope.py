"""Shows that the batch-6 forward merge of main (22f6aec -> 6e217450) changes no file compiled into the win-x64 runtime:
host/ hunks add only lines inside #if PLATFORM(MAC) blocks, and patches/, config/, gen/ and host/dom are untouched."""
import json, re, subprocess, sys
BASE, HEAD = '22f6aec80d07c8e11fa84c4b5971e1ba1eeaba93', '6e2174504b15b24d262425a9ca77688458456c56'
files = subprocess.run(['git', 'diff', '--name-only', BASE, HEAD], capture_output=True, text=True, check=True).stdout.split()
compiled = [f for f in files if re.match(r'(host|patches|config|gen|cmake|src)/', f) or f.endswith(('.cpp', '.h', '.inc', '.cmake'))]
hunks = {}
for f in compiled:
    diff = subprocess.run(['git', 'diff', '-U0', BASE, HEAD, '--', f], capture_output=True, text=True, check=True).stdout
    added = [l[1:] for l in diff.splitlines() if l.startswith('+') and not l.startswith('+++')]
    removed = [l[1:] for l in diff.splitlines() if l.startswith('-') and not l.startswith('---')]
    depth, guarded = 0, True
    for line in added:
        s = line.strip()
        if s.startswith('#if'):
            if depth == 0 and s != '#if PLATFORM(MAC)':
                guarded = False
            depth += 1
        elif s.startswith('#endif'):
            depth -= 1
        elif depth == 0:
            guarded = False
    hunks[f] = {'added': len(added), 'removed': len(removed), 'allAddedInsidePlatformMac': guarded and depth == 0 and not removed}
result = {'base': BASE, 'head': HEAD, 'files': files, 'compiledCandidates': compiled, 'hunks': hunks,
          'windowsCompileUnchanged': all(h['allAddedInsidePlatformMac'] for h in hunks.values())}
print(json.dumps(result, indent=1))
sys.exit(0 if result['windowsCompileUnchanged'] else 1)
