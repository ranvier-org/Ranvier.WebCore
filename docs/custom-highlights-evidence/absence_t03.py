import json, subprocess, urllib.request, urllib.error, datetime
from pathlib import Path
rids = ['win-x64','win-arm64','linux-x64','linux-arm64','osx-arm64']
native = ['Ranvier.WebCore','Ranvier.WebCore.Native'] + [f'Ranvier.WebCore.Native.{r}' for r in rids] + [f'Ranvier.WebCore.Native.Gpu.{r}' for r in rids]
core = ['Ranvier.Dom','Ranvier.Dom.Traced','Fable.Ranvier.Dom','Fable.Ranvier.Dom.Traced']
views = ['Ranvier.View','Ranvier.View.Traced','Ranvier.View.Dom','Ranvier.View.Dom.Traced','Ranvier.View.Anime','Ranvier.View.Anime.Traced','Fable.Ranvier.Anime','Fable.Ranvier.Anime.Traced']
backend = ['Ranvier.View.WebCore','Ranvier.View.WebCore.Traced','Ranvier.View.WebCore.Sdl','Ranvier.View.WebCore.Sdl.Traced']
want = [(p,'0.1.0-preview.40') for p in native] + [(p,'0.1.0-alpha.43') for p in core] + [(p,'0.1.33') for p in views] + [(p,'0.1.0-alpha.33') for p in backend]
rows = []
for pkg, ver in want:
    url = f'https://api.nuget.org/v3-flatcontainer/{pkg.lower()}/index.json'
    try: versions = json.load(urllib.request.urlopen(url, timeout=30))['versions']
    except urllib.error.HTTPError as e: versions = [] if e.code == 404 else None
    rows.append({'package': pkg, 'version': ver, 'published': None if versions is None else ver in versions, 'source': url})
gh = []
marks = ['preview.40', 'alpha.43', '0.1.33', 'alpha.33']
for repo in ['ranvier-org/Ranvier.WebCore', 'ranvier-org/Ranvier', 'ranvier-org/Ranvier.View']:
    tags = subprocess.run(['gh','api',f'repos/{repo}/tags','--paginate','--jq','.[].name'], capture_output=True, text=True).stdout.split()
    prs = json.loads(subprocess.run(['gh','pr','list','--repo',repo,'--state','open','--json','number,title,headRefName,url'], capture_output=True, text=True).stdout)
    gh.append({'repository': repo, 'matchingTags': [t for t in tags if any(m in t for m in marks)], 'openPullRequests': prs})
abi = subprocess.run(['git','grep','-n','return 48;','--','host/RanvierWebCoreAbi.cpp'], cwd='C:/wk/native-highlight', capture_output=True, text=True).stdout
receipt = {'checkedAtUtc': datetime.datetime.now(datetime.UTC).isoformat(), 'purpose': 'T03 custom highlights Native40/ABI48, DOM alpha.43, Views 0.1.33, WebCore backend alpha.33 reservation', 'abi': 48, 'stackedOn': '6d636fb: T06 901ced5, B22 c78a71a, G03 cdf1a4e, G04 15e1bc9, I08 2a9cf7d final heads merged', 'abiNumberInUse': abi.strip(), 'packages': rows, 'github': gh}
Path('C:/wk/native-highlight/docs/custom-highlights-evidence/allocation-absence.json').write_text(json.dumps(receipt, indent=2))
print('not-absent:', [(r['package'], r['version'], r['published']) for r in rows if r['published'] is not False])
for g in gh: print(g['repository'], 'tags', g['matchingTags'], 'prs', [(p['number'], p['headRefName']) for p in g['openPullRequests']])
