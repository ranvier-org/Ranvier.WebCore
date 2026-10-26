# Moving to a new WebKit commit

1. **Check the series.** With a WebKit clone that has the new commit:

   ```
   python -I scripts/patches.py check <commit> --source <webkit>
   ```

   Each patch reports `applies` or `FAILS` with git's reason. Patches are checked in order, each over the
   ones before it.

2. **Fix a failing patch** in a tree at the new commit: apply the series up to it by hand, make the change,
   then set `webkit.commit` in `pins.json` to the new commit and re-export:

   ```
   python -I scripts/patches.py export <name> <path>... --source <webkit>
   ```

   Most failures are CMake hunks whose context moved. A stub `.cpp` fails at link time instead, on an
   undefined or duplicate member, when upstream changes a class the stub defines members of.
   - 0001: re-run `scripts/angle_stub.py --source <webkit> --clang <clang-cl>` when the link fails on an
     undefined `gl*` or `egl*` symbol, then re-export.
   - 0008: the hooks and canvas processors are generated from upstream headers at build time and follow
     them without a patch change.
   - 0005 and 0007: a new IDL file under a removed directory is left out by directory; a new reference to a
     removed interface from remaining code needs a stand-in IDL file or a stub member.

3. **Build both flavors.** `lean` shows the patches leave a default build unchanged; `slim` is the
   shipped one.

   ```
   python -I scripts/build.py all --flavor lean
   python -I scripts/build.py all --flavor slim
   ```

4. **Check the host.** Run Ranvier's F# driver and conformance run against the packaged DLLs (Ranvier's
   `evidence/webcore-host`), then bump `package.version` in `pins.json`.

Also re-pin when WebKit moves its dependencies: vcpkg's port versions come from WebKit's own
`vcpkg-configuration.json`, so a new ICU version changes `pins.json`'s `icu` entry and the `icudt77`
names in `scripts/icu_data.py`.
