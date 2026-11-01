Non-Windows compile scan of the batch-6 head (int7).
- Scratch run 41267289491 (codex/int7-nonwin = e2a83cc + ninja -k 0): macOS failed only host/dom/RanvierDomGlue.cpp
  (Touch/TouchList unguarded; ENABLE_TOUCH_EVENTS is off on macOS). Linux: wsl1 built e2a83cc in WSL with -k 0, 0 errors.
- Feature macros: scratch run 41271493084 dumped #define ENABLE_/USE_/HAVE_ (clang -dM -E of cmakeconfig.h + wtf/Platform.h
  with each build's RanvierDomGlue.cpp flags) for linux-x64 and osx-arm64; windows-x64 by the same procedure locally
  (C:/wk/pointer-build). diff_features.py -> feature-diff.json.
- Stand-in: compile.py builds RanvierDomGlue.cpp with the batch6-candidate-2 flags (no PCH, -ferror-limit=0) and a
  cmakeconfig.h forcing every Windows-on/macOS-off feature to 0 (standin-cmakeconfig-tail.txt), except THREADING_GENERIC,
  the threading model (macOS selects THREADING_LIBDISPATCH, which needs dispatch.h). e2a83cc glue: 20 errors
  (macoff-old.log, the macOS set); 0c69f8b glue: 0 errors (macoff-new.log).
