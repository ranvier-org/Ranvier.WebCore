# Ranvier.WebCore.Native.Gpu

The GPU flavor of the native WebCore host: Slim plus accelerated compositing, WebGL and native GPU frames.
Reference it alongside the same version of `Ranvier.WebCore`, in place of `Ranvier.WebCore.Native`.

| Runtime | Package restored |
|---|---|
| `win-x64`, `linux-x64`, `linux-arm64`, `osx-arm64` | `Ranvier.WebCore.Native.Gpu.<rid>` |
| `win-arm64` | `Ranvier.WebCore.Native.win-arm64` (Slim) |

All five packages share one version, ABI, WebKit pin and source commit. An application references either this
package or `Ranvier.WebCore.Native`, never both: the two would put two `RanvierWebCoreHost` binaries in
`runtimes/<rid>/native/`.
