# Immutable d31 Mac recovery implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` for native execution in this lane; Root assigned implementation and QA reviews the concrete unarmed source.

**Goal:** Recover a warm d31 Mac Slim or GPU producer without changing its product checkout or publishing packages.

**Architecture:** Product F stays at the original workspace root. Builder H lives in a separate temporary Git checkout. F supplies cache keys, product compilation, packaging and native tests; H supplies the corrected helper builder and a recovery receipt binding both identities.

**Tech stack:** Python, CMake/Ninja and GitHub Actions on macOS26 ARM64.

**Spec:** Root's immutable-d31 recovery assignment and retained prewarm failure 41720640443.

**Files:** `scripts/mac_preview12_recovery.py` owns admission and bounded phases; `.github/workflows/macos-preview12-recovery.yml` owns cache transport and artifact ordering; `tests/test_mac_preview12_recovery.py` owns negative controls.

- [ ] Test and implement clean F/H separation, unique matching Host compile entry and rejection of unexpected engine compilation.
- [ ] Implement canonical cache normalisation, environment-enabled compile database generation, warm build and exact F package admission.
- [ ] Upload package and manifest before helpers; run corrected H helpers against F sources and independently collect unchanged F native gates. Retain SDK and helper evidence on failure.
- [ ] Keep the workflow literally disabled, verify focused tests and source scope, then freeze for Root/QA review. Activation is a separate reviewed operation after the original tag job boundary is clear.

Review focuses on dirty/wrong product source, builder paths entering product flags, duplicate or stale compile commands, cold engine rebuilds, package retention before helper failure, and cleanup of owned process groups. Existing d31 tags and product files remain immutable.
