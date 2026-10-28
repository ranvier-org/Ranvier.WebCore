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
it.

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

`rv_dom_<interface>_<member>`, in snake case: `Element.className` gives `rv_dom_element_get_class_name` and
`rv_dom_element_set_class_name`; `HTMLInputElement.setSelectionRange` gives
`rv_dom_html_input_element_set_selection_range`. Attributes take `get_` and `set_`; operations take their own
name.

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
| `DOMString`, `USVString`, `ByteString` | `const char*`, UTF-8 | `char* buffer, int32_t capacity, int32_t* length`, as `rv_node_get_string`: `*length` -1 for null |
| a union of strings and Trusted Types, such as `(TrustedHTML or DOMString)` | `const char*`, passed as the union's string | as a string |
| `boolean` | `int32_t` 0 or 1 | `int32_t*` |
| `byte` ... `unsigned long long` | `int8_t` ... `uint64_t` | the same, by pointer |
| `float`, `double` (also `unrestricted`) | `float`, `double` | by pointer |
| IDL enumeration | `int32_t` index (attribute setters and dictionary fields) | `int32_t*` index |
| IDL dictionary | `const RvDom<Dictionary>*` | (not mapped) |
| interface derived from `Node` | `RvNode*` | `RvNode**`, a new reference |
| interface derived from `Event` | `RvEvent*` | `RvEvent**`, a new reference |
| `EventTarget` | (not mapped) | `RvNode**` when the target is a node, else NULL |
| other interface in scope | `Rv<Root>*`, the handle of the root of its inheritance | `Rv<Root>**`, a new reference |

The object handles are `RvCSSStyleDeclaration`, `RvDOMTokenList`, `RvDOMStringMap`, `RvAbstractRange` (for
`Range`), `RvDOMSelection` (the `Selection` interface), `RvDOMRectReadOnly`, `RvNodeList`, `RvHTMLCollection`
and `RvValidityState`.

- **Nullable and optional.** A nullable argument, or an optional one without a default, is a pointer, and
  NULL means null or absent: `const int32_t* force` for `optional boolean force`, `const char*` that may be
  NULL for `DOMString?`. An optional argument with a default is a plain value; the header comment gives the
  IDL default. A nullable number or boolean result adds `int32_t* present`, 0 for null.
- **Handles.** Node and event handles are the existing `RvNode` and `RvEvent`: the generated and hand-written
  functions share them, and `rv_node_release` releases both. Each other interface has its own opaque handle,
  named after the root of its inheritance, with `rv_dom_<root>_release` and `rv_dom_<root>_retain`. A
  function of a derived interface (`Range` on `RvAbstractRange`) checks the object's interface and returns
  `RV_ERR_WRONG_INTERFACE` for another one, such as a `StaticRange`. A handle is the address of its WebCore
  object, as for nodes, so two handles to one object compare equal.
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
- A field maps as an argument does: `const char*` for a string (NULL for absent), a pointer for a scalar that
  is optional without a default (NULL for absent), a plain value otherwise, `int32_t` for an enumeration and
  `RvNode*` for a node. The header comment of each field gives its IDL default. A `required` field outside
  `size` returns `RV_ERR_NULL_ARGUMENT`.
- A dictionary declared in an interface's IDL file is that interface's C++ member (`Node::GetRootNodeOptions`).
- Dictionaries with members of other types (sequences, unions, other dictionaries, object handles) are not
  mapped, and the members that take them are left out.

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
A gated member of another interface without a document is left out.

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

`gen/dom.json` lists 55 interfaces: `Node`, `CharacterData`, `Text`, `Comment`, `DocumentFragment`, `ShadowRoot`,
`Document`, `Element`, `Attr`, `HTMLElement` and 27 HTML elements (form controls, `a`, `img`, `label`, `slot`,
lists, `details`, `dialog`, ...), `CSSStyleDeclaration`, `DOMTokenList`, `DOMStringMap`, `AbstractRange`,
`Range`, `DOMSelection` (`Selection`), `DOMRectReadOnly`, `NodeList`, `HTMLCollection`, `ValidityState`, and
`Event`, `UIEvent`, `MouseEvent`, `PointerEvent`, `WheelEvent`, `KeyboardEvent`, `FocusEvent`, `InputEvent` and
`CompositionEvent`.

They give 1,002 functions (525 getters, 270 setters, 207 operations), 9 object handle types with their release
and retain functions, 37 constants, 7 enumerations and 7 dictionary structs. `gen/dom-report.txt` lists the
466 members left out, by reason:

- **By rule:** event handler attributes (`onclick`; listeners go through `rv_node_add_event_listener`),
  constructors and static members, WebKit-prefixed members (`webkit*`), members not exposed to `Window`,
  `[Custom]` bindings and `[EnabledForWorld]` extensions.
- **Not mapped yet:** unions other than strings with Trusted Types, sequences and frozen arrays, variadic
  arguments (`append(...nodes)`), dictionary results and dictionaries with unmapped members, `any`, `object`,
  `Date`, callbacks, enumeration arguments of operations, and interfaces outside the scope (`NamedNodeMap`,
  `DOMRectList`, `StyleSheetList`, ...).
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
- Enumeration arguments of operations, unions other than strings, dictionary results, sequences and variadic
  arguments are not mapped.
- A dictionary that loses a locked field upstream is left unmapped, and the members that take it become stubs;
  `gen/dom-report.txt` names the lost fields. Keeping such a struct needs a decision on the retired field.
