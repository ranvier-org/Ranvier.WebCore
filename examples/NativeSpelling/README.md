# Native spelling suggestions

`WindowsSpellingProvider.h` is an optional application-side adapter to the Windows
SDK spelling service. It adds no renderer dependency, dictionary or browser menu.
The application supplies a language and a copied UTF-16 text snapshot. The result
reports `Available`, `Unavailable`, `Cancelled` or `Failed`; suggestions and their
ordering belong to the installed OS provider. An available result includes the
provider ID. Link the consuming application with `ole32.lib` and `uuid.lib`.

Call `RanvierNativeSpelling::checkWindowsSpelling(language, text, cancellation)`
outside a renderer callback. The cancellation flag is polled around synchronous
OS calls; it does not interrupt an OS call already in progress. Results own their
strings and contain UTF-16 offsets into the supplied snapshot. Requests are
bounded to 4,096 UTF-16 units, 64 issues and 16 suggestions per issue. `truncated`
reports a bounded result. Embedded NUL input is rejected rather than truncated.

The application owns the suggestion UI and request lifetime. Before applying a
result, verify that its request was not cancelled, the document is still current,
and the text snapshot still matches. Construct the corresponding engine range
and call the existing `rv_host_replace_range` on the host owner thread. This is
an `insertReplacementText` editor action: a `beforeinput` handler can cancel it,
the edit is undoable, and an active composition returns `RV_ERR_BUSY` without
committing or cancelling the composition. Discard stale ranges and results.

The executable test uses the installed `en-US` provider, displays an actual
suggestion in rendered native DOM, clicks it with native mouse input, and checks
the exact range, undo/redo, cancellation and stale-result behavior:

```powershell
python -I -X utf8 tests/spelling/windows.py --native-directory PATH_TO_NATIVE --output spelling-proof
```

It needs the Windows SDK and Visual Studio C++ tools. A missing OS language
provider is recorded explicitly as unavailable; no dictionary is installed. The
independent range/composition/lifetime regression always runs through
`tests/abi/spelling_replacement.py` in the normal native probe catalogue. The OS
consumer route currently runs on Windows x64; other platform provider adapters
are not supplied by this example.
