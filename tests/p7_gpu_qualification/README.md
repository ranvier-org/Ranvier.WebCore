# P7 Windows GPU qualification

This consumer-only control applies to the two `composited-translate` clipping cases at 1.5 and 2 times scale. It retains the original 54-case report, including those two failures, and requires all 12 strict mask controls and the other 52 comparisons to remain green. It does not change the baseline or authorize Linux publication.

The model derives geometry and a full-image RGBA envelope from the fixture and retained source telemetry. It separately bounds floating-point projection and interpolation, texture coordinate conversion, filtering and final UNORM conversion. The one-UNORM-quantum filter-output allowance is an explicit tested-profile policy inference, not a universal Direct3D guarantee. The consumer checks the actual ANGLE/D3D11 profile and independently exercises all 16 binary 2x2 patterns across 256x256 weight pairs on that device. Uniform-color samples remain exact. Ten targeted negative controls must fail.

The source inputs and model were reviewed against the private metadata-only reconstruction of the same producer source. That reconstruction matched all 54 original package captures locally; it is evidence for source geometry, not the published artifact. The workflow itself downloads and verifies all 26 payloads from the original P7 producer and captures fresh pixels from those exact bytes.
