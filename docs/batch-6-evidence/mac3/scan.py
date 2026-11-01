"""Compiles every host translation unit with carbon-globals.h force-included, four at a time, one log each in logs/.
usage: scan.py [--overlay <dir>]"""
import concurrent.futures, subprocess, sys
from pathlib import Path
here = Path(__file__).resolve().parent
logs = here / 'logs'; logs.mkdir(exist_ok=True)
units = {
    'host/dom/RanvierDomGlue.cpp': '000-RanvierDomGlue.cpp.obj.rsp',
    'host/RanvierSvgViewGlue.cpp': '001-RanvierSvgViewGlue.cpp.obj.rsp',
    'host/RanvierResourceGlue.cpp': '002-RanvierResourceGlue.cpp.obj.rsp',
    'host/RanvierEventGlue.cpp': '003-RanvierEventGlue.cpp.obj.rsp',
    'host/RanvierViewportGlue.cpp': '004-RanvierViewportGlue.cpp.obj.rsp',
    'host/RanvierInspectGlue.cpp': '005-RanvierInspectGlue.cpp.obj.rsp',
    'host/RanvierCanvasGlue.cpp': '006-RanvierCanvasGlue.cpp.obj.rsp',
    'host/RanvierWakeLockGlue.cpp': '007-RanvierWakeLockGlue.cpp.obj.rsp',
    'host/RanvierNotificationGlue.cpp': '008-RanvierNotificationGlue.cpp.obj.rsp',
    'host/RanvierTransferGlue.cpp': '009-RanvierTransferGlue.cpp.obj.rsp',
    'host/RanvierPointerGlue.cpp': '010-RanvierPointerGlue.cpp.obj.rsp',
    'host/RanvierCanvasPixelsGlue.cpp': '011-RanvierCanvasPixelsGlue.cpp.obj.rsp',
    'host/RanvierCanvasExportGlue.cpp': '012-RanvierCanvasExportGlue.cpp.obj.rsp',
    'host/RanvierImageEncoding.cpp': 'RanvierImageEncoding.cpp.rsp',
    'host/RanvierWebCoreAbi.cpp': 'RanvierWebCoreAbi.cpp.rsp',
    'host/RanvierWebCoreDom.cpp': 'RanvierWebCoreDom.cpp.rsp',
}
extra = sys.argv[1:]
suffix = '-macoff' if '--overlay' in extra else ''


def run(item):
    source, rsp = item
    log = logs / f'{Path(source).stem}{suffix}.log'
    out = subprocess.run([sys.executable, str(here / 'compile.py'), str(log), source, rsp, '--carbon', *extra],
                         capture_output=True, text=True)
    return out.stdout.strip().splitlines()[-1]


with concurrent.futures.ThreadPoolExecutor(4) as pool:
    for line in pool.map(run, units.items()):
        print(line)
