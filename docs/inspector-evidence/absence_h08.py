"""Fresh absence check of the H08 reservation: Native42/ABI50 (preview.42), DOM alpha.45, Views 0.1.35, backend alpha.35.
Writes docs/inspector-evidence/allocation-absence.json. Usage: absence_h08.py <stacked-on note>"""
import datetime, json, subprocess, sys, urllib.error, urllib.request
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
rids = ['win-x64', 'win-arm64', 'linux-x64', 'linux-arm64', 'osx-arm64']
native = ['Ranvier.WebCore', 'Ranvier.WebCore.Native'] + [f'Ranvier.WebCore.Native.{r}' for r in rids] + [f'Ranvier.WebCore.Native.Gpu.{r}' for r in rids]
core = ['Ranvier.Dom', 'Ranvier.Dom.Traced', 'Fable.Ranvier.Dom', 'Fable.Ranvier.Dom.Traced']
views = ['Ranvier.View', 'Ranvier.View.Traced', 'Ranvier.View.Dom', 'Ranvier.View.Dom.Traced', 'Ranvier.View.Anime', 'Ranvier.View.Anime.Traced',
         'Fable.Ranvier.Anime', 'Fable.Ranvier.Anime.Traced']
backend = ['Ranvier.View.WebCore', 'Ranvier.View.WebCore.Traced', 'Ranvier.View.WebCore.Sdl', 'Ranvier.View.WebCore.Sdl.Traced']
want = ([(p, '0.1.0-preview.42') for p in native] + [(p, '0.1.0-alpha.45') for p in core] + [(p, '0.1.35') for p in views]
        + [(p, '0.1.0-alpha.35') for p in backend])
rows = []
for package, version in want:
    url = f'https://api.nuget.org/v3-flatcontainer/{package.lower()}/index.json'
    try:
        versions = json.load(urllib.request.urlopen(url, timeout=30))['versions']
    except urllib.error.HTTPError as error:
        versions = [] if error.code == 404 else None
    rows.append({'package': package, 'version': version, 'published': None if versions is None else version in versions, 'source': url})
marks = ['preview.42', 'alpha.45', '0.1.35', 'alpha.35']
github = []
for name in ['ranvier-org/Ranvier.WebCore', 'ranvier-org/Ranvier', 'ranvier-org/Ranvier.View']:
    tags = subprocess.run(['gh', 'api', f'repos/{name}/tags', '--paginate', '--jq', '.[].name'], capture_output=True, text=True).stdout.split()
    prs = json.loads(subprocess.run(['gh', 'pr', 'list', '--repo', name, '--state', 'open', '--json', 'number,title,headRefName,url'],
                                    capture_output=True, text=True).stdout or '[]')
    github.append({'repository': name, 'matchingTags': [t for t in tags if any(m in t for m in marks)], 'openPullRequests': prs})
abi = subprocess.run(['git', 'grep', '-n', 'int32_t rv_abi_version(void)', '--', 'host/RanvierWebCoreAbi.cpp'], cwd=repo,
                     capture_output=True, text=True).stdout.strip()
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=repo, capture_output=True, text=True).stdout.strip()
receipt = {'checkedAtUtc': datetime.datetime.now(datetime.UTC).isoformat(),
           'purpose': 'H08 inspector diagnostics Native42/ABI50 (preview.42), DOM alpha.45, Views 0.1.35, WebCore backend alpha.35 reservation',
           'abi': 50, 'nativeHead': head, 'stackedOn': sys.argv[1] if len(sys.argv) > 1 else '', 'abiNumberInUse': abi,
           'packages': rows, 'github': github}
(repo / 'docs/inspector-evidence/allocation-absence.json').write_text(json.dumps(receipt, indent=2) + '\n')
print('not-absent:', [(r['package'], r['version'], r['published']) for r in rows if r['published'] is not False])
for entry in github:
    print(entry['repository'], 'tags', entry['matchingTags'], 'prs', [(p['number'], p['headRefName']) for p in entry['openPullRequests']])
