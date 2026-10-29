# C12 custom-property registration

Expose the pinned engine's `CSS.registerProperty` through a checked Document receiver, and export the four readonly CSSPropertyRule descriptors. Preserve existing ABI IDs and dictionary layouts; C12 allocates ABI22 and preview.14 after the preview.13 context/counter batch.

The new DOMCSSCustomPropertyDescriptor dictionary uses RvDomUtf8StringInput (present, data, byte length) for strings. Required fields remain size checked. A present empty string differs from omission; UTF-8 spans preserve embedded NUL and reject invalid lengths, pointers or encoding. Other dictionaries retain their original null-terminated string fields. Registration has its own capability, separate from CSS supports.

The shared managed API uses an explicit CustomPropertyInitialValue union (Omitted or Value of string), because Fable 5.13 erases Some null even with nullable-string annotations. Value null converts to WebIDL text `null`; there is no unregister operation. Provider disposal invalidates calls without changing registrations.

## Validation state

- Generator regression reproduced the missing independent capability and now passes with the full generator suite (33 tests before the canonical named-getter merge).
- Official preview.11 has no rv_dom_css_register_property export, confirmed by the permanent raw regression's missing-symbol RED.
- Actual Fable browser provider passes 14 focused Chromium assertions with the explicit union, including a mandatory-initial-value grammar that distinguishes present null from omission. Old-document navigation fails rather than registering into the replacement document.
- Native runtime effects, all target RIDs, managed host provider and public package consumption remain unverified.

Before final regeneration, forward-merge canonical Native122 and the reviewed Native123 context/counter branch. Keep that stack dependency explicit until Native123 merges. The shared WebKit checkout is not changed by this generator repair.
