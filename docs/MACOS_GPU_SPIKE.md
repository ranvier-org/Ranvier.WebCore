# Private macOS compositor experiment (#220)

The compositor uses Cocoa/CoreGraphics painting with WebCore's TextureMapper and ANGLE's Metal backend. The ordinary osx-arm64 GPU profile enables this path; the private experiment recipe remains available for isolated qualification. The seven Host objects have compiled on the actual Mac SDK. Full compositor execution, SDL presentation, texture input and official GPU package acceptance remain pending.

ABI64 appends `rv_host_acquire_iosurface_frame` and `rv_host_bind_iosurface`, preserving the existing347 signatures and their order. Acquired frames use `rv_gpu_frame_info` and `rv_gpu_frame_release`; the borrowed IOSurfaceRef contains premultiplied BGRA8 bytes. The input endpoint retains the producer's surface through replacement/unbind or target/document/host teardown. `tests/gpu/mac/qualify_package.py` compiles both native fixtures against these public endpoints and executes them on the extracted GPU package. Its receipts bind the unchanged native payload to the output/input and software-rejection controls.

A host-specific GraphicsLayer factory chooses TextureMapper without replacing Cocoa's global factory. The engine patches supply CoreGraphics image upload, required display exports and typed ANGLE GL dispatch. Other platform presets preserve their current transports; the Mac Slim preset keeps this path disabled.

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

The renderer-input fixture binds an IOSurface-backed native Metal producer through the TextureMapper attachment seam and checks clipping, scrolling, transforms, opacity, stacking, synchronization and loss. Its Mac runtime qualification remains separate from the existing Windows/Linux input proof.
