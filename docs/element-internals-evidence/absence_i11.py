import json, subprocess, urllib.request, urllib.error, datetime
from pathlib import Path
rids = ['win-x64','win-arm64','linux-x64','linux-arm64','osx-arm64']
native = ['Ranvier.WebCore','Ranvier.WebCore.Native'] + [f'Ranvier.WebCore.Native.{r}' for r in rids] + [f'Ranvier.WebCore.Native.Gpu.{r}' for r in rids]
core = ['Ranvier.Dom','Ranvier.Dom.Traced','Fable.Ranvier.Dom','Fable.Ranvier.Dom.Traced']
views = ['Ranvier.View','Ranvier.View.Traced','Ranvier.View.Dom','Ranvier.View.Dom.Traced','Ranvier.View.Anime','Ranvier.View.Anime.Traced','Fable.Ranvier.Anime','Fable.Ranvier.Anime.Traced']
backend = ['Ranvier.View.WebCore','Ranvier.View.WebCore.Traced','Ranvier.View.WebCore.Sdl','Ranvier.View.WebCore.Sdl.Traced']
want = [(p,'0.1.0-preview.41') for p in native] + [(p,'0.1.0-alpha.44') for p in core] + [(p,'0.1.34') for p in views] + [(p,'0.1.0-alpha.34') for p in backend]
rows = []
for pkg, ver in want:
    url = f'https://api.nuget.org/v3-flatcontainer/{pkg.lower()}/index.json'
    versions = None
    for attempt in range(4):
        try:
            versions = json.load(urllib.request.urlopen(url, timeout=60))['versions']
            break
        except urllib.error.HTTPError as e:
            versions = [] if e.code == 404 else None
            break
        except (TimeoutError, urllib.error.URLError):
            continue
    rows.append({'package': pkg, 'version': ver, 'published': None if versions is None else ver in versions, 'source': url})
gh = []
marks = ['preview.37', 'alpha.40', '0.1.34', 'alpha.30']
for repo in ['ranvier-org/Ranvier.WebCore', 'ranvier-org/Ranvier', 'ranvier-org/Ranvier.View']:
    tags = subprocess.run(['gh','api',f'repos/{repo}/tags','--paginate','--jq','.[].name'], capture_output=True, text=True).stdout.split()
    prs = json.loads(subprocess.run(['gh','pr','list','--repo',repo,'--state','open','--json','number,title,headRefName,url'], capture_output=True, text=True).stdout)
    gh.append({'repository': repo, 'matchingTags': [t for t in tags if any(m in t for m in marks)], 'openPullRequests': prs})
import glob
local = {w: subprocess.run(['git','grep','-n','return 49;','--','host/RanvierWebCoreAbi.cpp'], cwd=w, capture_output=True, text=True).stdout.strip() for w in sorted(glob.glob('C:/wk/native-*')) if Path(w, 'host/RanvierWebCoreAbi.cpp').is_file()}
STACKED = '43a0074 (T03 828fb2b Native40/ABI48, I08 2a9cf7d Native39/ABI47, G04 15e1bc9 Native38/ABI46, G03 cdf1a4e Native37/ABI45; source patch 0039 64e0457)'
abi = subprocess.run(['git','grep','-n','return 49;','--','host/RanvierWebCoreAbi.cpp'], cwd='C:/wk/native-elinternals', capture_output=True, text=True).stdout
receipt = {'checkedAtUtc': datetime.datetime.now(datetime.UTC).isoformat(), 'purpose': 'I11 component accessibility Native41/ABI49, DOM alpha.44, Views 0.1.34, WebCore backend alpha.34 reservation (ABI46-48 belong to G04, I08, T03)', 'abi': 49, 'stackedOn': STACKED, 'abiNumberInUse': abi.strip(), 'localWorktreesReturning49': {k: v for k, v in local.items() if v}, 'packages': rows, 'github': gh}
Path('C:/wk/native-elinternals/docs/element-internals-evidence/allocation-absence.json').write_text(json.dumps(receipt, indent=2))
print('not-absent:', [(r['package'], r['version'], r['published']) for r in rows if r['published'] is not False])
for g in gh: print(g['repository'], 'tags', g['matchingTags'], 'prs', [(p['number'], p['headRefName']) for p in g['openPullRequests']])
