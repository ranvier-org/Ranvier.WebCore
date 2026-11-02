# Content clipping paint gate

The twelve controls formed by the four reported #230 cases at scales 1, 1.5 and 2
must have exactly Chromium's complete solid-red content mask. This includes gaps
inside rows; matching a row's bounds and pixel count is insufficient. Border and
antialiasing pixels outside that mask are outside this strict parity claim.
This gate reads `rv_host_paint_rgba` on the GPU profile; the EGL and D3D probes
separately verify shared-frame transport.

All 54 controls separately compare complete RGBA pixels with Chromium. Apart from
the bounded half-coverage rule below, each
pixel's L1 error must be no greater than its error in the reviewed **current**
native baseline for that profile. Improvements at other pixels cannot compensate
for a regression. Reports retain every residual mask difference and every failing
pixel; no case is excluded because it already differs from Chromium. The current
Linux baseline has 21 residual mask differences; Windows has 18.

The Windows GPU `composited-translate` control at scale 1 also admits one measured
hardware quantization boundary: changed RGB channels may only exchange 127 and
128, with alpha fixed at 255 and every other component unchanged. Pixel coordinates
and the complete content mask remain unchanged. This rule never applies to the
twelve strict controls, another scale, another control or another platform.
[Direct3D 11.3 section 3.2.3.6](https://microsoft.github.io/DirectX-Specs/d3d/archive/D3D11_3_FunctionalSpec.htm)
permits 0.6 integer ULP for FLOAT-to-UNORM conversion; half coverage maps to 127.5
in RGBA8, within that bound of both 127 and 128.

The exact P4 package on NVIDIA RTX 5080 and CI's Microsoft Basic Render Driver
demonstrated this boundary. All 529 differing pixels were limited to those values;
the twelve strict masks and the other 53 controls remained unchanged. Reports keep
the raw 529 worse pixels, 528 previously exact losses and +1387 L1 delta, and label
qualified half-coverage pixels separately. Any other byte, alpha or shape change
continues to fail. The baseline images are unchanged.

Only the measured Linux x64 GPU and Windows x64 GPU profiles have baselines.
There is no ARM, macOS or Slim fallback. The tests check the package manifest,
host platform, architecture, ABI and compositing capability before using a profile.

Each profile freezes the source, runtime, package, cases, oracle and capture
hashes. The shared Chromium capture and each native capture contain lossless
compressed RGBA bytes with per-image hashes. The verification command only reads
these files.

Raw artifact hashes preserve their original byte provenance, including line
endings. Fixture verification uses the separate `canonical-json-v1` identity:
UTF-8 JSON with sorted keys, no ASCII escaping, and comma/colon separators without
extra whitespace. This identity is portable across LF and CRLF checkouts while
still rejecting changed JSON content. Per-image RGBA hashes remain byte-exact.

To propose a replacement baseline, use the profile's `regenerationCommand` with
the exact candidate stage and source commit, writing a **new** capture file. Run
the full paint capture and native catalogue, retain the old/new pointwise report
and residuals, and obtain independent review before replacing profile bytes or
provenance. Baselines are never regenerated as part of a test.

## Linux font precondition

The inline `fragment-clone` control names Arial. The reviewed Linux baseline resolves it to DejaVu Sans, SHA256 `ae7b7855e115a5966d8b1b3f80f254ccc117ec86f9965e202ee2940453837280`. The Linux clipping probe uses the process-local `linux-fonts.conf` alias and verifies the selected font bytes before creating the host. This does not change the application's fonts or any pixel policy.

The exact preview.4 Linux package from producer `41449896415` reproduced its CI failure under Liberation Sans. Consumer-only CI `41472188111` ran the unchanged gate twice against identical package bytes: the default font failed only `fragment-clone` at all three scales; the reviewed DejaVu Sans font matched all 54 stored RGBA captures byte for byte. Preserve both reports when assessing this environment correction.
