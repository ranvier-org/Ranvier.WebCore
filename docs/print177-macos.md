# CoreGraphics PDF implementation

Base: Native `6f10bea17d7a1f22e5e97d472819c055fba3ef06`; the existing C ABI and ownership contract remain unchanged.

The Mac backend uses the pinned `PrintContext` pagination and `GraphicsContextCG` with the system CoreGraphics PDF writer. A bounded `CGDataConsumer` owns the output. The common print guard restores screen layout and scroll on completion, cancellation and output failure. Existing deferred resource completion and host transaction guards own teardown.

`raster_dpi=0` selects the backend default: Skia 144, CoreGraphics 72. CoreGraphics accepts explicit 72 only; other explicit values fail before layout. The writer does not expose an equivalent of Skia's raster-DPI metadata. Null C options select Letter 612×792 points, 36-point margins, 16 pages and 8 MiB. Existing managed paper geometry remains unchanged and its default DPI becomes zero.

Implementation checkpoints:

1. Compile shared option-policy controls; retain the missing-header RED. Add bounded CG output and reuse pagination, cancellation and lifetime paths.
2. Extend actual ABI probes with null/default/explicit72 success, explicit unsupported DPI before cancellation polling, and the existing page/text/image/vector, budget, repeat and teardown controls.
3. Build one `osx-arm64` Slim package on a disposable macOS26 CI runner with existing cache restore, then run actual PDF probes and inspect physical page/ruler coordinates. Compile success alone does not qualify output.
4. Independently review immutable source/package/proof, retain compact artifacts, and remove owned temporary outputs/processes after reader release.

Windows/Linux historical proofs remain tied to their original bytes. The new backend and altered default policy require new runtime qualification. OS dialogs/spooling and production settings beyond this explicit profile are outside this change.
