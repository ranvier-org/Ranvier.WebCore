# The generated DOM functions

`gen/domgen.py` reads WebKit's IDL files and writes one C function per IDL attribute getter, attribute setter
and operation of the interfaces `gen/dom.json` lists: the DOM a native app's UI needs. The functions sit
beside the hand-written ABI of `host/RanvierWebCoreAbi.h`, in the same library, and follow its conventions.

| File | Written by the generator | Compiled into |
|---|---|---|
| `host/RanvierWebCoreDom.h` | the public header: handle types, constants, enumerations, dictionary structs, `rv_dom_*`; also the lock the generator reads | (header, shipped in the package's `include/`) |
| `host/RanvierWebCoreDom.cpp` | each `rv_dom_*` calls its `ranvier_dom_*` twin | RanvierWebCoreHost |
| `host/dom/RanvierDomGlue.h` | the `ranvier_dom_*` functions WebCore exports | (header) |
| `host/dom/RanvierDomGlue.cpp` | the glue: argument checks, the C++ call, result conversion | WebCore, through patch 0012 |
| `tests/abi/NativeDom.fs` | the F# P/Invoke declarations | the F# driver |
| `gen/dom-report.txt` | counts, and each member left out with the reason | |

```
python -I gen/domgen.py write --source <webkit>   # after editing gen/dom.json or the generator
python -I gen/domgen.py check --source <webkit>   # build.py prepare and abi_tests.py run this
```

The outputs are committed: the header is the record of the ABI, and a diff of it shows what a change does to
it. `gen/Ranvier.Dom.fs` additionally defines the shared browser/native interfaces in `Ranvier.Dom`.
Core owns that interface assembly; the native managed package owns only the low-level interop modules.
`gen/dom-api.json` is the schema-versioned transport model for wrapper generation: each function includes
its declaring interface/member, IDL arguments and defaults, C parameters, recursive mapped types and result.
It also records interface bases and dictionary fields in their locked C layout order.

Unions use a sequential C struct with `present`, a one-based IDL-order tag and separate arm fields.
Sequences use `present`, `count` and `items`; variadics use the same sequence transport, including mixed
node/string arrays. Input containers are borrowed for the duration of the call. Returned containers own
their allocated strings, retained handles and nested containers; call their generated release function
exactly once. An empty returned sequence has a null buffer. A DOMImplementation handle retains its owning
document; a created HTMLDocument has its own reference and outlives that implementation handle.

The shared F# source exposes typed DUs, array sequences and variadics, nullable interface references and
optional nullable scalar/union results. Fable-only adapters unwrap input DUs and rewrap union results while
preserving browser object identity. Ordinary members are shared directly. EventTarget exposes supported
function and listener-object callbacks. Dictionary classes carry IDL defaults in both targets.

## Where the glue compiles

WebCore is a shared library on Windows (`WebCore.dll`) and macOS (`WebCore.framework`), and exports only the
members marked `WEBCORE_EXPORT`. Most DOM members are not marked, and many are inline. Four ways to reach
them were weighed:

| Approach | Result |
|---|---|
| Export each member the functions call, in patch 0010 | One hunk per member in upstream headers, a few hundred of them, each a conflict to resolve at a WebKit bump. Inline members would need moving out of line. Rejected. |
| Export every symbol of WebCore (`WINDOWS_EXPORT_ALL_SYMBOLS`, default visibility) | A DLL holds at most 65,535 exports, which WebCore's symbol count is likely to exceed (E); inline members are still absent; the library grows. Rejected. |
| Link WebCore statically into the host | Changes the structure of the Windows and Mac ports, which build WebCore as a shared library. Rejected. |
| Compile the glue into WebCore and export plain C functions | One CMake hook in WebCore, unchanged by the number of members. The glue sees every member, inline or not. Chosen. |

Patch 0012 (`0012-embedder-sources`) adds `WebCore_EMBEDDER_SOURCES` to WebCore's sources, outside the
unified build. `config/common.cmake` sets it to `host/dom/RanvierDomGlue.cpp` in this repository, so the
glue builds from here and the WebKit checkout carries only the hook.

- **Windows (clang-cl, `WebCore.dll`):** `WEBCORE_EXPORT` is `__declspec(dllexport)` while WebCore builds and
  `dllimport` in the host.
- **macOS (`WebCore.framework`):** `WEBCORE_EXPORT` is default visibility. `WebCore.unexp` hides only C++
  standard library symbols, and the host already links the framework as an allowed client (`TestWebCore`).
  The glue includes WebCore's own headers from WebCore's source directories, so it reads the
  headers `PlatformCocoa.cmake` leaves out of the framework from source.
- **Linux (WPE):** WebCore is an `OBJECT` library, so its objects, the glue among them, link into
  `libRanvierWebCoreHost.so` directly.

The host defines each public `rv_dom_*` function as a call to its `ranvier_dom_*` twin, so every port exports
the same names from `RanvierWebCoreHost`, the one library the app loads. The two names differ because on
Linux both halves link into the same library. A call costs one extra direct call (E: a few nanoseconds).

## Naming

### Selected IDL namespaces

`namespaceBindings` selects real IDL namespace operations with a checked node context. CSS support
queries borrow a Document and call `DOMCSSNamespace::supports` with its parser settings. Their
`dom-css-supports` capability requires every selected overload to be compiled; namespace, partial
namespace and member feature gates all apply. Unselected namespace members stay excluded.

`rv_dom_css_supports_2` tests a property/value pair and `rv_dom_css_supports_1` tests a condition.
Each string is a `const uint8_t*` plus signed byte length, as every generated string input is. Failed calls
preserve the result.

Run `python -I tests/abi/css_supports.py --native-directory <staged-native-directory>` for real parser,
complete-input and receiver/thread validation. Every packaged slim CI target runs this probe.

`windowBindings` selects direct Window instance operations using a checked Document receiver.
`rv_dom_window_get_computed_style` returns a retained, live, read-only CSSStyleDeclaration for the
element or pseudo-element. A windowless context returns unsupported. Nullable input spans use
length -1 for null, zero for empty and positive lengths for complete UTF-8; invalid spans preserve
the result. Namespace and Window operations remain facade metadata rather than invented interface members.

`windowObjectBindings` selects the operations of the object a readonly Window attribute holds (`accessor`), called
through the Window of a checked Document: `rv_dom_crypto_random_uuid` calls `window()->crypto().randomUUID()`. A
windowless document returns unsupported. The functions are facades whose contract owner is the object's interface.

`typedArrayViewTypes` maps a top-level `[ReturnValue]` argument of a listed type (`ArrayBufferView`) to three
parameters: an `RV_DOM_ARRAY_BUFFER_VIEW_*` element kind, a writable `uint8_t*` buffer and its `int32_t` byte length.
The glue builds a view of that kind over a copy of the bytes, calls the member, and copies the bytes back on `RV_OK`,
which stands for the returned view. A byte length that is not a multiple of the element size raises RangeError, and an
unknown kind returns `RV_ERR_UNSUPPORTED`. A listed type nested in a union or sequence, as a result, or without
`[ReturnValue]` is not mapped.

Non-nullable IDL string results convert null internal engine strings to empty strings, matching
browser DOM conversion. Nullable string results preserve null. This includes empty computed
declarations for invalid/unresolved pseudo selectors. The computed-style ABI fixture verifies
cascade, pseudo values, live updates, read-only rejection, nullable strings and context/input errors.

`rv_dom_<interface>_<member>`, in snake case: `Element.className` gives `rv_dom_element_get_class_name` and
`rv_dom_element_set_class_name`; `HTMLInputElement.setSelectionRange` gives
`rv_dom_html_input_element_set_selection_range`. Attributes take `get_` and `set_`; operations take their own
name.

Dashed CSS descriptor aliases append `_css` to their native attribute name, so `fontFamily` and
`font-family` have distinct exports. Both call WebCore's camel-case descriptor accessor. The shared
F# contract quotes names such as ``font-family`` with double backticks.

- The `dom` prefix keeps the generated names apart from the hand-written ones, such as
  `rv_element_get_attribute`.
- A member comes from the interface that declares it, including its partial interfaces and included mixins:
  `ParentNode.querySelector` is `rv_dom_element_query_selector`, `rv_dom_document_query_selector` and
  `rv_dom_document_fragment_query_selector`. A function takes any handle whose object implements the
  interface, so `rv_dom_element_get_id` takes an `<input>`.
- Overloads take a suffix of their argument count: `HTMLSelectElement.remove()` and `remove(index)` are
  `rv_dom_html_select_element_remove_0` and `_1`. A single mapped overload takes no suffix, and keeps the plain
  name when a later mapping adds overloads: the overload whose arguments match the committed header's function
  of that name keeps it (`Element.scrollTo(x, y)` stays `rv_dom_element_scroll_to`, and
  `scrollTo(options)` is `rv_dom_element_scroll_to_1`).
- An unnamed getter, setter or deleter takes the C++ name WebKit's bindings call: `item` and `setItem` for an
  index, `namedItem`, `setNamedItem` and `deleteNamedProperty` for a name (`rv_dom_dom_string_map_named_item`).
- Constants are `RV_DOM_<INTERFACE>_<NAME>` (`RV_DOM_NODE_ELEMENT_NODE`); enumeration values
  `RV_DOM_<ENUM>_<VALUE>` (`RV_DOM_SHADOW_ROOT_MODE_OPEN`).

## Signatures

Every function returns `int32_t`: `RV_OK` or a negative status. Its first parameter is `target`, the object
the member belongs to; the IDL arguments follow in order; the result comes last, through pointers.

| IDL type | In | Out |
|---|---|---|
| `DOMString`, `USVString`, `ByteString` | `const uint8_t*` UTF-8 and `int32_t` byte length | `char* buffer, int32_t capacity, int32_t* length`, as `rv_node_get_string`: `*length` -1 for null |
| a union of strings and Trusted Types, such as `(TrustedHTML or DOMString)` | as a string | as a string |
| `boolean` | `int32_t` 0 or 1 | `int32_t*` |
| `byte` ... `unsigned long long` | `int8_t` ... `uint64_t` | the same, by pointer |
| `float`, `double` (also `unrestricted`) | `float`, `double` | by pointer |
| IDL enumeration | `int32_t` index (attribute setters and dictionary fields) | `int32_t*` index |
| IDL dictionary | `const RvDom<Dictionary>*` | `RvDom<Dictionary>**`, owned, for a dictionary `resultDictionaries` lists |
| `record<K, V>` | the entry sequence transport of `sequence<pair<K, V>>` | the same, owned |
| interface derived from `Node` | `RvNode*` | `RvNode**`, a new reference |
| interface derived from `Event` | `RvEvent*` | `RvEvent**`, a new reference |
| `EventTarget` | (not mapped) | `RvNode**` when the target is a node, else NULL |
| other interface in scope | `Rv<Root>*`, the handle of the root of its inheritance | `Rv<Root>**`, a new reference |

The object handles are `RvCSSStyleDeclaration`, `RvDOMTokenList`, `RvDOMStringMap`, `RvAbstractRange` (for
`Range`), `RvDOMSelection` (the `Selection` interface), `RvDOMRectReadOnly`, `RvDOMRectList`, `RvNodeList`, `RvHTMLCollection`
and `RvValidityState`.

- **Nullable and optional.** A nullable argument, or an optional one without a default, is a pointer, and
  NULL means null or absent: `const int32_t* force` for `optional boolean force`. A string takes length -1
  instead. An optional argument with a default is a plain value; the header comment gives the IDL default. A
  nullable number or boolean result adds `int32_t* present`, 0 for null.
- **UTF-8 byte lengths (ABI 51).** Every string input is `const uint8_t*` plus an `int32_t` byte count, so it
  may hold U+0000. Length -1 is null, or absent for an optional string without a default, which the member
  receives as a null `String`. These return `RV_ERR_NULL_ARGUMENT`: -1 for a nonnullable string, a length
  below -1, NULL with a positive length, and invalid UTF-8. NULL with length 0 is the empty string. A string
  inside a union or sequence is an `RvDomUtf8StringSpan` (`data`, `length`), and a dictionary string field is
  an `RvDomUtf8StringInput` (`present`, `data`, `length`). The generator rejects a NUL-terminated string
  input, and the retired keys `stringInputs`, `complexStringSpans`, `interfaceStringInputs` and
  `dictionaryStringInputs`. `sequenceStringSpans` only names its interfaces' string sequences `Utf8`; those
  share the layout of the unsuffixed sequences. `browserWellFormedUnions` and `browserWellFormedSetters`
  select the USVString inputs that the Fable browser provider converts to well-formed strings.
- **Handles.** Node and event handles are the existing `RvNode` and `RvEvent`: the generated and hand-written
  functions share them, and `rv_node_release` releases both. Each other interface has its own opaque handle,
  named after the root of its inheritance, with `rv_dom_<root>_release` and `rv_dom_<root>_retain`. A
  function of a derived interface (`Range` on `RvAbstractRange`) checks the object's interface and returns
  `RV_ERR_WRONG_INTERFACE` for another one, such as a `StaticRange`. A handle is the address of its WebCore
  object, as for nodes, so two handles to one object compare equal.
  Pass handles to functions accepting their declared root type; cross-root pointer casts are outside the ABI contract.
  `DOMRectList` retains a snapshot of its rectangles; each non-null `item` result adds a separately owned rectangle reference.
- **[ReturnValue].** `Node.appendChild` and its kin write the argument's handle, as the JavaScript binding
  returns the argument.

### Dictionaries

A dictionary argument is a pointer to a struct the header defines, `RvDom<Dictionary>`, whose first field is
`uint32_t size`. The caller sets `size` to `sizeof` of the struct as it compiled it. The glue reads a field only
when `size` covers it, and a field past `size` takes its IDL default, so a later header can add fields at the
end and an app built against an earlier one keeps working. For an optional dictionary argument NULL means
every default.

- Fields follow the base dictionary's, then the dictionary's own, in IDL order. The committed header fixes the
  order: a regenerated struct keeps the existing fields in place and appends new ones.
- A field maps as an argument does: `RvDomUtf8StringInput` for a string (`present` 0 for absent), a pointer for a scalar that
  is optional without a default (NULL for absent), a plain value otherwise, `int32_t` for an enumeration and
  `RvNode*` for a node. The header comment of each field gives its IDL default. A `required` field outside
  `size` returns `RV_ERR_NULL_ARGUMENT`.
- A dictionary declared in an interface's IDL file is that interface's C++ member (`Node::GetRootNodeOptions`).
- Dictionaries can contain supported union and sequence transports. Unsupported field types still exclude
  the dictionary and its consumers; explicit exclusions are recorded in the report.

### Dictionary results

`resultDictionaries` in `gen/dom.json` lists the dictionaries a function may return. A listed dictionary keeps its
argument layout. As a result, the glue allocates the struct, sets `size` to its own `sizeof`, and owns every field:
strings, nested dictionaries (pointers), and union and sequence transports (pointers). A string or scalar field
that the engine leaves absent reads as absent (`present` 0 for an `RvDomUtf8StringInput`, NULL for a pointer).
`rv_dom_<dictionary>_release` frees the struct with everything it owns, on the main thread.

- A function result is `RvDom<Dictionary>** result`. A nullable result writes NULL for null.
- A listed dictionary may nest another listed dictionary; the nesting needs no `nestedDictionaries` entry.
- A union or sequence result arm of a listed dictionary is an owned pointer; the container's release frees it.
- A result dictionary with a node, event, object or enumeration member is left out, with its functions.
- `dom-api.json`'s `resultDictionaries` gives each listed dictionary's struct and release function.

## Statuses, exceptions and threads

| Status | When |
|---|---|
| `RV_ERR_NULL_ARGUMENT` | `target`, a non-nullable argument, a required dictionary field, or a result pointer is NULL |
| `RV_ERR_WRONG_THREAD` | the call is on a thread other than the host thread; nothing changes |
| `RV_ERR_WRONG_INTERFACE` (-11) | `target` or a handle argument is an object of another interface |
| `RV_ERR_DOM_EXCEPTION` | the member threw; `rv_last_exception` gives its name and message |
| `RV_ERR_BUFFER_TOO_SMALL` | a string result does not fit; `*length` holds the size |
| `RV_ERR_UNSUPPORTED` | WebKit compiles the member out on this platform (its IDL `Conditional`); its `[EnabledBySetting]` setting is off; the function is a stub; or an enumeration index is out of range |

The latest exception lives in WebCore (`Ranvier::recordException`, `host/dom/RanvierDomGlue.h`), and the host's
own functions record theirs there too, so `rv_last_exception` reports the latest of either.

### Settings

A member marked `[EnabledBySetting=X]` is generated, and checks the setting on each call as WebKit's bindings
check it when they expose the member: `A&B` needs both settings, `A|B` either. While the setting is off the
function returns `RV_ERR_UNSUPPORTED` and leaves the DOM unchanged. The glue reads the settings of the target's
document; for an event, of its target node's document, so an event that has no node target returns
`RV_ERR_UNSUPPORTED`; for a range, of its start container's document; for a `DOMStringMap`, of its element's.
A gated member of another interface without a document is left out, unless `creationGatedInterfaces` maps the
interface to the factory member that creates its objects (`CaretPosition` to `Document.caretPositionFromPoint`): the
factory checks the setting, so the interface's members check only settings beyond the interface's own. The generator
stops when the named factory does not carry the setting.

`finiteNumberInputs` names interfaces, or single `Interface.member` operations, whose restricted `double` and `float`
arguments reject NaN and infinities with a `TypeError`, as WebIDL conversion does.

## How the glue calls a member

The glue calls each member as WebKit's JavaScript bindings do (`CodeGenerator.pm`, `CodeGeneratorJS.pm`):

- the C++ name is the IDL name, or `[ImplementedAs]`; a setter is `set` + the name with its first letter
  uppercased; `[ImplementedBy=X]` calls `X::member(impl, ...)`;
- `[Reflect]`, `[ReflectURL]` and `[ReflectSetter]` read and write the content attribute as
  `GetterExpression` and `SetterExpression` do (`hasAttributeWithoutSynchronization`, `integralAttribute`,
  `getIdAttribute`, `setAttributeWithoutSynchronization`, `getElementAttributeForBindings`, ...);
- `[CallWith]` that names the document or script execution context passes the node's document.

C++ signatures differ from member to member and change between WebKit commits in ways the IDL does not show:
a getter returns `String`, `const AtomString&` or `ExceptionOr<String>`; a node comes back as `Element*`,
`RefPtr<Element>` or `Ref<Element>`; an argument is taken as `const String&`, `String&&`, `StringView` or a
`std::variant` with Trusted Types, a node as `Node&`, `Node*` or `Ref<Node>&&`. The glue leaves these types to
the compiler: templates in the glue's preamble unwrap `ExceptionOr`, take the raw pointer of any reference or
smart pointer, convert any string type, convert each argument to the parameter the member takes (`StringArg`,
`HandleArg`, `OptionalArg`), and assign dictionary fields whether the C++ member is optional or not
(`assignValue`, `assignString`, `assignEnumeration`). A WebKit change of these kinds only rebuilds the glue.

The C++ the IDL does not determine is listed in `gen/dom.json`: `atomArguments` names operations that take
`AtomString` for a string argument the IDL does not mark `[AtomString]`.

## Scope

`gen/dom.json` lists the scoped interfaces: `Node`, `CharacterData`, `Text`, `Comment`, `DocumentFragment`, `ShadowRoot`,
`Document`, `Element`, `Attr`, `HTMLElement` and selected HTML elements (form controls, `a`, `img`, `label`, `slot`,
lists, `details`, `dialog`, ...), `CSSStyleDeclaration`, `DOMTokenList`, `DOMStringMap`, `AbstractRange`,
`Range`, `DOMSelection` (`Selection`), `DOMRectReadOnly`, `NodeList`, `HTMLCollection`, `ValidityState`, and
`Event`, `UIEvent`, `MouseEvent`, `PointerEvent`, `WheelEvent`, `KeyboardEvent`, `FocusEvent`, `InputEvent` and
`CompositionEvent`, plus `HTMLDocument`, `DOMImplementation`, `NamedNodeMap`, `HTMLTemplateElement`,
`StaticRange`, `DOMRect` and `RadioNodeList`. The table editor surface additionally includes `HTMLTableElement`,
`HTMLTableCaptionElement`, `HTMLTableColElement`, `HTMLTableSectionElement`, `HTMLTableRowElement` and
`HTMLTableCellElement`: live row/cell collections, insertion/deletion and reflected table properties.

Additional HTML reflection covers base, breaks, data/datalist, directory/description lists, fonts, headings,
rules, html, maps, marquees, menus, metadata, edit annotations, parameters, pictures, preformatted text,
quotes, selected content, sources, time and title elements. The host enables WebCore's existing datalist
factory so `HTMLDataListElement.options` returns its live engine collection.

`nodeCastTags` handles concrete HTML classes without WebCore TypeCastTraits: a checked HTMLElement cast
and qualified HTML tag-name match precede the concrete cast. Mod, pre and quote elements use this route
for all their tag aliases; a different interface or namespace fails with `RV_ERR_WRONG_INTERFACE`.

SVGElement and MathMLElement expose their shared inline styles, dataset, nonce, autofocus, tab index and
focus operations through their actual engine types. Interface-level build and setting guards apply to
their own members and included mixins; unavailable operations keep their ABI and return `RV_ERR_UNSUPPORTED`.

Area elements expose semantic reflection, URL components and live relation tokens. The host enables
download-attribute reflection; this does not provide a navigation or download handler. Area `ping` is
excluded like the anchor equivalent.

Stylesheet discovery and rule editing include style/link elements, sheets, rule lists, media lists,
conditional/grouping rules, layers, scopes, imports, namespaces, nested declarations, keyframes, font
descriptors, counter styles, position fallbacks, starting styles and view-transition rule metadata.
Rule and descriptor setting guards use their owning stylesheet's document, or its constructor document
for constructed sheets; a detached object without either returns `RV_ERR_UNSUPPORTED` for gated members.
The host enables the existing anchor-positioning and font-metric descriptor settings. CSS generator
fixtures under `css/scripts/test/` are excluded from runtime partial interfaces.

Sheet constructors, asynchronous replacement and adopted-sheet lists still need their native bridges;
these exports do not claim those operations, layout parity or cross-platform conformance is complete.

`runtimeTypeRoots` generates UTF-8 concrete-interface queries for selected object roots. The model's
`runtimeTypeQueries` names their exports, parameter types and most-derived-first scoped interface names.
They borrow the target handle, reject null arguments and calls off the owning thread, and do not add
invented members to the shared DOM interfaces. CSS rule, stylesheet and declaration wrappers use these
queries because CSSOM's historical `CSSRule.type` returns zero for modern rule types. An unscoped subtype
reports its nearest scoped ancestor. Query names are reported separately from the IDL member count.

An `Event` root reads an `RvEvent` handle (`rv_dom_event_get_interface_name`). A root listed in
`runtimeTypePublicNames` reports the exposed interface name, `AnimationEvent` for `CSSAnimationEvent`, and
`runtimeTypeExtras` names unscoped interfaces the query still reports, such as `CustomEvent`. An event outside
both reports its nearest generated base: a `DragEvent` reads `MouseEvent`, a `TextEvent` `UIEvent`, a
`ClipboardEvent` `Event`.

A constructor with `"globalObject": true` serves `[CallWith=CurrentGlobalObject]`: the factory receives the
receiver Document's global object first, and a document without a browsing context, such as one of a destroyed
host, fails with `InvalidStateError`. `getterExpressions` maps `Interface.member` to the C++ expression a getter
reads, for a member whose C++ type differs from its IDL type (`AnimationPlaybackEvent.currentTime` converts a
`WebAnimationTime` to `CSSNumberish`).

`callbackObjectRoots` makes a callback interface, such as `NodeFilter`, an object handle root. Its arguments and
attributes pass `Rv<Name>*` handles with the generated `rv_dom_<name>_retain`/`_release`, and its members are
excluded by name. The host creates the handles (`rv_node_filter_create`), so `RanvierWebCoreAbi.h` declares the
handle type. `contract` gives the type the shared F# contract declares, and `resultEnum` the integer enumeration it
returns. A nullable attribute of the type is an F# option there; an optional argument takes the function itself.
Constants above `INT32_MAX` (`NodeFilter.SHOW_ALL`) are emitted as unsigned `#define`s and F# `u` literals.

`gen/dom-report.txt` records the generated interface/function counts, handle types, constants, enumerations,
dictionary structs and every member left out, by reason:

- **By rule:** event handler attributes (`onclick`; listeners go through `rv_node_add_event_listener`),
  constructors and static members, WebKit-prefixed members (`webkit*`), members not exposed to `Window`,
  `[Custom]` bindings and `[EnabledForWorld]` extensions.
- **Not mapped yet:** dictionary results outside `resultDictionaries`, dictionaries with unmapped members, `any`, `object`,
  `Date`, callbacks, enumeration arguments of operations, and interfaces outside the scope (
  `DOMRectList`, ...).
- **By `gen/dom.json`'s `exclude`:** browser features the patches cut or a UI does not use: cookies,
  navigation, `document.write`, fullscreen, pointer lock, form submission, legacy colours.

Partial interfaces, mixins and partial dictionaries declared under `Modules/` are skipped: they add browser
features (storage, media, payments) to `Document`, `Element` and `HTMLElement`.

## Versioning and stability

The generated surface does not change `rv_abi_version`. `rv_abi_has("dom-generated")` is 1 when the library
has the functions, and `rv_abi_has("dom:<Interface>")` when it has those of one interface, so an app can test
for an interface it needs.

- **Stable names and types.** Names and C types come from the IDL, which follows the specifications, so a
  WebKit bump that keeps an IDL member keeps its C function. C++ refactors behind the IDL are absorbed by
  the glue's templates.
- **Stable on every port.** A member WebKit compiles out on a platform keeps its function, which returns
  `RV_ERR_UNSUPPORTED`, so every port exports the same set.
- **The committed header is the lock.** The generator reads `host/RanvierWebCoreDom.h` before writing it. A
  function of the lock whose member WebKit's IDL no longer has, or no longer maps, while its interface stays
  in scope and the member is not excluded, is kept as a stub with the same signature that returns
  `RV_ERR_UNSUPPORTED`; its header comment says so, and `gen/dom-report.txt` lists it. An app built against
  the earlier header keeps binding the symbol. Removing an interface from `gen/dom.json`, or excluding a
  member, removes its functions. The lock also fixes the plain name of an overload and the field order of a
  dictionary struct.
- **Changes show up at prepare.** `build.py prepare` runs `domgen.py check` against the checkout's IDL files
  before applying the patches. A bump that adds or retypes a member in scope fails there until `write`
  updates the outputs; the diff of `RanvierWebCoreDom.h` is the ABI change to review, and `check` prints each
  function whose signature differs from the committed one. `check` prints each stub and passes when the
  outputs, stubs included, are current.

## Adding an interface or member

1. Add the interface to `gen/dom.json`, or remove a member from `exclude`. A derived interface outside the node
   and event trees needs its root too (`Range` needs `AbstractRange`).
2. `python -I gen/domgen.py write --source <webkit>`; read `gen/dom-report.txt` for what is left out.
3. Build. A compile error in `RanvierDomGlue.cpp` names a C++ signature the templates do not cover: add the
   member to `atomArguments` or `exclude`, or teach the generator the case.
4. Test it in `tests/abi/Dom.fs`.

## Known gaps

- `[CEReactions]`: the glue does not open a custom element reaction scope. The host runs no page script, so no
  custom element has script reactions; a page that defines them would see them run late.
- Enumeration arguments of operations, and dictionary results outside `resultDictionaries`, are not mapped.
- A dictionary that loses a locked field upstream is left unmapped, and the members that take it become stubs;
  `gen/dom-report.txt` names the lost fields. Keeping such a struct needs a decision on the retired field.
