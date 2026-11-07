# Ranvier.WebCore.Native.Cpu

The CPU-only native WebCore host, the Slim flavor: presentation-focused WebKit without the GPU code, painting every
frame on the CPU (`rv_host_paint_rgba`). Reference it alongside the same version of `Ranvier.WebCore`, in place of
`Ranvier.WebCore.Native`, for the smallest package or for pixels that do not depend on a GPU, such as screenshot
tests that compare frames across machines.

| Runtime | Package restored |
|---|---|
| `win-x64`, `win-arm64`, `linux-x64`, `linux-arm64`, `osx-arm64` | `Ranvier.WebCore.Native.Cpu.<rid>` |

All five packages share one version, ABI, WebKit pin and source commit. An application references either this
package or `Ranvier.WebCore.Native`, never both: the two would put two `RanvierWebCoreHost` binaries in
`runtimes/<rid>/native/`.
