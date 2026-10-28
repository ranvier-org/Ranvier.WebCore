# Windows UI Automation acceptance

The fixture uses the actual `RanvierWebCoreHost.dll` UIA bridge. It opens a visible native HWND and
starts a separate MTA COM client, which discovers that HWND through the operating system UI Automation
API. Queries and actions never bypass UIA. The fixture window is temporarily topmost without activation
so another desktop window cannot obscure the OS hit-test target.

The check covers tree/name/control-type mapping, hidden nodes, physical screen bounds and hit testing,
stable runtime IDs, Invoke and a real Name property event, editable Value, Toggle, range value and invalid
range rejection and numeric property events, disabled actions, UTF-16 text/range selection and geometry,
exact RangeFromChild, child enumeration, the innermost enclosing element, empty degenerate/offscreen geometry,
textarea clipping, protected values, DOM-node removal, unsolicited messages and retained providers after
teardown. The fixture and client have bounded lifetimes.

After packaging a Windows slim build, the native CI lane can run:

```sh
python -I tests/uia/check_exports.py OUT/runtimes/win-x64/native
python -I tests/uia/run.py --stage OUT --build-dir BUILD --build-only
python -I tests/uia/run.py --stage OUT --run-only --teardown explicit
python -I tests/uia/run.py --stage OUT --run-only --teardown host
python -I tests/uia/run.py --stage OUT --run-only --teardown window
python -I tests/uia/run.py --stage OUT --run-only --teardown sync
python -I tests/uia/run.py --stage OUT --run-only --teardown overflow
python -I tests/uia/run.py --stage OUT --build-dir BUILD --cache-probe --build-only
python -I tests/uia/run.py --stage OUT --cache-probe --run-only --teardown cache
```

`OUT` is the directory containing `manifest.json`, and `BUILD` is the WebCore CMake build directory.
The `overflow` case keeps a 640-CSS-pixel viewport, adds 2000-CSS-pixel document overflow, moves the HWND
and uses a device scale of 1.5; UIA bounds must match the known CSS rectangle in physical screen pixels.
The linker consumes `BUILD/lib/RanvierWebCoreHost.lib`; it is a build product, not a DLL copied into the
package. `--host-lib` can supply a different import library. `--native` can replace `--stage` with an
explicit native runtime directory. `--host-dll` overrides only the host DLL for local relinking while
retaining all other staged runtime files. All test outputs stay in this checkout's ignored `artifacts/uia`.

The runner uses `cl` from the environment when available. Otherwise it discovers an installed Visual
Studio C++ toolchain through `vswhere`; `--compiler-environment` can explicitly select `vcvars64.bat`.
The C++ workload and Windows SDK are prerequisites, as for building the Windows native host. The runner
does not install tools and needs neither RTK nor a screen reader installed on the CI machine.

Build and run are separate so callers can acquire and release their respective build/test leases.

The cache case is a separate white-box lifetime test. `CacheAcceptance.cpp` includes the identical provider
implementation in the fixture translation unit, while still using the real WebCore DLL and an independent
OS UIA client process. The client drives 128 DOM add/query/remove cycles and checks that the internal native
node/provider caches remain bounded. This gives ownership evidence without adding diagnostics to the public
ABI or production DLL. The five normal cases always exercise the provider implementation inside the DLL.
