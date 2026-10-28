"""Run the compiled realm fixture in a private headless Chromium profile."""

import argparse
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--browser', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True, help='Fickl output directory containing RealmBrowser.js.')
args = parser.parse_args()
output = args.output.resolve()
assert (output / 'RealmBrowser.js').is_file(), 'Compile RealmBrowser.fsproj first'
page = output / 'realm-fixture.html'
page.write_text('<!doctype html><html><body><script type="module" src="RealmBrowser.js"></script></body></html>')
with tempfile.TemporaryDirectory(prefix='ranvier-realm-browser-') as profile:
    result = subprocess.run([str(args.browser.resolve()), '--headless=new', '--disable-gpu',
                             '--no-first-run', '--no-default-browser-check', '--allow-file-access-from-files',
                             '--user-data-dir=' + profile, '--virtual-time-budget=5000', '--dump-dom', page.as_uri()],
                            capture_output=True, text=True, timeout=45)
    (output / 'realm-browser-result.html').write_text(result.stdout, encoding='utf-8')
    (output / 'realm-browser-stderr.log').write_text(result.stderr, encoding='utf-8')
    assert result.returncode == 0, result.stderr[-4000:]
    assert 'data-result="REAL_BROWSER_REALMS_PASS"' in result.stdout, result.stdout[-4000:] + result.stderr[-2000:]
print('REAL_BROWSER_REALMS PASS: iframe HTML/SVG/RadioNodeList and detached-document elements preserve identity')
