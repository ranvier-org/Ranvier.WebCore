# Content clipping paint gate

The twelve controls formed by the four reported #230 cases at scales 1, 1.5 and 2
must have exactly Chromium's complete solid-red content mask. This includes gaps
inside rows; matching a row's bounds and pixel count is insufficient. Border and
antialiasing pixels outside that mask are outside this strict parity claim.
This gate reads `rv_host_paint_rgba` on the GPU profile; the EGL and D3D probes
separately verify shared-frame transport.

All 54 controls separately compare complete RGBA pixels with Chromium. Each
pixel's L1 error must be no greater than its error in the reviewed **current**
native baseline for that profile. Improvements at other pixels cannot compensate
for a regression. Reports retain every residual mask difference and every failing
pixel; no case is excluded because it already differs from Chromium. The current
Linux baseline has 21 residual mask differences; Windows has 18.

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
