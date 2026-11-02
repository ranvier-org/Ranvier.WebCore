# Private macOS compositor experiment (#220)

This is source for a bounded, opt-in experiment. The Mac SDK compile, Metal execution, SDL presentation and Mac texture-input path have not been qualified. It adds no production transport enum, public ABI allocation or package cohort.

The experiment keeps Cocoa/CoreGraphics painting and uses WebCore's existing TextureMapper with ANGLE's Metal backend. A private GraphicsLayer factory chooses TextureMapper without replacing Cocoa's global factory. The narrow engine patch supplies its CoreGraphics image upload and required display exports. Other presets leave this path disabled.

Each private frame retains an IOSurface-backed GL target. The producer completes before handing it to SDL's Metal renderer; the consumer drains its reported Metal queue before releasing the frame. Frames can outlive resize, document replacement and their host. The display/context has process lifetime. External CALayer contents are unsupported by this experiment; this is not a general Mac media/canvas compositor.

The host integration preserves the current scale-aware compositor, dirty-only base painting and document transaction guards. Its private acquisition API uses the current CSS-to-physical floor convention and rejects stale hosts. Experimental counters report GPU acquisitions, host CPU frame transfers and base backing paints. CoreGraphics still rasterizes DOM content; this is not a claim of zero CPU layout or painting.

## Recipe

Use a dedicated macOS26 arm64 runner with the selected Xcode26 SDK, CMake, Ninja, Python, Perl, Ruby, gperf, .NET and SDL3/pkg-config available. Record their actual identities. Keep its source/build/output separate from release builds and protected warm sites.

Print the plan without fetching or creating its work directory:

```sh
rtk proxy python3 tests/gpu/mac/run.py --rid osx-arm64 --mac-gpu-spike --work "$HOME/rw-mac220" --jobs 4
```

The coordinator may execute the same plan in a scheduled Mac window:

```sh
rtk proxy python3 tests/gpu/mac/run.py --rid osx-arm64 --mac-gpu-spike --work "$HOME/rw-mac220" --jobs 4 --execute
```

The recipe requires a clean producer checkout, an explicit opt-in, private version `0.0.0-project2-mac220.1`, strict preparation and at most four build jobs. It refuses another platform or a work directory overlapping the producer. Existing evidence is never overwritten. It verifies the actual TextureMapper configuration, packages only into its private directory and never dispatches CI or publishes.

The native proof has a 180-second process limit. Command output and terminal status are retained even on timeout. A failure does not qualify the experiment: retain the first concrete SDK, link, EGL, Metal, pixel or lifecycle error before changing the implementation.

## Native proof

Three independent cycles use odd CSS viewport dimensions at explicit backing scales1,1.5,2. They require actual Metal renderer identity, premultiplied BGRA/orientation samples, clipped translucent content and CoreGraphics text. Paused transform/opacity animations are sampled through WebCore's animation API, with base-backing paint counts held constant and host CPU frame-transfer counts zero. Text/document replacement must produce changed pixels; retained old frames must remain stable. Resize and host destruction retain existing frame leases, and acquisition through the destroyed host must reject it. Wrong-thread acquisition/release and compositor-off controls remain strict.

The final SDL backbuffer readback is an oracle, not the presentation transport. Physical Retina behavior remains separate from explicit host device-scale tests. The current source preparation tests and Linux header checks do not prove that any Metal frame has run.

After the output path runs on Mac, the renderer-input step will bind an IOSurface-backed native Metal producer through a compatible TextureMapper attachment seam and qualify clipping, scrolling, transforms, opacity, stacking, synchronization and loss. The current Windows/Linux input implementations do not establish that Mac path.
