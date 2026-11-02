"""Download the pinned P7 Windows producer and qualification artifacts."""
import argparse
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--work', type=Path, required=True)
args = parser.parse_args()
work = args.work.resolve()
work.mkdir(parents=True, exist_ok=False)
for run, name, directory in [
    (41498246594, 'package-win-x64-gpu', 'package'),
    (41498246594, 'manifest-win-x64-gpu', 'manifest'),
    (41498246594, 'probe-logs-win-x64-gpu', 'probe'),
    (41498246594, 'clipping-report-win-x64-gpu', 'original'),
    (41541720378, 'p7-windows-qualification', 'qualification'),
]:
    subprocess.run(['gh', 'run', 'download', str(run), '--repo', 'ranvier-org/Ranvier.WebCore',
                    '--name', name, '--dir', str(work / directory)], check=True, timeout=180)
subprocess.run([sys.executable, '-I', str(Path(__file__).with_name('recover_preview7_gpu.py')),
    '--package', str(work / 'package/Ranvier.WebCore.Native.Gpu.win-x64.0.1.1-preview.7.nupkg'),
    '--manifest', str(work / 'manifest/manifest.json'), '--producer-summary', str(work / 'probe/summary.txt'),
    '--original-report', str(work / 'original/background-content-clipping-regression.json'),
    '--evidence', str(work / 'qualification'), '--qualification', '41541720378',
    '--receipt', str(work / 'verification.json'), '--export', str(work / 'export')], check=True, timeout=90)
