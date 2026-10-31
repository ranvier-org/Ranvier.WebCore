import json, subprocess, urllib.request, urllib.error, datetime
from pathlib import Path
rids = ['win-x64','win-arm64','linux-x64','linux-arm64','osx-arm64']
native = ['Ranvier.WebCore','Ranvier.WebCore.Native'] + [f'Ranvier.WebCore.Native.{r}' for r in rids] + [f'Ranvier.WebCore.Native.Gpu.{r}' for r in rids]
core = ['Ranvier.Dom','Ranvier.Dom.Traced','Fable.Ranvier.Dom','Fable.Ranvier.Dom.Traced']
views = ['Ranvier.View','Ranvier.View.Traced','Ranvier.View.Dom','Ranvier.View.Dom.Traced','Ranvier.View.Anime','Ranvier.View.Anime.Traced','Fable.Ranvier.Anime','Fable.Ranvier.Anime.Traced']
backend = ['Ranvier.View.WebCore','Ranvier.View.WebCore.Traced','Ranvier.View.WebCore.Sdl','Ranvier.View.WebCore.Sdl.Traced']
want = [(p,'0.1.0-preview.34') for p in native] + [(p,'0.1.0-alpha.37') for p in core] + [(p,'0.1.27') for p in views] + [(p,'0.1.0-alpha.27') for p in backend]
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
marks = ['preview.34', 'alpha.37', '0.1.27', 'alpha.27']
for repo in ['ranvier-org/Ranvier.WebCore', 'ranvier-org/Ranvier', 'ranvier-org/Ranvier.View']:
    tags = subprocess.run(['gh','api',f'repos/{repo}/tags','--paginate','--jq','.[].name'], capture_output=True, text=True).stdout.split()
    prs = json.loads(subprocess.run(['gh','pr','list','--repo',repo,'--state','open','--json','number,title,headRefName,url'], capture_output=True, text=True).stdout)
    gh.append({'repository': repo, 'matchingTags': [t for t in tags if any(m in t for m in marks)], 'openPullRequests': prs})
abi = subprocess.run(['git','grep','-n','return 42;','--','host/RanvierWebCoreAbi.cpp'], cwd='C:/wk/native-formsubmit', capture_output=True, text=True).stdout
receipt = {'checkedAtUtc': datetime.datetime.now(datetime.UTC).isoformat(), 'purpose': 'D14 form submission Native34/ABI42, DOM alpha.37, Views 0.1.27, WebCore backend alpha.27 reservation', 'abi': 42, 'stackedOn': '7c92f3c (Native33/ABI41 H13 final 3c7e8d4, H11 6610b57, G09 fb87eb0 and a215ef9, source patch 0037 a005332)', 'abiNumberInUse': abi.strip(), 'packages': rows, 'github': gh}
Path('C:/wk/native-formsubmit/docs/form-submission-evidence/allocation-absence.json').write_text(json.dumps(receipt, indent=2))
print('not-absent:', [(r['package'], r['version'], r['published']) for r in rows if r['published'] is not False])
for g in gh: print(g['repository'], 'tags', g['matchingTags'], 'prs', [(p['number'], p['headRefName']) for p in g['openPullRequests']])
