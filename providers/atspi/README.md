# Ranvier.WebCore.Accessibility.Atspi

Optional Linux accessibility provider. It mirrors the host's `rv_ax_*` tree onto the AT-SPI bus through GDBus,
so Orca and other assistive technologies can read a page rendered through `libRanvierWebCoreHost.so`. The
consumer-facing model (tree, events, actions, text) is in `docs/ACCESSIBILITY.md`.

## Contents

- `libRanvierWebCoreAtspi.so`, `include/RanvierAtspi.h` and the host header `include/RanvierWebCoreAbi.h`.
- `NOTICE.md`, `THIRD-PARTY.md` and `licenses/LGPL-2.1.txt`. The provider embeds AT-SPI interface declarations
  generated from eight XML files of the pinned WebKit source; `THIRD-PARTY.md` records those inputs and the
  system dependencies.
- No WebCore, JavaScriptCore, GLib, GIO, GObject or libatspi binary. The application selects a matching
  `Ranvier.WebCore.Native` (GPU) or `Ranvier.WebCore.Native.Cpu` (Slim) aggregate separately. GLib, GIO and GObject come
  from the operating system; libatspi serves build headers and independent test clients only.

## Behaviour

- Exposes the Accessible, Application, Component, Action, Value and Text interfaces. Native object identity is
  preserved, and all native work runs on the host thread.
- Character offsets on the bus are converted from the ABI's UTF-16 offsets at the boundary.
- Forward ARIA relations come from `rv_ax_relations`; text attribute runs come from `rv_ax_text_style_run`.
  Opacity queries report unsupported.
- Child additions and removals emit identity-preserving `children-changed` events. Detached nodes are
  unregistered and their native references released. Replacing the document retires the old node paths and
  exposes the new root.
- The provider owns the host's accessibility callback while attached. Release it, and every retained `RvAxNode`,
  before `rv_host_destroy`. A failed attach retains neither the callback nor native nodes.
- A null bus address resolves `AT_SPI_BUS_ADDRESS`, then the session's `org.a11y.Bus.GetAddress`, within two
  seconds. A missing module or bus leaves window rendering usable and reports accessibility as unavailable.
- Screen coordinates report unsupported while the window position is unknown; window coordinates remain available.

## Host requirement

The provider admits a host whose `rv_abi_version()` is 63, 64 or 65 and whose `rv_abi_has("accessibility-text-style")`
is 1. `package.py` refuses any other host.

## Build and package

`.github/workflows/atspi-provider.yml` (manual dispatch) takes a reviewed native producer run, artifact and
host SHA256 and then:

1. stages the host with `tests/atspi/stage_native.py`;
2. builds `providers/atspi` with CMake against that host and installs the module under `$ORIGIN`;
3. runs the unit tests, `tests/abi/accessibility_text_styles.py` and the protocol fixture `tests/atspi/run.py`
   against an owned accessibility bus with an independent libatspi client;
4. packs the module with `providers/atspi/package.py` and checks it with `tests/atspi/consumer.py`, which restores
   the package from a local feed, publishes a .NET application and loads the provider's four exports.

`package.py` accepts only `linux-x64`, an installed provider whose runpath is exactly `$ORIGIN`, and private
identities (`Ranvier.Private.*`, version `0.0.0-private*` or `0.0.0-ci.<run>`). `provider-manifest.json` records
the caller-supplied source revision and cohort label as unverified claims, the host and provider hashes and the
payload hashes. Compare those hashes with the producer's receipts.

## Release package

Every Slim release run of `.github/workflows/build.yml` builds the public `Ranvier.WebCore.Accessibility.Atspi`
package at the release version:

1. The `atspi` job builds the provider on `linux-x64` and `linux-arm64` against the run's own Slim host and runs
   the same checks as `atspi-provider.yml` (the ABI is 64). It records each build in `build-receipt.json`.
2. The `atspi-package` job packs both builds with `providers/atspi/release.py`, then checks the SDK's RID
   selection with `tests/atspi/consumer.py --layout-only`.
3. `publish` pushes it with the rest of the release; a full Slim release requires it.

## Using the package

Reference the package beside a `Ranvier.WebCore.Native` package of the same version. The SDK copies
`runtimes/<rid>/native/libRanvierWebCoreAtspi.so` into the RID-specific publish output, next to
`libRanvierWebCoreHost.so`. Native consumers `#include "RanvierAtspi.h"`.

The package covers `linux-x64` and `linux-arm64`. Windows uses the UI Automation bridge in the host, and macOS has
no adapter.
