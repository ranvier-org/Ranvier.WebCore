"""Generates the per-member DOM C ABI from WebKit's IDL files: one C function per IDL attribute getter, attribute
setter and operation of the interfaces gen/dom.json lists. docs/GENERATOR.md describes the design.

Usage:
  python -I gen/domgen.py write --source <webkit>   writes the files below from the checkout's IDL files
  python -I gen/domgen.py check --source <webkit>   exits 1 when a file below differs from what write would write

Outputs:
  host/RanvierWebCoreDom.h        the public C header: handle types, constants and the rv_dom_* functions
  host/RanvierWebCoreDom.cpp      the host's rv_dom_* functions, each calling its ranvier_dom_* twin in WebCore
  host/dom/RanvierDomGlue.h       the ranvier_dom_* functions WebCore exports, for the host
  host/dom/RanvierDomGlue.cpp     their definitions, compiled into WebCore by patch 0012
  tests/abi/NativeDom.fs          the F# P/Invoke declarations of the rv_dom_* functions
  gen/dom-report.txt              counts, and each member left out with the reason
"""

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import idl  # noqa: E402
from domtypes import ComplexGeneratorMixin, token as transport_token

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = ROOT / "gen" / "dom.json"
OUT_HEADER = ROOT / "host" / "RanvierWebCoreDom.h"
OUT_HOST = ROOT / "host" / "RanvierWebCoreDom.cpp"
OUT_GLUE_HEADER = ROOT / "host" / "dom" / "RanvierDomGlue.h"
OUT_GLUE = ROOT / "host" / "dom" / "RanvierDomGlue.cpp"
OUT_FSHARP = ROOT / "tests" / "abi" / "NativeDom.fs"
OUT_REPORT = ROOT / "gen" / "dom-report.txt"

NUMBERS = {
    "byte": "int8_t",
    "octet": "uint8_t",
    "short": "int16_t",
    "unsigned short": "uint16_t",
    "long": "int32_t",
    "unsigned long": "uint32_t",
    "long long": "int64_t",
    "unsigned long long": "uint64_t",
    "float": "float",
    "unrestricted float": "float",
    "double": "double",
    "unrestricted double": "double",
}
STRINGS = {"DOMString", "USVString", "ByteString"}
# Interfaces of a string union that a C string stands for: the string is passed as the union's string.
TRUSTED_TYPES = {"TrustedHTML", "TrustedScript", "TrustedScriptURL"}
FSHARP_NUMBERS = {
    "int8_t": "sbyte",
    "uint8_t": "byte",
    "int16_t": "int16",
    "uint16_t": "uint16",
    "int32_t": "int",
    "uint32_t": "uint32",
    "int64_t": "int64",
    "uint64_t": "uint64",
    "float": "float32",
    "double": "float",
}
FSHARP_KEYWORDS = set(
    """abstract and as assert base begin class default delegate do done downcast downto elif else end exception extern
    false finally fixed for fun function global if in inherit inline interface internal lazy let match member module
    mutable namespace new not null of open or override private public rec return select sig static struct then to
    true try type upcast use val void when while with yield break checked component const constraint continue event
    external include mixin parallel process protected pure sealed tailcall trait virtual""".split()
)
C_KEYWORDS = {"default", "char", "int", "float", "double", "long", "short", "unsigned", "signed", "register", "switch",
              "case", "const", "volatile", "struct", "union", "enum", "auto", "extern", "static", "goto", "return",
              "sizeof", "typedef", "void", "while", "for", "do", "if", "else", "break", "continue", "bool", "new",
              "delete", "class", "template", "this", "namespace", "operator", "private", "public", "protected", "inline"}
# The names generated functions give their own parameters, which an IDL argument does not take.
RESERVED = {"target", "buffer", "capacity", "length", "result", "present"}
# Extended attributes of a member that the generator does not map.
UNMAPPED = ["Custom", "EnabledForWorld", "EnabledByQuirk", "ForwardToMapLike", "ForwardToSetLike", "CustomBinding",
            "PrivateIdentifier", "LegacyFactoryFunction"]
# CallWith values the glue supplies from the node's document.
# How the glue reaches a document for the settings of [EnabledBySetting], by the root of an interface other than a node.
SETTINGS_DOCUMENT = {"AbstractRange": "impl->startContainer().document()", "DOMStringMap": "impl->element().document()"}
# ArrayBufferView element kinds of typedArrayViewTypes: (macro suffix, JSC view, element size), indexed by value.
TYPED_ARRAY_VIEW_KINDS = [('INT8', 'Int8Array', 1), ('UINT8', 'Uint8Array', 1), ('UINT8_CLAMPED', 'Uint8ClampedArray', 1),
                          ('INT16', 'Int16Array', 2), ('UINT16', 'Uint16Array', 2), ('INT32', 'Int32Array', 4),
                          ('UINT32', 'Uint32Array', 4), ('FLOAT16', 'Float16Array', 2), ('FLOAT32', 'Float32Array', 4),
                          ('FLOAT64', 'Float64Array', 8), ('BIG_INT64', 'BigInt64Array', 8),
                          ('BIG_UINT64', 'BigUint64Array', 8), ('DATA_VIEW', 'DataView', 1)]
TYPED_ARRAY_RUNTIME_HEAD = """
namespace {
template<typename View>
RefPtr<JSC::ArrayBufferView> typedArrayView(RefPtr<JSC::ArrayBuffer>&& buffer, int32_t length, int32_t elementSize, int32_t& status)
{
    if (length % elementSize) {
        status = Ranvier::recordException(Exception { ExceptionCode::RangeError, "The byte length is not a multiple of the element size."_s });
        return nullptr;
    }
    RefPtr<JSC::ArrayBufferView> view = View::tryCreate(WTF::move(buffer), 0, static_cast<size_t>(length / elementSize));
    if (!view)
        status = Ranvier::recordException(Exception { ExceptionCode::RangeError, "The view could not be allocated."_s });
    return view;
}

// A view of the kind (RV_DOM_ARRAY_BUFFER_VIEW_*) over a copy of the caller's bytes, or null with the status set.
RefPtr<JSC::ArrayBufferView> makeTypedArrayView(int32_t kind, const uint8_t* bytes, int32_t length, int32_t& status)
{
    RefPtr buffer = JSC::ArrayBuffer::tryCreate(length ? std::span<const uint8_t> { bytes, static_cast<size_t>(length) } : std::span<const uint8_t> { });
    if (!buffer) {
        status = Ranvier::recordException(Exception { ExceptionCode::RangeError, "The array buffer could not be allocated."_s });
        return nullptr;
    }
    switch (kind) {
"""
TYPED_ARRAY_RUNTIME_TAIL = """
    }
    status = RV_ERR_UNSUPPORTED;
    return nullptr;
}

// Copies the view's bytes, which the member may have written, back to the caller's buffer.
void copyTypedArrayView(JSC::ArrayBufferView& view, uint8_t* bytes)
{
    auto span = view.span();
    if (!span.empty())
        memcpySpan(std::span<uint8_t> { bytes, span.size() }, span);
}
}
"""
# The note a stub's comment carries.
STUB_NOTE = "WebKit's IDL no longer has this member: a stub that returns RV_ERR_UNSUPPORTED"
DOCUMENT_CALL_WITH = {"CurrentDocument", "RelevantDocument", "CurrentScriptExecutionContext",
                      "RelevantScriptExecutionContext"}


def snake(name: str) -> str:
    """innerHTML -> inner_html, HTMLInputElement -> html_input_element, DOMTokenList -> dom_token_list."""
    name = name.replace("-", "_")
    name = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
    return name.lower()


def wk_ucfirst(name: str) -> str:
    """CodeGenerator.pm's WK_ucfirst, for setter names."""
    result = name[:1].upper() + name[1:]
    if re.match(r"^Xml[^a-z]", result):
        result = "XML" + result[3:]
    return result


def flag(attrs, name):
    return name in attrs


def attr_list(value):
    if value is None or value is True:
        return []
    if isinstance(value, list):
        return value
    return re.split(r"[&|]", value)


class Mapped:
    """A C mapping of an IDL type."""

    def __init__(self, kind, nullable=False, ctype=None, interface=None, root=None, cls=None, enum=None, atom=False,
                 subtypes=(), label=None, string_spans=False):
        self.kind = kind  # string, bool, number, enum, node, event, object, dict, void
        self.atom = atom  # a string union whose DOMString is [AtomString]
        self.nullable = nullable
        self.ctype = ctype
        self.interface = interface
        self.root = root  # the handle struct's interface for object handles
        self.cls = cls  # the C++ class
        self.enum = enum
        self.subtypes = subtypes
        self.label = label
        self.string_spans = string_spans
        self.finite_input = False

    @property
    def handle(self):
        if self.kind == "dict":
            return f"RvDom{self.interface}"
        return {"node": "RvNode", "event": "RvEvent"}.get(self.kind) or f"Rv{self.root}"


class Unsupported(Exception):
    pass


def type_label(t):
    if t.name == "union":
        return "Or".join(type_label(child) for child in t.subtypes)
    if t.subtypes:
        return "".join(word[:1].upper() + word[1:] for word in t.name.split()) + "Of" + "And".join(type_label(child) for child in t.subtypes)
    return "".join(word[:1].upper() + word[1:] for word in t.name.split())


# Configuration keys of the transport before every generated string input carried an explicit byte length (WebCore
# #142, ABI 51). A stale key fails the run instead of silently selecting nothing.
RETIRED_STRING_KEYS = ('complexStringSpans', 'interfaceStringInputs', 'dictionaryStringInputs', 'stringInputs')


def retired_string_keys(value, path='gen/dom.json'):
    """The paths of every retired string-transport key in a configuration value."""
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in RETIRED_STRING_KEYS:
                found.append(f'{path}.{key}')
            found += retired_string_keys(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found += retired_string_keys(child, f'{path}[{index}]')
    return found


class World:
    def __init__(self, source: pathlib.Path, config: dict):
        retired = retired_string_keys(config)
        if retired:
            raise SystemExit('string inputs are UTF-8 with explicit byte lengths by default; remove the retired keys '
                             + ', '.join(retired))
        self.webcore = source / "Source" / "WebCore"
        self.config = config
        self.skip = config["skipDirectories"]
        self.interfaces = {}  # name -> Interface (the non-partial definition)
        self.partials = {}  # name -> [Interface]
        self.includes = {}  # target -> [(mixin, attrs)]
        self.typedefs = {}
        self.enums = {}  # name -> (values, attrs, file)
        self.dictionaries = {}  # name -> idl.Dictionary, with its partials' members
        self.callbacks = set()
        self.namespaces = {}
        self.namespace_partials = {}
        self.dictionary_partials = {}
        self.dictionary_exclusions = set()
        # True while the members of an interface in sequenceStringSpans are mapped: their string sequences are named Utf8.
        self.span_sequences = False
        # Case-folded path parts order the files the same on every platform; partial interfaces merge in this order.
        for path in sorted(self.webcore.rglob("*.idl"), key=lambda path: [part.casefold() for part in path.relative_to(self.webcore).parts]):
            relative = path.relative_to(self.webcore).as_posix()
            if relative.startswith("bindings/scripts/test/"):
                continue
            document = idl.parse(path.read_text(encoding="utf-8"), relative)
            for namespace in document.namespaces:
                if namespace.partial:
                    if not self.skipped(relative):
                        self.namespace_partials.setdefault(namespace.name, []).append(namespace)
                elif namespace.name not in self.namespaces or not self.skipped(relative):
                    self.namespaces[namespace.name] = namespace
            for interface in document.interfaces:
                if interface.partial:
                    self.partials.setdefault(interface.name, []).append(interface)
                elif interface.name not in self.interfaces or not self.skipped(interface.file):
                    self.interfaces[interface.name] = interface
            for target, mixin, attrs in document.includes:
                self.includes.setdefault(target, []).append((mixin, attrs, relative))
            self.typedefs.update(document.typedefs)
            for name, (values, attrs) in document.enums.items():
                self.enums[name] = (values, attrs, relative)
            for name, dictionary in document.dictionaries.items():
                if dictionary.partial:
                    if not self.skipped(relative):
                        self.dictionary_partials.setdefault(name, []).append(dictionary)
                elif name not in self.dictionaries or not self.skipped(relative):
                    self.dictionaries[name] = dictionary
            self.callbacks |= document.callbacks
        # A setlike or maplike declaration is a member only of an interface gen/dom.json binds it for.
        bound = {'setlike': set(config.get('setlikeBindings', {})), 'maplike': set(config.get('maplikeBindings', {}))}
        for interface in [*self.interfaces.values(), *(p for ps in self.partials.values() for p in ps)]:
            interface.members = [member for member in interface.members
                                 if member.kind not in bound or interface.name in bound[member.kind]]
        self.scope = config["interfaces"]
        missing = [name for name in self.scope if name not in self.interfaces]
        if missing:
            raise SystemExit(f"gen/dom.json names interfaces the IDL files do not define: {missing}")
        self.contract_config = config.get("contract", {})
        self.contract_aliases = self.contract_config.get("aliases", {}) | self.contract_config.get("mixins", {})
        self.contract_types = list(self.scope)
        self.tag_interfaces = []
        for key, namespace, namespace_uri in [("htmlTags", "HTML", "http://www.w3.org/1999/xhtml"),
                                              ("svgTags", "SVG", "http://www.w3.org/2000/svg")]:
            catalogue = self.contract_config.get(key)
            if not catalogue:
                continue
            for raw in (self.webcore / catalogue).read_text(encoding="utf-8").splitlines():
                raw = raw.split("#", 1)[0].strip()
                if not raw or "=" in raw.split()[0]:
                    continue
                tag, _, options = raw.partition(" ")
                properties = dict(re.findall(r"(\w+)\s*=\s*([^,\s]+)", options))
                # Match make_names.pl's SVG FE capitalization before its ucfirst conversion.
                capitalized = "FE" + tag[2:3].upper() + tag[3:] if namespace == "SVG" and tag.startswith("fe") else tag[:1].upper() + tag[1:]
                implementation = properties.get("interfaceName", namespace + capitalized + "Element")
                public = properties.get("JSInterfaceName", implementation)
                if public not in self.interfaces:
                    raise SystemExit(f"{catalogue}: {tag} names missing IDL interface {public}")
                self.tag_interfaces.append({"tag": tag, "namespaceURI": namespace_uri,
                                            "interface": public, "implementationInterface": implementation})
                if public not in self.contract_types:
                    self.contract_types.append(public)
        for name in self.contract_config.get("interfaces", []) + list(self.contract_aliases):
            if name not in self.interfaces:
                raise SystemExit(f"contract interface {name} has no WebKit IDL definition")
            if name not in self.contract_types:
                self.contract_types.append(name)
        for name in list(self.contract_types):
            for ancestor in self.chain(name)[1:]:
                if ancestor not in self.contract_types:
                    self.contract_types.insert(0, ancestor)
        self.contract_dictionary_fields = {name: self.dictionary_fields(name)
                                           for name in self.contract_config.get("dictionaries", [])}

    def public_name(self, name):
        return self.contract_aliases.get(name, name)

    def contract_mixins(self, name):
        return [mixin for mixin, _, file in self.includes.get(name, [])
                if mixin in self.contract_config.get("mixins", {}) and not self.skipped(file)]

    @staticmethod
    def member_key(member):
        return (member.kind, member.name, str(member.type), member.special,
                tuple((str(arg.type), arg.optional, arg.variadic) for arg in member.arguments))

    def contract_owner(self, interface, member):
        key = self.member_key(member)
        for mixin in self.contract_mixins(interface):
            if any(self.member_key(candidate) == key for candidate in self.members(mixin)):
                return self.public_name(mixin)
        if member.kind == "operation":
            for ancestor in self.chain(interface)[1:]:
                for candidate in self.members(ancestor):
                    if self.member_key(candidate) == key:
                        return self.contract_owner(ancestor, candidate)
        return self.public_name(interface)

    def skipped(self, file):
        return any(file.startswith(prefix) for prefix in self.skip)

    def chain(self, name):
        """The interface and its ancestors, nearest first."""
        found = []
        while name:
            found.append(name)
            interface = self.interfaces.get(name)
            name = interface.base if interface else None
        return found

    def cpp_class(self, name):
        interface = self.interfaces[name]
        return interface.attrs.get("ImplementedAs", name) if isinstance(interface.attrs.get("ImplementedAs"), str) else name

    def members(self, name):
        """The members of an interface with those of its partials and included mixins, with the extended
        attributes of the interface, partial, mixin and includes statement merged into each, as CodeGenerator.pm does."""
        interface = self.interfaces[name]
        found = [self.copy(member, {}) for member in interface.members]
        for partial in self.partials.get(name, []):
            if self.skipped(partial.file):
                continue
            found += [self.copy(member, partial.attrs) for member in partial.members]
        for mixin, include_attrs, file in self.includes.get(name, []):
            definition = self.interfaces.get(mixin)
            if not definition or self.skipped(definition.file):
                continue
            merged = dict(definition.attrs)
            merged.update({k: v for k, v in include_attrs.items()})
            found += [self.copy(member, merged) for member in definition.members]
            for partial in self.partials.get(mixin, []):
                if self.skipped(partial.file):
                    continue
                attrs = dict(partial.attrs)
                attrs.update(include_attrs)
                found += [self.copy(member, attrs) for member in partial.members]
        gates = {key: interface.attrs[key] for key in ("Conditional", "EnabledBySetting", "EnabledForWorld")
                 if key in interface.attrs}
        return [self.copy(member, gates) for member in found]

    @staticmethod
    def copy(member, merged):
        result = idl.Member(**{k: v for k, v in member.__dict__.items()})
        attrs = dict(member.attrs)
        for key in ("Conditional", "EnabledBySetting", "EnabledForWorld"):
            if key in merged:
                attrs[key] = f"{attrs[key]}&{merged[key]}" if key in attrs else merged[key]
        for key in ("ImplementedBy", "Exposed", "CallWith", "SecureContext"):
            if key in merged and key not in attrs:
                attrs[key] = merged[key]
        result.attrs = attrs
        return result

    def resolve(self, t: idl.Type) -> idl.Type:
        flatten = False
        while t.name in self.typedefs:
            flatten |= t.name in self.config.get('flattenUnionTypedefs', [])
            target = self.typedefs[t.name]
            t = idl.Type(target.name, t.nullable or target.nullable, target.subtypes, {**target.attrs, **t.attrs})
        if flatten:
            if t.name != 'union':
                raise Unsupported('configured union flattening requires a union typedef')
            def leaves(children):
                for child in children:
                    child = self.resolve(child)
                    if child.name == 'union':
                        if child.nullable:
                            raise Unsupported('configured union flattening does not support nullable nested unions')
                        yield from leaves(child.subtypes)
                    else:
                        yield child
            t = idl.Type('union', t.nullable, list(leaves(t.subtypes)), t.attrs)
        return t

    def string_union(self, t: idl.Type):
        """For a union of string types and Trusted Types, whether its DOMString is [AtomString]; else None."""
        atom = False
        for subtype in t.subtypes:
            subtype = self.resolve(subtype)
            if subtype.name == "union":
                inner = self.string_union(subtype)
                if inner is None:
                    return None
                atom = atom or inner
            elif subtype.name in STRINGS:
                atom = atom or "AtomString" in subtype.attrs
            elif subtype.name not in TRUSTED_TYPES:
                return None
        return atom

    def dictionary_fields(self, name):
        """The members of a dictionary, its bases' first, as (member, Mapped), or raises Unsupported."""
        if name not in self.dictionaries:
            raise Unsupported(f"dictionary {name} not found")
        dictionary = self.dictionaries[name]
        found = self.dictionary_fields(dictionary.base) if dictionary.base else []
        members = list(dictionary.members)
        for partial in self.dictionary_partials.get(name, []):
            members += partial.members
        for member in members:
            if f"{name}.{member.name}" in self.config["exclude"]:
                self.dictionary_exclusions.add(f"{name}.{member.name}")
                continue
            if "Conditional" in member.attrs or "EnabledBySetting" in member.attrs:
                continue
            try:
                mapped = self.map(member.type)
            except Unsupported as error:
                raise Unsupported(f"dictionary {name}: member {member.name}: {error}")
            empty_default = member.default == '{}' or member.attrs.get('ImplementationDefaultValue') == '{}'
            result_nested = (name in self.config.get("resultDictionaries", [])
                             and mapped.interface in self.config.get("resultDictionaries", []) and not mapped.nullable)
            if mapped.kind == "dict" and not result_nested and (name not in self.config.get("nestedDictionaries", [])
                                          or member.required or not empty_default or mapped.nullable):
                raise Unsupported(f"dictionary {name}: nested member {member.name} requires an opted-in nonnullable empty default")
            configured_object = f"{name}.{member.name}" in self.config.get("dictionaryObjectMembers", [])
            if configured_object and (mapped.kind != "object" or not member.required or mapped.nullable):
                raise SystemExit(f"{name}.{member.name}: dictionary object members must be required nonnullable object handles")
            if (mapped.kind in ("object", "event") and not configured_object) or mapped.interface == "EventTarget":
                raise Unsupported(f"dictionary {name}: member {member.name} of type {member.type}")
            found.append((member, mapped))
        return found

    def map(self, t: idl.Type, nested=False) -> Mapped:
        t = self.resolve(t)
        if t.name == "undefined":
            return Mapped("void")
        if t.name in STRINGS:
            return Mapped("string", t.nullable)
        if t.name == "boolean":
            return Mapped("bool", t.nullable, "int32_t")
        if t.name in NUMBERS:
            return Mapped("number", t.nullable, NUMBERS[t.name])
        if t.name in self.enums:
            if t.nullable:
                raise Unsupported(f"nullable enumeration {t.name}")
            return Mapped("enum", False, "int32_t", enum=t.name)
        if t.name == "EventTarget":
            return Mapped("node", t.nullable, interface="EventTarget", cls="EventTarget")
        if t.name in self.config.get('byteSpanTypes', []):
            if t.nullable:
                raise Unsupported(f'nullable byte span {t.name}')
            if not nested:
                raise Unsupported(f'byte span {t.name} outside a union or sequence input')
            return Mapped('bytes', False, 'RvDomByteSpan', label=t.name)
        if t.name in self.config.get('typedArrayViewTypes', []):
            if t.nullable:
                raise Unsupported(f'nullable typed array view {t.name}')
            if nested:
                raise Unsupported(f'typed array view {t.name} inside a union or sequence')
            return Mapped('typedarray', False, 'uint8_t*', label=t.name)
        if t.name in self.config.get('opaqueUnionArms', []):
            return Mapped('opaque', t.nullable, interface=t.name, cls=self.cpp_class(t.name))
        if t.name in self.interfaces and not self.interfaces[t.name].mixin:
            if self.interfaces[t.name].callback:
                if t.name not in self.config.get("callbackObjectRoots", []) or t.name not in self.scope:
                    raise Unsupported(f"callback {t.name}")
                return Mapped("object", t.nullable, interface=t.name, root=t.name, cls=self.cpp_class(t.name))
            chain = self.chain(t.name)
            if "Node" in chain:
                if t.name not in self.scope:
                    raise Unsupported(f"interface {t.name} outside gen/dom.json")
                return Mapped("node", t.nullable, interface=t.name, cls=self.cpp_class(t.name))
            if "Event" in chain:
                if t.name not in self.scope:
                    raise Unsupported(f"interface {t.name} outside gen/dom.json")
                return Mapped("event", t.nullable, interface=t.name, cls=self.cpp_class(t.name))
            root = chain[-1]
            if root not in self.scope and not (root == "EventTarget" and t.name in self.config.get("eventTargetObjects", {})):
                raise Unsupported(f"interface {t.name} outside gen/dom.json")
            return Mapped("object", t.nullable, interface=t.name, root=root, cls=self.cpp_class(t.name))
        if t.name == "union":
            strings = self.string_union(t)
            if strings is not None:
                return Mapped("string", t.nullable, atom=strings)
            children = [self.map(child, nested=True) for child in t.subtypes]
            label = "Or".join(type_label(self.resolve(child)) for child in t.subtypes)
            if label in self.config.get('finiteUnionInputs', []):
                for source, child in zip(t.subtypes, children):
                    child.finite_input = self.resolve(source).name in ('double', 'float')
            for child in children:
                if child.kind == 'string':
                    child.string_spans = True
            return Mapped("union", t.nullable, "RvDomUnion" + label + ("Nullable" if t.nullable else ""),
                          subtypes=children, label=label)
        if t.name in ("sequence", "FrozenArray"):
            child = self.map(t.subtypes[0], nested=True)
            element = self.resolve(t.subtypes[0])
            label = type_label(element)
            if child.kind == 'pair':
                label = child.ctype.removeprefix('RvDom')
            if element.nullable and element.name in self.config.get('complexNullableElements', []):
                label += 'NullableElement'
            if child.kind == 'string':
                child.string_spans = True
            if self.span_sequences and (child.kind == 'string' or (child.kind == 'sequence' and child.ctype.endswith('Utf8'))):
                # FUTURE CLEANUP: the Utf8 name predates length-delimited strings everywhere; RvDomSequenceUSVStringUtf8
                # and RvDomSequenceUSVString now share a layout. The name stays for ABI and wrapper stability.
                label += 'Utf8'
            return Mapped("sequence", t.nullable, "RvDomSequence" + label + ("Nullable" if t.nullable else ""),
                          subtypes=[child], label=label + " sequence")
        if t.name == 'pair' and len(t.subtypes) == 2:
            children = [self.map(child) for child in t.subtypes]
            labels = []
            for value, child in zip(t.subtypes, children):
                resolved = self.resolve(value)
                labels.append(child.ctype.removeprefix('RvDom') if child.kind in ('union', 'sequence', 'pair')
                              else type_label(resolved) + ('Nullable' if resolved.nullable else ''))
                if child.kind == 'string':
                    child.string_spans = True
            label = 'And'.join(labels)
            return Mapped('pair', False, 'RvDomPair' + label, subtypes=children, label=label + ' entry')
        if t.name == "record" and len(t.subtypes) == 2:
            # WebCore holds a record as Vector<KeyValuePair<K, V>>: the transport of a sequence of entries.
            return self.map(idl.Type("sequence", t.nullable, [idl.Type("pair", subtypes=list(t.subtypes))]))
        if t.name in ("record", "Promise", "ObservableArray"):
            raise Unsupported(f"{t.name} type {t}")
        if t.name in self.dictionaries:
            self.dictionary_fields(t.name)
            return Mapped("dict", t.nullable, interface=t.name)
        if t.name in self.callbacks or t.name in ("EventHandler", "OnErrorEventHandler", "OnBeforeUnloadEventHandler"):
            raise Unsupported(f"callback {t.name}")
        raise Unsupported(f"type {t}")


class Function:
    """One generated C function."""

    def __init__(self, interface, member, kind, name, params, comment):
        self.interface = interface
        self.member = member
        self.kind = kind  # getter, setter, operation
        self.name = name  # without the rv_dom_ prefix
        self.params = params  # [(ctype, name)]
        self.comment = comment
        self.body = []
        self.conditional = None
        self.unused = False  # a stub, whose parameters the glue does not read


def c_name(name):
    name = snake(name) if not name.isupper() else name.lower()
    return name + "_" if name in RESERVED or name in C_KEYWORDS else name


class Generator(ComplexGeneratorMixin):
    unsupported_type = Unsupported
    result_field_name = staticmethod(lambda name: c_name(name))
    def __init__(self, world: World):
        self.world = world
        self.functions = []
        self.excluded = []  # (Interface.member, reason)
        self.constants = []  # (macro, value, comment)
        self.typed_array_views_used = False
        self.enums_used = {}
        self.handles = []  # object handle roots
        self.headers = {"HTMLNames.h", "ElementInlines.h", "NodeInlines.h", "Exception.h", "ExceptionOr.h"}
        self.interface_headers = {}
        for name, header in world.config.get('interfaceHeaders', {}).items():
            if name not in world.scope:
                raise SystemExit(f'{name}: interface header override requires a selected interface')
            if (not isinstance(header, str) or not header.endswith('.h') or '\\' in header
                    or pathlib.PurePosixPath(header).is_absolute() or pathlib.PureWindowsPath(header).is_absolute()
                    or '..' in pathlib.PurePosixPath(header).parts):
                raise SystemExit(f'{name}: interface header must name a WebCore-relative header')
            path = world.webcore / header
            if not path.resolve().is_relative_to(world.webcore.resolve()) or not path.is_file():
                raise SystemExit(f'{name}: interface header must exist inside WebCore: {header}')
            self.interface_headers[f'{world.cpp_class(name)}.h'] = header
        excludes = world.config["exclude"]
        self.exclude = set(excludes)
        self.dicts_used = {}  # name -> [(member, Mapped)] in struct order
        self.lock, self.lock_structs = read_lock(OUT_HEADER)
        self.stubs = []
        self.changed = []  # names whose C signature differs from the lock
        self.complex_used = {}
        self.complex_inputs = set()
        self.result_dicts = {}  # name -> struct, for dictionaries the glue encodes as owned results
        self.namespace_features = []
        self.const_getters_used = set()
        self.setter_checks_used = set()
        self.svg_matrix_bindings = set(world.config.get('svgMatrixDictionaryBindings', []))
        supported_svg_matrix_bindings = {'SVGSVGElement.createSVGTransformFromMatrix', 'SVGTransform.setMatrix', 'SVGTransformList.createSVGTransformFromMatrix'}
        unsupported_svg_matrix_bindings = self.svg_matrix_bindings - supported_svg_matrix_bindings
        if unsupported_svg_matrix_bindings:
            raise SystemExit(f'unsupported SVG matrix dictionary binding: {sorted(unsupported_svg_matrix_bindings)}')
        self.svg_matrix_bindings_used = set()
        self.tracked_roots = {}
        for root, concrete in world.config.get('trackedHandleRoots', {}).items():
            if root not in world.scope or concrete not in world.scope or world.chain(concrete) != [concrete, root]:
                raise SystemExit(f'{root}: tracked handles require a scoped root and one direct mutable subtype')
            self.tracked_roots[world.cpp_class(root)] = world.cpp_class(concrete)

    def run(self):
        for name in self.world.scope:
            interface = self.world.interfaces[name]
            self.headers.add(f"{self.world.cpp_class(name)}.h")
            chain = self.world.chain(name)
            if "Node" not in chain and "Event" not in chain:
                root = chain[-1]
                if root == "EventTarget" and name in self.world.config.get("eventTargetObjects", {}):
                    # An event target handle is the RvEventTarget of the hand-written event ABI.
                    if chain != [name, root]:
                        raise SystemExit(f"{name}: an event target object must derive directly from EventTarget")
                elif root not in self.world.scope:
                    raise SystemExit(f"{name}: gen/dom.json lists an interface without its base {root}, which names the handle")
                if root == name:
                    self.handles.append(name)
            self.interface(name)
        for name, binding in self.world.config.get("namespaceBindings", {}).items():
            self.namespace(name, binding)
        for name, bindings in self.world.config.get("windowBindings", {}).items():
            # A list holds one binding per capability feature.
            for binding in bindings if isinstance(bindings, list) else [bindings]:
                self.window_context(name, binding)
        for name, binding in self.world.config.get('windowObjectBindings', {}).items():
            self.window_object_context(name, binding)
        for name, binding in self.world.config.get("staticBindings", {}).items():
            self.static_context(name, binding)
        for name, binding in self.world.config.get('iterableBindings', {}).items():
            self.iterable_snapshot(name, binding)
        for kind in ('setlike', 'maplike'):
            for name, binding in self.world.config.get(f'{kind}Bindings', {}).items():
                self.collection_like(name, kind, binding)
        missing_const_getters = set(self.world.config.get('constGetterBindings', {})) - self.const_getters_used
        if missing_const_getters:
            raise SystemExit(f'configured const getters did not match selected object getters: {sorted(missing_const_getters)}')
        missing_setter_checks = set(self.world.config.get('setterValueChecks', {})) - self.setter_checks_used
        if missing_setter_checks:
            raise SystemExit(f'configured setter checks did not match selected setters: {sorted(missing_setter_checks)}')
        missing_svg_matrix_bindings = self.svg_matrix_bindings - self.svg_matrix_bindings_used
        if missing_svg_matrix_bindings:
            raise SystemExit(f'configured SVG matrix dictionary bindings did not match selected operations: {sorted(missing_svg_matrix_bindings)}')
        self.add_stubs()
        releases = [snake(name) for name in self.handles] + [snake(name) for name in self.result_dicts]
        if len(set(releases)) != len(releases):
            raise SystemExit(f"dictionary result releases collide with handle releases: {sorted(releases)}")
        terminated = [f"rv_dom_{f.name}" for f in self.functions if any(ctype == "const char*" for ctype, _ in f.params)]
        if terminated:
            raise SystemExit(f"NUL-terminated string inputs, which truncate at U+0000: {terminated}")
        names = [f.name for f in self.functions]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise SystemExit(f"generated names collide: {sorted(duplicates)}")
        self.runtime_queries = []
        for root in self.world.config.get("runtimeTypeRoots", []):
            # An Event root reads an RvEvent handle; every other root is a scoped object handle.
            if root not in self.handles and root != "Event":
                raise SystemExit(f"{root}: runtime type query requires a scoped object-handle root")
            # Extras are interfaces outside the scope that the query still names, such as CustomEvent.
            extras = self.world.config.get("runtimeTypeExtras", {}).get(root, [])
            for name in extras:
                if name in self.world.scope or name not in self.world.interfaces:
                    raise SystemExit(f"{root}: runtime type extra {name} must be an unscoped IDL interface")
                self.headers.add(f"{name}.h")
            interfaces = sorted((name for name in [*self.world.scope, *extras] if root in self.world.chain(name) and name != root),
                                key=lambda name: (-len(self.world.chain(name)), name))
            for name in interfaces:
                self.cast_expression(self.world.cpp_class(name), self.world.cpp_class(root), "*impl")
            public = root in self.world.config.get("runtimeTypePublicNames", [])
            self.runtime_queries.append({
                "root": root,
                "function": f"rv_dom_{snake(root)}_get_interface_name",
                "feature": f"dom-type-query:{root}",
                "interfaces": interfaces + [root],
                "names": [self.world.public_name(name) if public else name for name in interfaces + [root]],
                "extras": extras,
                "parameters": [{"ctype": f"Rv{root}*", "name": "target"}, {"ctype": "char*", "name": "buffer"},
                               {"ctype": "int32_t", "name": "capacity"}, {"ctype": "int32_t*", "name": "length"}],
            })

    def skip(self, interface, member, reason):
        label = member.name or member.special or member.kind
        self.excluded.append((f"{interface}.{label}", reason))

    def window_context(self, name, binding):
        if name != 'DOMWindow' or binding.get('receiver') != 'Document':
            raise SystemExit('Window bindings require DOMWindow with a Document receiver')
        if name not in self.world.interfaces:
            raise SystemExit(f'{name}: configured Window interface was not found')
        if 'Document' not in self.world.scope:
            raise SystemExit(f'{name}: Window context receiver must be a scoped Document')
        self.headers.add('LocalDOMWindow.h')
        selected = set(binding['members'])
        operations = {}
        definition = self.world.interfaces[name]
        members = [self.scoped_member(member, definition.attrs) for member in definition.members]
        for partial in self.world.partials.get(name, []):
            if not self.world.skipped(partial.file):
                members += [self.scoped_member(member, partial.attrs, definition.attrs) for member in partial.members]
        attributes = {}
        for member in members:
            if member.name not in selected:
                continue
            reason = self.member_reason(name, member)
            readonly_attribute = member.kind == 'attribute' and member.readonly
            if reason or (member.kind != 'operation' and not readonly_attribute):
                raise SystemExit(f'{name}.{member.name}: {reason or "configured member is not an operation or a readonly attribute"}')
            if member.attrs.get('CallWith') or member.attrs.get('ImplementedBy') or member.attrs.get('GetterCallWith'):
                raise SystemExit(f'{name}.{member.name}: Window context bindings require a direct instance member')
            if readonly_attribute:
                attributes[member.name] = member
            else:
                operations.setdefault(member.name, []).append(member)
        if selected != set(operations) | set(attributes):
            raise SystemExit(f'{name}: missing configured Window members {sorted(selected - set(operations) - set(attributes))}')
        generated = []
        for attribute, member in attributes.items():
            function = Function(name, member, 'context_operation', f'window_get_{snake(attribute)}', [],
                                f'Window.{attribute} getter: checked Document context')
            function.receiver = 'Document'
            function.feature = binding['feature']
            function.context_checks = ['if (!impl->window())', '    return RV_ERR_UNSUPPORTED;']
            try:
                result = self.world.map(member.type)
                call = f'impl->window()->{member.attrs.get("ImplementedAs", member.name)}()'
                self.finish(function, 'Document', member, [], [], result, call, [])
            except Unsupported as error:
                raise SystemExit(f'{name}.{member.name}: {error}') from error
            generated.append(function)
        for operation, overloads in operations.items():
            for member in overloads:
                suffix = '' if len(overloads) == 1 else f'_{len(member.arguments)}'
                function = Function(name, member, 'context_operation', f'window_{snake(operation)}{suffix}', [],
                                    f'Window.{operation}: checked Document context; nullable string byte length -1 means null')
                function.receiver = 'Document'
                function.feature = binding['feature']
                function.context_checks = ['if (!impl->window())', '    return RV_ERR_UNSUPPORTED;']
                try:
                    args = [self.world.map(argument.type) for argument in member.arguments]
                    result = self.world.map(member.type)
                    placeholders = ', '.join(f'{{arg{i}}}' for i in range(len(args)))
                    call = f'impl->window()->{member.attrs.get("ImplementedAs", member.name)}({placeholders})'
                    self.finish(function, 'Document', member, member.arguments, args, result, call, [])
                except Unsupported as error:
                    raise SystemExit(f'{name}.{member.name}: {error}') from error
                generated.append(function)
        self.namespace_features.append((binding['feature'], [function.conditional for function in generated if function.conditional]))

    def window_object_context(self, name, binding):
        """The operations and readonly attributes of the object a chain of readonly attributes from the Window holds,
        such as Window.crypto or Window.screen.orientation, called through the Window of a checked Document."""
        if binding.get('receiver') != 'Document' or 'Document' not in self.world.scope:
            raise SystemExit(f'{name}: Window object bindings require a scoped Document receiver')
        if name not in self.world.interfaces or 'DOMWindow' not in self.world.interfaces:
            raise SystemExit(f'{name}: configured Window object interface was not found')
        accessor = binding.get('accessor') or ''
        holder, steps, gates = 'DOMWindow', [], []
        for index, step in enumerate(accessor.split('.')):
            target = name if index == len(accessor.split('.')) - 1 else None
            found = [member for member in self.world.members(holder)
                     if member.kind == 'attribute' and member.readonly and member.name == step
                     and self.world.resolve(member.type).name in self.world.interfaces
                     and (target is None or self.world.resolve(member.type).name == target)]
            if len(found) != 1 or found[0].attrs.get('ImplementedBy') or found[0].attrs.get('CallWith'):
                raise SystemExit(f'{name}: Window object bindings require a readonly Window attribute chain to the interface')
            gates.append(found[0].attrs)
            steps.append(found[0].attrs.get('ImplementedAs', step))
            holder = self.world.resolve(found[0].type).name
            self.headers.add(f'{self.world.cpp_class(holder)}.h')
        self.headers.add('LocalDOMWindow.h')
        path = 'impl->window()->' + '().'.join(steps) + '()'
        selected = set(binding['members'])
        operations = {}
        attributes = {}
        for member in self.world.members(name):
            if member.name not in selected:
                continue
            member = self.scoped_member(member, *[{key: attrs[key] for key in ('EnabledBySetting', 'Conditional')
                                                    if key in attrs and attrs[key] != member.attrs.get(key)} for attrs in gates])
            reason = self.member_reason(name, member)
            readonly_attribute = member.kind == 'attribute' and member.readonly
            if reason or (member.kind != 'operation' and not readonly_attribute):
                raise SystemExit(f'{name}.{member.name}: {reason or "configured member is not an operation or a readonly attribute"}')
            if member.attrs.get('CallWith') or member.attrs.get('ImplementedBy') or member.attrs.get('GetterCallWith'):
                raise SystemExit(f'{name}.{member.name}: Window object bindings require a direct instance member')
            if readonly_attribute:
                attributes[member.name] = member
            else:
                operations.setdefault(member.name, []).append(member)
        if selected != set(operations) | set(attributes):
            raise SystemExit(f'{name}: missing configured Window object members {sorted(selected - set(operations) - set(attributes))}')
        generated = []
        for attribute, member in attributes.items():
            function = Function(name, member, 'context_operation', f'{snake(name)}_get_{snake(attribute)}', [],
                                f'Window.{accessor}.{attribute} getter: checked Document context')
            function.receiver = 'Document'
            function.context_owner = name
            function.feature = binding['feature']
            function.context_checks = ['if (!impl->window())', '    return RV_ERR_UNSUPPORTED;']
            try:
                result = self.world.map(member.type)
                self.finish(function, 'Document', member, [], [], result, f'{path}.{member.attrs.get("ImplementedAs", attribute)}()', [])
            except Unsupported as error:
                raise SystemExit(f'{name}.{member.name}: {error}') from error
            generated.append(function)
        for operation, overloads in operations.items():
            for member in overloads:
                suffix = '' if len(overloads) == 1 else f'_{len(member.arguments)}'
                function = Function(name, member, 'context_operation', f'{snake(name)}_{snake(operation)}{suffix}', [],
                                    f'Window.{accessor}.{operation}: checked Document context')
                function.receiver = 'Document'
                function.context_owner = name
                function.feature = binding['feature']
                function.context_checks = ['if (!impl->window())', '    return RV_ERR_UNSUPPORTED;']
                try:
                    args = [self.world.map(argument.type) for argument in member.arguments]
                    result = self.world.map(member.type)
                    placeholders = ', '.join(f'{{arg{i}}}' for i in range(len(args)))
                    call = f'{path}.{member.attrs.get("ImplementedAs", member.name)}({placeholders})'
                    self.finish(function, 'Document', member, member.arguments, args, result, call, [])
                except Unsupported as error:
                    raise SystemExit(f'{name}.{member.name}: {error}') from error
                generated.append(function)
        self.namespace_features.append((binding['feature'], [function.conditional for function in generated if function.conditional]))

    def use_typed_array_views(self):
        if self.typed_array_views_used:
            return
        self.typed_array_views_used = True
        self.headers.update({'JavaScriptCore/ArrayBuffer.h', 'JavaScriptCore/DataView.h', 'JavaScriptCore/TypedArrays.h'})
        for index, (macro, view, _) in enumerate(TYPED_ARRAY_VIEW_KINDS):
            self.constants.append((f'RV_DOM_ARRAY_BUFFER_VIEW_{macro}', str(index), f'ArrayBufferView element kind {view}'))

    def typed_array_view_runtime(self):
        if not self.typed_array_views_used:
            return []
        cases = []
        for index, (_, view, size) in enumerate(TYPED_ARRAY_VIEW_KINDS):
            if view == 'DataView':
                cases.append(f'    case {index}: return JSC::DataView::create(WTF::move(buffer), 0, static_cast<size_t>(length));')
            else:
                cases.append(f'    case {index}: return typedArrayView<JSC::{view}>(WTF::move(buffer), length, {size}, status);')
        return [TYPED_ARRAY_RUNTIME_HEAD + '\n'.join(cases) + TYPED_ARRAY_RUNTIME_TAIL]

    def iterable_snapshot(self, name, binding):
        if name not in self.world.scope:
            raise SystemExit(f'{name}: iterable snapshot requires a scoped interface')
        members = [member for member in self.world.members(name) if member.kind == 'iterable']
        if len(members) != 1 or members[0].type.subtypes[0].name != 'pair':
            raise SystemExit(f'{name}: iterable snapshot requires one key/value iterable')
        if self.world.config.get('objectContexts', {}).get(name) != 'Document':
            raise SystemExit(f'{name}: iterable snapshot requires a checked Document context')
        member = members[0]
        mapped = self.world.map(member.type)
        entry_type = self.transport_cpp(mapped.subtypes[0])
        function = Function(name, member, 'iterator_snapshot', f'{snake(name)}_entries', [],
                            f'{name}.entries: owned snapshot of the engine key/value iterable')
        function.feature = binding['feature']
        call = (f'([&]() {{ Vector<{entry_type}> entries; auto iterator = impl->createIterator(&{{call_with_bare}}); '
                'while (auto entry = iterator.next()) entries.append(WTF::move(*entry)); return entries; })()')
        self.finish(function, name, member, [], [], mapped, call, ['document'])
        self.namespace_features.append((function.feature, []))

    def collection_like(self, name, kind, binding):
        """The operations of a setlike or maplike declaration, over the engine's backing state through the C++
        adapter class binding['adapter'] (host/dom/<adapter>.h): size, has, values or get and entries, then add or
        set, delete and clear unless the declaration is readonly. values and entries return a snapshot copy."""
        if name not in self.world.scope:
            raise SystemExit(f'{name}: {kind} binding requires a scoped interface')
        members = [member for member in self.world.members(name) if member.kind == kind]
        if len(members) != 1:
            raise SystemExit(f'{name}: {kind} binding requires one {kind} declaration')
        declaration = members[0]
        adapter = binding.get('adapter', '')
        if not re.fullmatch(r'Ranvier[A-Za-z]+', adapter) or not (ROOT / 'host' / 'dom' / f'{adapter}.h').is_file():
            raise SystemExit(f'{name}: {kind} binding requires an adapter class with a header in host/dom')
        value = declaration.type.subtypes[-1]
        key = declaration.type.subtypes[0]
        boolean, size, void = idl.Type('boolean'), idl.Type('unsigned long'), idl.Type('undefined')
        if kind == 'setlike':
            reads = [('size', 'size', [], size), ('has', 'has', [idl.Argument('value', value)], boolean),
                     ('values', 'values', [], idl.Type('sequence', subtypes=[value]))]
            writes = [('add', 'add', [idl.Argument('value', value)], void),
                      ('delete', 'remove', [idl.Argument('value', value)], boolean), ('clear', 'clear', [], void)]
        else:
            nullable = idl.Type(value.name, True, list(value.subtypes), dict(value.attrs))
            reads = [('size', 'size', [], size), ('has', 'has', [idl.Argument('key', key)], boolean),
                     ('get', 'get', [idl.Argument('key', key)], nullable),
                     ('entries', 'entries', [], idl.Type('sequence', subtypes=[idl.Type('pair', subtypes=[key, value])]))]
            writes = [('set', 'set', [idl.Argument('key', key), idl.Argument('value', value)], void),
                      ('delete', 'remove', [idl.Argument('key', key)], boolean), ('clear', 'clear', [], void)]
        self.headers.add(f'{adapter}.h')
        for operation, implemented, arguments, returns in reads + ([] if declaration.readonly else writes):
            member = idl.Member('operation', operation, returns, arguments=arguments, attrs=dict(declaration.attrs),
                                file=declaration.file, owner=declaration.owner)
            snapshot = '; *result is a snapshot copy in iteration order, unchanged by later mutation' if operation in ('values', 'entries') else ''
            function = Function(name, member, 'operation', f'{snake(name)}_{snake(operation)}', [],
                                f'{name}.{operation}: {declaration.type}{snapshot}')
            try:
                args = [self.world.map(argument.type) for argument in arguments]
                result = self.world.map(returns)
                placeholders = ''.join(f', {{arg{i}}}' for i in range(len(args)))
                self.finish(function, name, member, arguments, args, result, f'WebCore::{adapter}::{implemented}(*impl{placeholders})', [])
            except Unsupported as error:
                raise SystemExit(f'{name}.{operation}: {error}') from error

    def static_context(self, name, binding):
        if name not in self.world.scope:
            raise SystemExit(f'{name}: static binding requires a scoped interface')
        receiver = binding['receiver']
        if receiver not in self.world.scope or 'Node' not in self.world.chain(receiver):
            raise SystemExit(f'{name}: static receiver must be a scoped node interface')
        selected = set(binding['members'])
        operations = {}
        for member in self.world.members(name):
            if member.name not in selected:
                continue
            checked = idl.Member(**member.__dict__)
            checked.static = False
            reason = self.member_reason(name, checked)
            if reason or member.kind != 'operation' or not member.static:
                raise SystemExit(f'{name}.{member.name}: {reason or "configured member is not a static operation"}')
            operations.setdefault(member.name, []).append(member)
        if selected != set(operations):
            raise SystemExit(f'{name}: missing configured static operations {sorted(selected - set(operations))}')
        generated = []
        for operation, overloads in operations.items():
            for member in overloads:
                suffix = '' if len(overloads) == 1 else f'_{len(member.arguments)}'
                function = Function(name, member, 'static_operation', f'{snake(name)}_{snake(operation)}{suffix}', [],
                                    f'{name}.{operation}: static operation with checked {receiver} context and UTF-8 byte lengths')
                function.receiver = receiver
                function.feature = binding.get('memberFeatures', {}).get(operation, binding['feature'])
                try:
                    args = [self.world.map(argument.type) for argument in member.arguments]
                    result = self.world.map(member.type)
                    call_with = self.call_with(attr_list(member.attrs.get('CallWith')))
                    cpp = member.attrs.get('ImplementedBy', self.world.cpp_class(name))
                    self.headers.add(f'{cpp}.h')
                    placeholders = ', '.join(f'{{arg{i}}}' for i in range(len(args)))
                    call = f'{cpp}::{member.attrs.get("ImplementedAs", member.name)}({{call_with_lead}}{placeholders})'
                    self.finish(function, receiver, member, member.arguments, args, result, call, call_with)
                except Unsupported as error:
                    raise SystemExit(f'{name}.{member.name}: {error}') from error
                generated.append(function)
        for feature in dict.fromkeys(function.feature for function in generated):
            self.namespace_features.append((feature, [function.conditional for function in generated
                                                       if function.feature == feature and function.conditional]))

    def scoped_member(self, member, *scopes):
        result = member
        for attrs in scopes:
            result = self.world.copy(result, attrs)
        for key in ('Conditional', 'EnabledBySetting', 'EnabledForWorld'):
            gates = [attrs[key] for attrs in (member.attrs, *scopes) if attrs.get(key)]
            if gates:
                terms = ['']
                for gate in gates:
                    text = '&'.join(gate) if isinstance(gate, list) else gate
                    terms = [f'{left}&{right}' if left else right for left in terms for right in text.split('|')]
                result.attrs[key] = '|'.join(terms)
        return result

    def namespace(self, name, binding):
        definition = self.world.namespaces.get(name)
        if not definition:
            raise SystemExit(f"{name}: configured IDL namespace was not found")
        receiver = binding["receiver"]
        if receiver not in self.world.scope or "Node" not in self.world.chain(receiver):
            raise SystemExit(f"{name}: namespace receiver must be a scoped node interface")
        public = definition.attrs.get("InterfaceName", name)
        cpp = definition.attrs.get("ImplementedAs", name)
        self.headers.add(f"{cpp}.h")
        members = [self.scoped_member(member, definition.attrs) for member in definition.members]
        for partial in self.world.namespace_partials.get(name, []):
            members += [self.scoped_member(member, partial.attrs, definition.attrs) for member in partial.members]
        selected = set(binding["members"])
        operations = {}
        for member in members:
            if member.name not in selected:
                self.skip(name, member, "namespace member outside configured binding")
                continue
            reason = self.member_reason(name, member)
            if reason or (member.kind != "operation" and not (member.kind == "attribute" and member.readonly)):
                raise SystemExit(f"{name}.{member.name}: {reason or 'namespace members are configured operations or readonly attributes'}")
            operations.setdefault(member.name, []).append(member)
        if selected != set(operations):
            raise SystemExit(f"{name}: missing configured namespace operations {sorted(selected - set(operations))}")
        generated = []
        for operation, overloads in operations.items():
            for member in overloads:
                suffix = "" if len(overloads) == 1 else f"_{len(member.arguments)}"
                attribute = member.kind == "attribute"
                function = Function(name, member, "namespace_operation",
                                    f"{snake(public)}_{'get_' if attribute else ''}{snake(operation)}{suffix}", [],
                                    f"{public}.{operation}: namespace attribute getter with {receiver} context" if attribute else
                                    f"{public}.{operation}: namespace operation with {receiver} context and explicit UTF-8 byte lengths")
                function.namespace = public
                function.receiver = receiver
                function.feature = binding.get("memberFeatures", {}).get(operation, binding["feature"])
                try:
                    args = [self.world.map(argument.type) for argument in member.arguments]
                    result = self.world.map(member.type)
                    call_with = self.call_with(attr_list(member.attrs.get("CallWith")))
                    placeholders = ", ".join(f"{{arg{i}}}" for i in range(len(args)))
                    implemented_by = member.attrs.get("ImplementedBy", cpp)
                    self.headers.add(f"{implemented_by}.h")
                    arguments_text = "{call_with_bare}" if attribute else f"{{call_with_lead}}{placeholders}"
                    call = f"{implemented_by}::{member.attrs.get('ImplementedAs', member.name)}({arguments_text})"
                    self.finish(function, receiver, member, member.arguments, args, result, call, call_with)
                except Unsupported as error:
                    raise SystemExit(f"{name}.{member.name}: {error}") from error
                generated.append(function)
        for feature in dict.fromkeys(function.feature for function in generated):
            self.namespace_features.append((feature, [function.conditional for function in generated
                                                       if function.feature == feature and function.conditional]))

    def interface(self, name):
        self.world.span_sequences = name in self.world.config.get('sequenceStringSpans', [])
        try:
            self.interface_members(name)
        finally:
            self.world.span_sequences = False

    def interface_members(self, name):
        members = self.world.members(name)
        overloaded_constructor = sum(member.kind == 'constructor' for member in members) > 1
        seen_constants = set()
        operations = {}
        for member in members:
            if member.kind == "const":
                if member.name in seen_constants:
                    continue
                seen_constants.add(member.name)
                self.constant(name, member)
                continue
            if member.kind == "constructor":
                if name in self.world.config.get("constructors", {}):
                    self.constructor(name, member, overloaded_constructor)
                else:
                    self.skip(name, member, "constructor")
                continue
            if member.kind == "operation":
                if member.static and member.name in self.world.config.get('staticBindings', {}).get(name, {}).get('members', []):
                    continue
                if not member.name and member.special in ("getter", "setter", "deleter") and member.arguments:
                    member = self.special_name(member)
                operations.setdefault(member.name, []).append(member)
            elif member.kind == "attribute":
                self.attribute(name, member)
        for op_name, overloads in operations.items():
            supported = []
            for member in overloads:
                reason = self.member_reason(name, member)
                if reason:
                    self.skip(name, member, reason)
                    continue
                try:
                    supported.append((member, [self.world.map(idl.Type("sequence", subtypes=[a.type]) if a.variadic else a.type) for a in member.arguments],
                                      self.world.map(member.type)))
                except Unsupported as error:
                    self.skip(name, member, str(error))
            plain = self.plain_overload(name, op_name, supported)
            for index, (member, args, returns) in enumerate(supported):
                suffix = "" if len(supported) == 1 or index == plain else f"_{len(member.arguments)}"
                self.operation(name, member, args, returns, suffix)

    def special_name(self, member):
        """An unnamed getter, setter or deleter under the C++ name WebKit's bindings call: item and setItem for an
        index, namedItem, setNamedItem and deleteNamedProperty for a name."""
        index = self.world.resolve(member.arguments[0].type).name in NUMBERS
        name = {("getter", True): "item", ("setter", True): "setItem", ("getter", False): "namedItem",
                ("setter", False): "setNamedItem", ("deleter", False): "deleteNamedProperty"}.get((member.special, index))
        if not name:
            return member
        result = idl.Member(**{k: v for k, v in member.__dict__.items()})
        result.name = name
        return result

    def plain_overload(self, interface, op_name, supported):
        """The index of the overload that keeps the name without a suffix: the one the lock gives it, so a new
        overload upstream leaves the existing function as it is. None when the lock has none."""
        if len(supported) < 2:
            return None
        name = f"{snake(interface)}_{snake(op_name)}"
        locked = self.lock.get(name)
        if not locked:
            return None
        locked_names = [n for _, n in locked["params"][1:]]
        # A length-delimited string argument adds its <name>_length parameter after the data pointer.
        locked_names = [n for i, n in enumerate(locked_names)
                        if not (i and n.endswith('_length') and locked_names[i - 1] == n.removesuffix('_length'))]
        for index, (member, args, returns) in enumerate(supported):
            # The overload whose arguments are the lock's parameters before the result's.
            names = [c_name(a.name) for a in member.arguments]
            rest = locked_names[len(names):]
            if locked_names[:len(names)] == names and all(n in RESERVED for n in rest):
                return index
        return None

    def add_stubs(self):
        """Keeps each function of the lock that the IDL files no longer give, for a member still in scope, as a
        stub returning RV_ERR_UNSUPPORTED with the locked signature."""
        generated = {f.name: f for f in self.functions}
        for name, locked in self.lock.items():
            if name in generated:
                if [tuple(p) for p in generated[name].params] != [tuple(p) for p in locked["params"]]:
                    self.changed.append(name)
                continue
            match = re.match(r"(\w+)\.(\w+)", locked["comment"])
            if not match:
                continue
            interface, member = match.groups()
            if interface not in self.world.scope or f"{interface}.{member}" in self.exclude or member in self.exclude:
                continue
            comment = locked["comment"]
            if STUB_NOTE not in comment:
                comment += f"; {STUB_NOTE}"
            function = Function(interface, None, "stub", name, [tuple(p) for p in locked["params"]], comment)
            function.body = ["return RV_ERR_UNSUPPORTED;"]
            function.unused = True
            self.stubs.append(function)
        # A stub goes after the functions of its interface, in lock order.
        for stub in self.stubs:
            last = max((i for i, f in enumerate(self.functions) if f.interface == stub.interface), default=len(self.functions) - 1)
            self.functions.insert(last + 1, stub)

    def constant(self, interface, member):
        if member.name.lower().startswith("webkit"):
            return
        value = member.value
        if not re.fullmatch(r"-?(0[xX][0-9a-fA-F]+|[0-9]+)", value):
            self.skip(interface, member, f"constant {value} is not an integer")
            return
        macro = f"RV_DOM_{snake(interface).upper()}_{member.name.upper()}"
        self.constants.append((macro, value, f"{interface}.{member.name}"))

    def member_reason(self, interface, member):
        """Why the member is left out, or None."""
        label = f"{interface}.{member.name}"
        if label in self.exclude or member.name in self.exclude:
            return "excluded by gen/dom.json"
        if member.kind == 'operation' and member.special == 'stringifier' and interface not in self.world.config.get('stringifiers', []):
            return 'stringifier outside configured binding'
        if not member.name:
            return "unnamed special operation"
        if member.static:
            return "static"
        if member.name.lower().startswith(("webkit", "onwebkit")):
            return "WebKit-prefixed"
        exposed = member.attrs.get("Exposed")
        if exposed and exposed is not True:
            names = attr_list(exposed)
            if "*" not in names and "Window" not in names:
                return f"Exposed={exposed}"
        for key in UNMAPPED:
            if key in member.attrs:
                return f"[{key}]"
        return None

    def call_with(self, values):
        """The C++ expressions CallWith supplies, or raises Unsupported."""
        found = []
        for value in values:
            if value in DOCUMENT_CALL_WITH:
                found.append("document")
            else:
                raise Unsupported(f"[CallWith={value}]")
        return found

    def conditional(self, member):
        value = member.attrs.get("Conditional")
        if not value:
            return None
        if isinstance(value, list):
            value = "&".join(value)
        terms = []
        for disjunct in value.split("|"):
            terms.append(" && ".join(f"ENABLE({c})" if not c.startswith("!") else f"!ENABLE({c[1:]})"
                                     for c in disjunct.split("&")))
        return " || ".join(f"({t})" if "&&" in t and len(terms) > 1 else t for t in terms)

    def self_param(self, interface):
        chain = self.world.chain(interface)
        if "Node" in chain:
            return "RvNode*"
        if "Event" in chain:
            return "RvEvent*"
        return f"Rv{chain[-1]}*"

    def cast_expression(self, cls, root, value):
        if root in self.tracked_roots:
            if cls != self.tracked_roots[root]:
                raise Unsupported(f'{root}: unconfigured tracked subtype {cls}')
            return f'castTrackedHandle<{cls}>({value})'
        if root == "Node" and cls.startswith("SVG") and cls != "SVGElement":
            self.headers.add("SVGElementTypeHelpers.h")
        tags = self.world.config.get("nodeCastTags", {}).get(cls) if root == "Node" else None
        if tags:
            self.headers.update({"HTMLElement.h", "HTMLNames.h"})
            matches = " || ".join(f"element->hasTagName(HTMLNames::{tag}Tag)" for tag in tags)
            return (f"([&]() -> {cls}* {{ auto* element = dynamicDowncast<HTMLElement>({value}); "
                    f"return element && ({matches}) ? static_cast<{cls}*>(element) : nullptr; }}())")
        if root == "Event" and cls in self.world.config.get("eventInterfaceCasts", []):
            return (f"([&]() -> {cls}* {{ auto& event = {value}; return event.interfaceType() == EventInterfaceType::{cls} "
                    f"? static_cast<{cls}*>(&event) : nullptr; }}())")
        via = self.world.config.get("castVia", {}).get(cls)
        if via:
            self.headers.add(f"{via}.h")
            return (f"([&]() -> {cls}* {{ auto* base = dynamicDowncast<{via}>({value}); "
                    f"return base ? dynamicDowncast<{cls}>(*base) : nullptr; }}())")
        return f"dynamicDowncast<{cls}>({value})"

    # Attributes.

    def reflect(self, member, setter):
        """CodeGenerator.pm's ContentAttributeName: the HTMLNames attribute, or None."""
        attrs = member.attrs
        value = attrs.get("Reflect") or attrs.get("ReflectURL") or (attrs.get("ReflectSetter") if setter else None)
        if not value:
            return None
        if value is True:
            value = member.name.lower()
        value = value.strip('"').replace("-", "_")
        return f"HTMLNames::{value}Attr"

    def getter_call(self, interface, member, mapped):
        bridge = self.world.config.get("attributeBridges", {}).get(f"{interface}.{member.name}")
        if bridge:
            return bridge["getter"]
        # A C++ getter whose type differs from the IDL type, read through the configured conversion.
        expression = self.world.config.get("getterExpressions", {}).get(f"{interface}.{member.name}")
        if expression:
            return expression
        attribute = self.reflect(member, False)
        name = member.attrs.get("ImplementedAs", member.name)
        if mapped.kind == 'object' and self.world.resolve(member.type).name.startswith('SVGAnimated'):
            name += 'Animated'
        if "CSSStyleDeclaration" in self.world.chain(interface) and "-" in name:
            name = name.split("-")[0] + "".join(part[:1].upper() + part[1:] for part in name.split("-")[1:])
        if not attribute:
            implemented_by = member.attrs.get("ImplementedBy")
            if implemented_by:
                self.headers.add(f"{implemented_by}.h")
                return f"WebCore::{implemented_by}::{name}(*impl{{call_with}})"
            return f"impl->{name}({{call_with_bare}})"
        t = self.world.resolve(member.type).name
        if member.attrs.get("ReflectURL"):
            return f"impl->getURLAttributeForBindings({attribute})"
        if t == "boolean":
            return f"impl->hasAttributeWithoutSynchronization({attribute})"
        if t in ("double",):
            return f"impl->numericAttribute({attribute})"
        if t == "long":
            return f"impl->integralAttribute({attribute})"
        if t == "unsigned long":
            return f"impl->unsignedIntegralAttribute({attribute})"
        if t == "Element":
            return f"impl->getElementAttributeForBindings({attribute})"
        if t == "FrozenArray" and f"{interface}.{member.name}" in self.world.config.get("elementArrayReflections", []):
            # The engine's reflected elements, a snapshot of the explicitly set elements or the attribute's IDs.
            return f"impl->getElementsArrayAttributeForBindings({attribute})"
        if mapped.kind != "string":
            raise Unsupported(f"[Reflect] of type {t}")
        if attribute == "HTMLNames::idAttr":
            return "impl->getIdAttribute()"
        if attribute == "HTMLNames::nameAttr":
            return "impl->getNameAttribute()"
        return f"impl->attributeWithoutSynchronization({attribute})"

    def setting_check(self, interface, chain, setting):
        """The glue that returns RV_ERR_UNSUPPORTED while a setting of [EnabledBySetting] is off, as WebKit's
        bindings hide the member then: A&B needs both, A|B either."""
        lines = []
        if "Node" in chain:
            document = "impl->document()"
        elif "Event" in chain:
            # An event reaches the settings through its target's document; one without a node target has none.
            lines = ["RefPtr settingsNode = dynamicDowncast<Node>(impl->target());", "if (!settingsNode)",
                     "    return RV_ERR_UNSUPPORTED;"]
            document = "settingsNode->document()"
        elif chain[-1] == "CSSRule" or interface in ("CSSFontFaceDescriptors", "CSSPositionTryDescriptors"):
            self.headers.add("Document.h")
            lines = ["RefPtr<Document> settingsDocument = impl->documentForBindings();",
                     "if (!settingsDocument)", "    return RV_ERR_UNSUPPORTED;"]
            document = "(*settingsDocument)"
        elif chain[-1] == "CSSStyleDeclaration":
            root = chain[-1]
            self.headers.add("CSSStyleSheet.h")
            lines = [f"RefPtr settingsSheet = static_cast<{root}&>(*impl).parentStyleSheet();",
                     "RefPtr<Document> settingsDocument = settingsSheet ? settingsSheet->ownerDocument() : nullptr;",
                     "if (!settingsDocument && settingsSheet)",
                     "    settingsDocument = settingsSheet->constructorDocument();",
                     "if (!settingsDocument)", "    return RV_ERR_UNSUPPORTED;"]
            document = "(*settingsDocument)"
        elif chain[-1] in SETTINGS_DOCUMENT:
            document = SETTINGS_DOCUMENT[chain[-1]]
        elif interface in self.world.config.get("contextSettingsObjects", []):
            # An ActiveDOMObject reaches the settings through its script execution context, a Document on the host.
            self.headers |= {"ContextDestructionObserverInlines.h", "Document.h"}
            lines = ["RefPtr settingsDocument = dynamicDowncast<Document>(static_cast<ActiveDOMObject&>(*impl).scriptExecutionContext());",
                     "if (!settingsDocument)", "    return RV_ERR_DETACHED;"]
            document = "(*settingsDocument)"
        else:
            raise Unsupported(f"[EnabledBySetting={setting}] on {interface}, which has no document")
        self.headers |= {"DocumentSettingsValues.h", "Settings.h"}
        terms = []
        for conjunct in setting.split("&"):
            alternatives = [f"settings.{to_method_name(flag)}" for flag in conjunct.split("|")]
            terms.append(f"({' || '.join(alternatives)})" if len(alternatives) > 1 else alternatives[0])
        return lines + [f"auto& settings = {document}.settingsValues();", f"if (!({' && '.join(terms)}))", "    return RV_ERR_UNSUPPORTED;"]

    def dictionary_cpp(self, name):
        configured = self.world.config.get("dictionaryCppTypes", {}).get(name)
        if configured:
            return configured
        dictionary = self.world.dictionaries[name]
        value = dictionary.attrs.get("ImplementedAs")
        if isinstance(value, str):
            return value
        # A dictionary declared in the IDL file of an interface is a member of that interface's class.
        stem = pathlib.PurePosixPath(dictionary.file).stem
        if stem != name and stem in self.world.interfaces and self.world.interfaces[stem].file == dictionary.file:
            return f"{self.world.cpp_class(stem)}::{name}"
        return name

    def uses_dictionary_string_spans(self):
        return any(self.field_ctype(member, mapped, name) == "RvDomUtf8StringInput"
                   for name, fields in self.dicts_used.items() for member, mapped in fields)

    def use_dictionary(self, name):
        """The dictionary's fields in struct order: the lock's fields first, in its order, then new ones."""
        if name in self.dicts_used:
            return self.dicts_used[name]
        fields = self.world.dictionary_fields(name)
        self.headers.add(f"{pathlib.PurePosixPath(self.world.dictionaries[name].file).stem}.h")
        locked = self.lock_structs.get(f"RvDom{name}", [])
        current = {c_name(m.name) for m, _ in fields}
        retired = [n for n in locked if n not in current]
        if retired:
            raise Unsupported(f"dictionary {name} lost the locked fields {retired}")
        by_name = {c_name(m.name): (m, mp) for m, mp in fields}
        ordered = [by_name[n] for n in locked]
        ordered += [f for f in fields if c_name(f[0].name) not in locked]
        for member, mapped in ordered:
            if mapped.kind == "enum":
                self.enums_used[mapped.enum] = self.world.enums[mapped.enum]
            elif mapped.kind == "dict":
                self.use_dictionary(mapped.interface)
            elif mapped.kind in ("union", "sequence"):
                self.use_complex(mapped)
        self.dicts_used[name] = ordered
        return ordered

    def field_ctype(self, member, mapped, dictionary=None):
        """The C type of a dictionary field: a pointer for an optional scalar without a default, NULL for absent."""
        absent = mapped.nullable or (not member.required and member.default is None)
        if mapped.kind == "string":
            return "RvDomUtf8StringInput"
        if mapped.kind in ("node", "object"):
            return f"{mapped.handle}*"
        if mapped.kind == "dict":
            return f"const {mapped.handle}*"
        if mapped.kind in ("union", "sequence"):
            return f"const {mapped.ctype}*"
        ctype = mapped.ctype
        return f"const {ctype}*" if absent else ctype

    def dictionary_object_prefix(self, pointer, struct, cpp, target, dictionary, objects, argument):
        """Reads a dictionary's one required object member first: its C++ struct holds a Ref and has no default."""
        own = self.world.dictionaries[dictionary]
        if (len(objects) != 1 or argument.optional or not own.base or len(own.members) != 1
                or own.members[0].name != objects[0][0].name):
            raise SystemExit(f"{dictionary}: an object member must be the one own member of a derived dictionary argument")
        member, mapped = objects[0]
        field = c_name(member.name)
        root = self.world.cpp_class(mapped.root)
        self.headers.add(f"{mapped.cls}.h")
        covered = f"{pointer}->size >= offsetof({struct}, {field}) + sizeof({pointer}->{field})"
        source = f"reinterpret_cast<{root}*>({pointer}->{field})"
        cast = source if root == mapped.cls else self.cast_expression(mapped.cls, root, f"*{source}")
        return [f"if (!({covered}) || !{pointer}->{field})", "    return RV_ERR_NULL_ARGUMENT;",
                f"RefPtr<{mapped.cls}> {target}{field} = {cast};", f"if (!{target}{field})", "    return RV_ERR_WRONG_INTERFACE;",
                f"{cpp} {target} {{ {{ }}, {target}{field}.releaseNonNull() }};"]

    def dictionary_field(self, pointer, struct, target, member, mapped, dictionary=None):
        """The glue that copies one field of a C dictionary into the C++ one, when the struct's size covers it."""
        field = c_name(member.name)
        cpp_field = member.attrs.get("ImplementedAs", member.name)
        covered = f"{pointer}->size >= offsetof({struct}, {field}) + sizeof({pointer}->{field})"
        ctype = self.field_ctype(member, mapped, dictionary)
        lines = []
        if mapped.kind == "object":
            raise Unsupported(f"dictionary object member {member.name} outside a derived dictionary argument")
        if member.required:
            lines += [f"if (!({covered}))", "    return RV_ERR_NULL_ARGUMENT;"]
            covered = "true"
        if mapped.kind == "string":
            span = f"{pointer}->{field}"
            if member.required:
                lines += [f"if ({span}.present != 1)", "    return RV_ERR_NULL_ARGUMENT;"]
            lines += [f"if ({covered}) {{",
                      f"    if ({span}.present != 0 && {span}.present != 1)",
                      "        return RV_ERR_NULL_ARGUMENT;",
                      f"    if ({span}.present) {{",
                      f"        if ({span}.length < 0 || ({span}.length > 0 && !{span}.data))",
                      "            return RV_ERR_NULL_ARGUMENT;",
                      f"        if (!assignString({target}.{cpp_field}, {span}.data, {span}.length))",
                      "            return RV_ERR_NULL_ARGUMENT;",
                      "    }", "}"]
        elif mapped.kind == "node":
            self.headers.add(f"{mapped.cls}.h")
            lines.append(f"if ({covered} && {pointer}->{field}) {{")
            if mapped.cls == "Node":
                lines.append(f"    {target}.{cpp_field} = nodeOf({pointer}->{field});")
            else:
                lines.append(f"    RefPtr value = dynamicDowncast<{mapped.cls}>(*nodeOf({pointer}->{field}));")
                lines.append("    if (!value)")
                lines.append("        return RV_ERR_WRONG_INTERFACE;")
                lines.append(f"    {target}.{cpp_field} = value.get();")
            lines.append("}")
        elif mapped.kind == "dict":
            nested = 'nested_' + re.sub(r'\W', '_', f'{target}.{cpp_field}')
            lines += [f"if ({covered} && {pointer}->{field}) {{",
                      f"    const auto* {nested} = {pointer}->{field};"]
            for child_member, child in self.use_dictionary(mapped.interface):
                lines += ["    " + line for line in self.dictionary_field(
                    nested, mapped.handle, f"{target}.{cpp_field}", child_member, child, mapped.interface)]
            lines.append("}")
        elif mapped.kind in ("union", "sequence"):
            lines += [f"if ({covered} && {pointer}->{field}) {{", "    int32_t status = RV_OK;",
                      f"    auto value = decode{mapped.ctype}({pointer}->{field}, status);",
                      "    if (status != RV_OK) return status;",
                      f"    {target}.{cpp_field} = std::move(*value);", "}"]
        else:
            pointer_field = ctype.endswith("*")
            value = f"*{pointer}->{field}" if pointer_field else f"{pointer}->{field}"
            guard = f"{covered} && {pointer}->{field}" if pointer_field else covered
            if mapped.kind == "enum":
                lines.append(f"if ({guard} && !assignEnumeration({target}.{cpp_field}, {value}, {enum_table(mapped.enum)}))")
                lines.append("    return RV_ERR_UNSUPPORTED;")
            else:
                if mapped.kind == "bool":
                    value = f"!!{value}"
                lines.append(f"if ({guard})")
                lines.append(f"    assignValue({target}.{cpp_field}, {value});")
        return lines

    def setter_call(self, interface, member, mapped, value):
        bridge = self.world.config.get("attributeBridges", {}).get(f"{interface}.{member.name}")
        if bridge:
            return bridge["setter"].replace("{value}", value)
        if interface == 'SVGAnimatedString' and member.name == 'baseVal':
            self.headers.add('TrustedScriptURL.h')
        attribute = self.reflect(member, True)
        if not attribute:
            name = member.attrs.get("ImplementedAs", member.name)
            if "CSSStyleDeclaration" in self.world.chain(interface) and "-" in name:
                name = name.split("-")[0] + "".join(part[:1].upper() + part[1:] for part in name.split("-")[1:])
            name = "set" + wk_ucfirst(name)
            implemented_by = member.attrs.get("ImplementedBy")
            if implemented_by:
                self.headers.add(f"{implemented_by}.h")
                return f"WebCore::{implemented_by}::{name}(*impl{{call_with}}, {value})"
            return f"impl->{name}({{call_with_lead}}{value})"
        t = self.world.resolve(member.type).name
        if t == "boolean":
            return f"impl->setBooleanAttribute({attribute}, {value})"
        if t == "double":
            return f"impl->setNumericAttribute({attribute}, {value})"
        if t == "long":
            return f"impl->setIntegralAttribute({attribute}, {value})"
        if t == "unsigned long":
            return f"impl->setUnsignedIntegralAttribute({attribute}, {value})"
        if t == "Element":
            return f"impl->setElementAttribute({attribute}, {value})"
        if t == "FrozenArray" and f"{interface}.{member.name}" in self.world.config.get("elementArrayReflections", []):
            return f"impl->setElementsArrayAttribute({attribute}, {value})"
        if mapped.kind != "string":
            raise Unsupported(f"[Reflect] of type {t}")
        return f"impl->setAttributeWithoutSynchronization({attribute}, AtomString {{ {value} }})"

    def attribute(self, interface, member):
        bridge = self.world.config.get("attributeBridges", {}).get(f"{interface}.{member.name}")
        if bridge:
            member = idl.Member(**member.__dict__)
            member.type = idl.Type("sequence", subtypes=[idl.Type(bridge["sequenceElement"])])
            member.attrs = {key: value for key, value in member.attrs.items()
                            if key not in {"CallWith", "ImplementedAs", "CachedAttribute", "CustomSetter"}}
        reason = self.member_reason(interface, member)
        if reason:
            self.skip(interface, member, reason)
            return
        try:
            mapped = self.world.map(member.type)
        except Unsupported as error:
            self.skip(interface, member, str(error))
            return
        suffix = "_css" if "-" in member.name else ""
        base = f"{snake(interface)}_{{}}_{snake(member.name)}{suffix}"
        idl_text = f"{'readonly ' if member.readonly else ''}attribute {member.type} {member.name}"
        # Getter.
        element_array = f"{interface}.{member.name}" in self.world.config.get("elementArrayReflections", [])
        if element_array and not (self.reflect(member, False) and self.world.resolve(member.type).name == "FrozenArray"):
            raise SystemExit(f"{interface}.{member.name}: element array reflections require [Reflect] FrozenArray<Element>?")
        if "CustomGetter" in member.attrs and not element_array and f"{interface}.{member.name}" not in self.world.config.get("customGetters", []):
            self.skip(interface, member, "[CustomGetter]")
        else:
            try:
                call_with = self.call_with(attr_list(member.attrs.get("CallWith")) +
                                           attr_list(member.attrs.get("GetterCallWith")))
                call = self.getter_call(interface, member, mapped)
                function = Function(interface, member, "getter", base.format("get"), [], f"{interface}.{member.name} getter: {idl_text}")
                self.finish(function, interface, member, [], [], mapped, call, call_with)
            except Unsupported as error:
                self.skip(interface, member, f"getter: {error}")
        # Setter.
        if member.readonly:
            return
        if "CustomSetter" in member.attrs:
            self.skip(interface, member, "setter: [CustomSetter]")
            return
        try:
            call_with = self.call_with(attr_list(member.attrs.get("SetterCallWith")))
            argument = idl.Argument("value", member.type)
            function = Function(interface, member, "setter", base.format("set"), [], f"{interface}.{member.name} setter: {idl_text}")
            self.finish(function, interface, member, [argument], [mapped], self.world.map(idl.Type("undefined")),
                        self.setter_call(interface, member, mapped, "{arg0}"), call_with)
        except Unsupported as error:
            self.skip(interface, member, f"setter: {error}")

    # Operations.

    def constructor(self, interface, member, overloaded=False):
        configured = self.world.config["constructors"][interface]
        receiver = configured["receiver"]
        if receiver not in self.world.scope:
            raise SystemExit(f"{interface}: constructor receiver {receiver} is outside scope")
        try:
            args = [self.world.map(idl.Type('sequence', subtypes=[argument.type]) if argument.variadic else argument.type)
                    for argument in member.arguments]
            returns = self.world.map(idl.Type(interface))
            arguments = ", ".join(f"{{arg{i}}}" for i in range(len(args)))
            if configured.get('passReceiver', True):
                arguments = f"*impl{', ' if arguments else ''}{arguments}"
            call = f"{configured['factory']}({arguments})"
            note = ""
            if configured.get('globalObject'):
                # [CallWith=CurrentGlobalObject] receives the Document's global object, absent without a frame.
                if receiver != 'Document':
                    raise SystemExit(f"{interface}: a globalObject constructor requires a Document receiver")
                cls = self.world.cpp_class(interface)
                call = (f"[&]() -> ExceptionOr<Ref<{cls}>> {{ auto* global = impl->globalObject(); if (!global) "
                        f"return Exception {{ ExceptionCode::InvalidStateError, \"The document has no global object.\"_s }}; "
                        f"return {configured['factory']}(*global{', ' if arguments else ''}{arguments}); }}()")
                note = "; RV_ERR_DOM_EXCEPTION (InvalidStateError) for a document without a browsing context"
            function = Function(interface, member, "constructor", f"{snake(interface)}_create", [],
                                f"{interface}.constructor: target is the {receiver} of the constructed object{note}")
            self.finish(function, receiver, member, member.arguments, args, returns, call, [])
            if overloaded:
                locked = self.lock.get(function.name)
                if not locked or function.params != [tuple(parameter) for parameter in locked['params']]:
                    function.name += f'_{len(member.arguments)}'
        except Unsupported as error:
            self.skip(interface, member, f"constructor: {error}")

    def operation(self, interface, member, args, returns, suffix):
        try:
            call_with = self.call_with(attr_list(member.attrs.get("CallWith")))
        except Unsupported as error:
            self.skip(interface, member, str(error))
            return
        name = member.attrs.get("ImplementedAs", member.name)
        implemented_by = member.attrs.get("ImplementedBy")
        placeholders = ", ".join(f"{{arg{i}}}" for i in range(len(args)))
        if implemented_by:
            self.headers.add(f"{implemented_by}.h")
            call = f"WebCore::{implemented_by}::{name}(*impl{{call_with}}{', ' if placeholders else ''}{placeholders})"
        else:
            call = f"impl->{name}({{call_with_lead}}{placeholders})"
        arguments = ", ".join(f"{'optional ' if a.optional else ''}{a.type} {a.name}{' = ' + a.default if a.default else ''}"
                              for a in member.arguments)
        function = Function(interface, member, "operation", f"{snake(interface)}_{snake(member.name)}{suffix}", [],
                            f"{interface}.{member.name}({arguments}) -> {member.type}")
        try:
            self.finish(function, interface, member, member.arguments, args, returns, call, call_with)
        except Unsupported as error:
            self.skip(interface, member, str(error))

    # Code.

    def finish(self, function, interface, member, arguments, mapped_args, returns, call, call_with):
        """Fills in the function's C parameters and glue body, then records it."""
        svg_matrix_key = f'{interface}.{member.name}'
        svg_matrix_binding = svg_matrix_key in self.svg_matrix_bindings
        if svg_matrix_binding:
            expected_return = 'undefined' if svg_matrix_key == 'SVGTransform.setMatrix' else 'SVGTransform'
            if (member.kind != 'operation' or len(arguments) != 1 or len(mapped_args) != 1
                    or arguments[0].name != 'matrix' or mapped_args[0].kind != 'dict'
                    or mapped_args[0].interface != 'DOMMatrix2DInit' or mapped_args[0].nullable
                    or self.world.resolve(member.type).name != expected_return):
                raise SystemExit(f'{svg_matrix_key}: requires one nonnullable DOMMatrix2DInit matrix argument and its SVG return type')
            self.svg_matrix_bindings_used.add(svg_matrix_key)
            self.headers.add('DOMMatrixReadOnly.h')
        if returns.kind == 'opaque' or any(self.contains_opaque(mapped) for mapped in mapped_args):
            raise Unsupported('an opaque interface is a union result arm only')
        self_type = self.self_param(interface)
        params = [(self_type, "target")]
        checks = ["target"]
        prepare = []
        passed = []
        notes = []
        context_receiver = None
        if call_with and 'Node' not in self.world.chain(interface):
            context_receiver = self.world.config.get('objectContexts', {}).get(interface)
            if context_receiver:
                if context_receiver != 'Document' or context_receiver not in self.world.scope:
                    raise SystemExit(f'{interface}: object context must be a scoped Document')
                if any(c_name(argument.name) == 'context' for argument in arguments):
                    raise SystemExit(f'{interface}.{member.name}: argument conflicts with checked context parameter')
                params.append(('RvNode*', 'context'))
                checks.append('context')
                self.headers.add('Document.h')
                function.context_receiver = context_receiver
                notes.append('context is an explicit checked Document for the operation')
        return_value = None
        for index, (argument, mapped) in enumerate(zip(arguments, mapped_args)):
            name = c_name(argument.name)
            optional_no_default = argument.optional and argument.default is None
            maybe_null = mapped.nullable or optional_no_default
            if argument.optional and argument.default is not None:
                notes.append(f"{name} defaults to {argument.default} in IDL")
            if mapped.kind == "string":
                # UTF-8 bytes and their count, so the string may hold U+0000; -1 is null, or absent for an optional
                # argument without a default.
                params += [("const uint8_t*", name), ("int32_t", name + "_length")]
                minimum = -1 if maybe_null else 0
                checks.append(f"({name}_length >= {minimum} && ({name}_length <= 0 || {name}))")
                null_guard = f'{name}_length >= 0 && ' if maybe_null else ''
                prepare += [f"StringArg a{index} {{ {name}, {name}_length }};",
                            f"if ({null_guard}a{index}.string().isNull()) return RV_ERR_NULL_ARGUMENT;"]
                atom = ("AtomString" in argument.attrs or "AtomString" in argument.type.attrs or mapped.atom
                        or f"{interface}.{member.name}" in self.world.config["atomArguments"])
                existing_atom = ('RequiresExistingAtomString' in argument.attrs or 'RequiresExistingAtomString' in argument.type.attrs)
                if existing_atom and optional_no_default:
                    passed.append(f'a{index}.string().isNull() ? std::nullopt : std::optional<AtomString> {{ StringView {{ a{index}.string() }}.toExistingAtomString() }}')
                elif existing_atom:
                    passed.append(f'StringView {{ a{index}.string() }}.toExistingAtomString()')
                elif optional_no_default:
                    passed.append(f"a{index}")
                else:
                    passed.append(f"a{index}.atom()" if atom else f"a{index}.string()")
                if maybe_null:
                    notes.append(f"{name}_length -1 means " + ("absent" if optional_no_default else "null"))
            elif mapped.kind in ("bool", "number"):
                ctype = mapped.ctype
                if (mapped.kind == 'number' and (function.interface in self.world.config.get('finiteNumberInputs', []) or f'{function.interface}.{member.name}' in self.world.config.get('finiteNumberInputs', []))
                        and self.world.resolve(argument.type).name in ('double', 'float')):
                    condition = f'{name} && !std::isfinite(*{name})' if maybe_null else f'!std::isfinite({name})'
                    prepare += [f'if ({condition})',
                                '    return Ranvier::recordException(Exception { ExceptionCode::TypeError, "A finite numeric value is required."_s });']
                if maybe_null:
                    params.append((f"const {ctype}*", name))
                    passed.append(f"OptionalArg<{ctype}> {{ {name} }}")
                    notes.append(f"{name} may be NULL" + (" (absent)" if optional_no_default else " (null)"))
                else:
                    params.append((ctype, name))
                    passed.append(f"!!{name}" if mapped.kind == "bool" else name)
            elif mapped.kind == "enum":
                if function.kind != "setter":
                    raise Unsupported(f"enumeration {mapped.enum} argument")
                self.enums_used[mapped.enum] = self.world.enums[mapped.enum]
                params.append(("int32_t", name))
                prepare.append(f"auto a{index} = enumerationFromIndex<std::remove_cvref_t<decltype({self.getter_call(interface, member, mapped)})>>({name}, {enum_table(mapped.enum)});")
                prepare.append(f"if (!a{index})")
                prepare.append("    return RV_ERR_UNSUPPORTED;")
                passed.append(f"*a{index}")
            elif mapped.kind == "dict":
                if mapped.nullable:
                    raise Unsupported(f"nullable dictionary {mapped.interface}")
                fields = self.use_dictionary(mapped.interface)
                struct = mapped.handle
                params.append((f"const {struct}*", name))
                if not argument.optional:
                    checks.append(name)
                else:
                    notes.append(f"{name} may be NULL for the IDL default")
                cpp = self.dictionary_cpp(mapped.interface)
                objects = [(field_member, field_mapped) for field_member, field_mapped in fields if field_mapped.kind == "object"]
                if objects:
                    prepare += self.dictionary_object_prefix(name, struct, cpp, f"a{index}", mapped.interface, objects, argument)
                else:
                    prepare.append(f"{cpp} a{index} {{ }};")
                prepare.append(f"if ({name}) {{")
                for field_member, field_mapped in fields:
                    if field_mapped.kind == "object":
                        continue
                    prepare += ["    " + line for line in self.dictionary_field(name, struct, f"a{index}", field_member, field_mapped, mapped.interface)]
                prepare.append("}")
                if svg_matrix_binding:
                    prepare += [f'auto matrixValidation{index} = DOMMatrixReadOnly::validateAndFixup(a{index});',
                                f'if (matrixValidation{index}.hasException())',
                                f'    return Ranvier::recordException(matrixValidation{index}.releaseException());']
                    prepare += [f'a{index}.{short} = a{index}.{alias};'
                                for short, alias in zip('abcdef', ['m11', 'm12', 'm21', 'm22', 'm41', 'm42'])]
                passed.append(f"std::move(a{index})")
            elif mapped.kind in ("union", "sequence"):
                self.use_complex(mapped)
                params.append((f"const {mapped.ctype}*", name))
                if self.contains_bytes(mapped) and self.contains_string_spans(mapped):
                    notes.append(f"a string part of {name} is UTF-8, and invalid UTF-8 returns RV_ERR_NULL_ARGUMENT")
                if not maybe_null and not argument.optional:
                    checks.append(name)
                if argument.optional and argument.default is None and not mapped.nullable:
                    prepare += [f'std::optional<{self.transport_cpp(mapped)}> a{index};',
                                f'if ({name}) {{', f'    int32_t status{index} = RV_OK;',
                                f'    a{index} = decode{mapped.ctype}({name}, status{index});',
                                f'    if (status{index} != RV_OK) return status{index};', '}']
                    passed.append(f'std::move(a{index})')
                    notes.append(f'{name} may be NULL for an absent optional argument')
                    continue
                prepare += [f"int32_t status{index} = RV_OK;",
                            f"auto a{index} = decode{mapped.ctype}({name}, status{index});"]
                if argument.optional and argument.default is not None and not mapped.nullable:
                    default = self.complex_default(mapped, argument.default)
                    prepare += [f"if (!{name}) {{ a{index} = {default}; status{index} = RV_OK; }}"]
                prepare += [f"if (status{index} != RV_OK) return status{index};"]
                if mapped.kind == "sequence" and not mapped.nullable:
                    passed.append(f"DomSequenceArgument<{self.transport_cpp(mapped.subtypes[0])}> {{ std::move(*a{index}) }}")
                else:
                    passed.append(f"std::move(*a{index})")
            elif mapped.kind == 'typedarray':
                if 'ReturnValue' not in argument.attrs or argument.optional or argument.variadic:
                    raise Unsupported('typed array view argument without [ReturnValue]')
                self.use_typed_array_views()
                params += [('int32_t', f'{name}_kind'), ('uint8_t*', name), ('int32_t', f'{name}_length')]
                checks.append(f'({name}_length >= 0 && ({name}_length == 0 || {name}))')
                prepare += [f'int32_t status{index} = RV_OK;',
                            f'RefPtr<JSC::ArrayBufferView> a{index} = makeTypedArrayView({name}_kind, {name}, {name}_length, status{index});',
                            f'if (!a{index})', f'    return status{index};']
                passed.append(f'*a{index}')
                notes.append(f'{name}_kind is an RV_DOM_ARRAY_BUFFER_VIEW_* element kind and {name}_length the byte length; '
                             f'the member reads and writes a copy, which returns to {name} on RV_OK; '
                             'an unknown kind returns RV_ERR_UNSUPPORTED')
                return_value = (index, mapped)
            elif mapped.kind in ("node", "event", "object"):
                if mapped.interface == "EventTarget":
                    raise Unsupported(f"{mapped.interface} argument")
                self.headers.add(f"{mapped.cls}.h")
                params.append((f"{mapped.handle}*", name))
                if mapped.kind == "object":
                    root_cls = self.world.cpp_class(mapped.root)
                    accessor, base = f"reinterpret_cast<{root_cls}*>", root_cls
                else:
                    accessor = "nodeOf" if mapped.kind == "node" else "eventOf"
                    base = "Node" if mapped.kind == "node" else "Event"
                if not maybe_null:
                    checks.append(name)
                if mapped.cls == base:
                    prepare.append(f"RefPtr<{base}> a{index} = {accessor}({name});")
                else:
                    cast = (self.cast_expression(mapped.cls, base, f'*{accessor}({name})')
                            if base in self.tracked_roots or base == 'Event'
                            else f'dynamicDowncast<{mapped.cls}>(*{accessor}({name}))')
                    prepare.append(f"RefPtr<{mapped.cls}> a{index} = {name} ? {cast} : nullptr;")
                    prepare.append(f"if ({name} && !a{index})")
                    prepare.append("    return RV_ERR_WRONG_INTERFACE;")
                passed.append(f"a{index}.get()" if maybe_null else f"HandleArg<{mapped.cls}> {{ a{index}.get() }}")
                if maybe_null:
                    notes.append(f"{name} may be NULL")
                if "ReturnValue" in argument.attrs:
                    return_value = (index, mapped)
            else:
                raise Unsupported(f"{mapped.kind} argument")
        prepare += self.setter_value_checks(function, mapped_args)
        # The result.
        sink = None
        if return_value is not None and return_value[1].kind == 'typedarray':
            sink = ('copyback', return_value[0], c_name(arguments[return_value[0]].name))
        elif return_value is not None:
            index, mapped = return_value
            params.append((f"{mapped.handle}**", "result"))
            checks.append("result")
            sink = ("returnvalue", index)
        elif returns.kind == 'typedarray':
            raise Unsupported('typed array view result')
        elif returns.kind == "string":
            params += [("char*", "buffer"), ("int32_t", "capacity"), ("int32_t*", "length")]
            checks.append("length")
            copier = 'copyString' if returns.nullable else 'copyRequiredString'
            sink = f"{copier}(asString(value), buffer, capacity, length)"
        elif returns.kind in ("bool", "number"):
            params.append((f"{returns.ctype}*", "result"))
            checks.append("result")
            if returns.nullable:
                params.append(("int32_t*", "present"))
                checks.append("present")
                sink = f"storeOptional<{returns.ctype}>(value, result, present)"
                notes.append("*present is 0 for null, and *result is then unchanged")
            else:
                sink = f"store<{returns.ctype}>(value, result)"
        elif returns.kind == "enum":
            self.enums_used[returns.enum] = self.world.enums[returns.enum]
            params.append(("int32_t*", "result"))
            checks.append("result")
            sink = f"storeEnumeration(value, result, {enum_table(returns.enum)})"
        elif returns.kind in ("node", "event", "object"):
            self.headers.add(f"{returns.cls}.h")
            params.append((f"{returns.handle}**", "result"))
            checks.append("result")
            root = {"node": "Node", "event": "Event"}.get(returns.kind) or self.world.cpp_class(returns.root)
            if returns.interface == "EventTarget":
                sink = "storeNode(dynamicDowncast<Node>(rawPointer<EventTarget>(value)), result)"
            else:
                label = f'{function.interface}.{member.name}'
                const_binding = self.world.config.get('constGetterBindings', {}).get(label)
                if const_binding is not None:
                    if (function.kind != 'getter' or returns.kind != 'object' or root in self.tracked_roots
                            or const_binding.get('interface') != returns.interface or const_binding.get('root') != returns.root):
                        raise SystemExit(f'{label}: const getter requires the exact declared interface/root of a polymorphic object getter')
                    self.const_getters_used.add(label)
                    sink = f'storeConstGetter<{root}, {returns.cls}>(value, result)'
                else:
                    sink = (f"storeTrackedHandle<{root}, {returns.cls}>(value, result)" if root in self.tracked_roots
                            else f"storeHandle<{root}>(value, result)")
            notes.append("*result is a new reference" + (", or NULL" if returns.nullable or returns.interface == "EventTarget" else ""))
        elif returns.kind == "dict":
            struct = self.use_result_dictionary(returns.interface)
            params.append((f"{struct}**", "result"))
            checks.append("result")
            if returns.nullable:
                sink = f"storeOptionalDictionary(value, result, [](const auto& item) {{ return encodeDict{struct}(item); }})"
                notes.append("*result is NULL for null")
            else:
                sink = f"(*result = encodeDict{struct}(value), RV_OK)"
            notes.append(f"*result is owned; release it with rv_dom_{snake(returns.interface)}_release")
        elif returns.kind in ("union", "sequence"):
            if not self.transport_can_return(returns):
                raise Unsupported("dictionary result in a union or sequence")
            self.use_complex(returns, input=False)
            params.append((f"{returns.ctype}*", "result"))
            checks.append("result")
            sink = f"encode{returns.ctype}(value, result)"
            notes.append("*result owns its contents; release with the matching rv_dom_*_release")
        # The body.
        cls = self.world.cpp_class(interface)
        chain = self.world.chain(interface)
        body = [f"if ({' || '.join('!' + c for c in checks)})", "    return RV_ERR_NULL_ARGUMENT;",
                "if (!isMainThread())", "    return RV_ERR_WRONG_THREAD;"]
        if "Node" in chain:
            if cls == "Node":
                body.append("RefPtr<Node> impl = nodeOf(target);")
            else:
                body += [f"RefPtr impl = {self.cast_expression(cls, 'Node', '*nodeOf(target)')};", "if (!impl)", "    return RV_ERR_WRONG_INTERFACE;"]
        elif "Event" in chain:
            if cls == "Event":
                body.append("RefPtr<Event> impl = eventOf(target);")
            else:
                body += [f"RefPtr impl = {self.cast_expression(cls, 'Event', '*eventOf(target)')};", "if (!impl)", "    return RV_ERR_WRONG_INTERFACE;"]
        else:
            root_cls = self.world.cpp_class(chain[-1])
            if root_cls == cls:
                body.append(f"RefPtr<{cls}> impl = reinterpret_cast<{cls}*>(target);")
            else:
                body += [f"RefPtr impl = {self.cast_expression(cls, root_cls, f'*reinterpret_cast<{root_cls}*>(target)')};", "if (!impl)",
                         "    return RV_ERR_WRONG_INTERFACE;"]
        setting = member.attrs.get("EnabledBySetting")
        if setting and "Event" in chain and self.world.interfaces[interface].attrs.get("EnabledBySetting") == setting:
            # An event of a gated interface exists only where its setting was on: its constructor checks the
            # setting, and the engine creates one only then. A constructed event has no target before dispatch.
            setting = None
        if setting and interface in self.world.config.get("creationGatedInterfaces", {}) and self.world.interfaces[interface].attrs.get("EnabledBySetting") == setting:
            # An object of the interface comes only from its listed factory, which checks the same setting.
            factory = self.world.config["creationGatedInterfaces"][interface]
            owner, name = factory.split(".")
            if not any(m.name == name and setting in m.attrs.get("EnabledBySetting", "").split("&") for m in self.world.members(owner)):
                raise SystemExit(f"creationGatedInterfaces: {factory} does not check [EnabledBySetting={setting}]")
            setting = None
        if setting:
            body += self.setting_check(interface, chain, setting)
            notes.append(f"RV_ERR_UNSUPPORTED while the setting {setting} is off")
        if call_with:
            if "Node" not in chain:
                if not context_receiver:
                    raise Unsupported("[CallWith] on an interface other than a node")
                body += ['RefPtr contextDocument = dynamicDowncast<Document>(*nodeOf(context));',
                         'if (!contextDocument)', '    return RV_ERR_WRONG_INTERFACE;',
                         'Ref document = contextDocument.releaseNonNull();']
            else:
                body.append("Ref document = impl->document();")
        attached = self.world.config.get("eventTargetObjects", {}).get(interface, {}).get("attached")
        if attached:
            body += [f"if (!({attached}))", "    return RV_ERR_DETACHED;"]
            notes.append("RV_ERR_DETACHED once the object's window has no frame")
        body += getattr(function, 'context_checks', [])

        def with_context(text):
            text = text.replace("{call_with}", "".join(", document.get()" for _ in call_with))
            text = text.replace("{call_with_bare}", ", ".join("document.get()" for _ in call_with))
            return text.replace("{call_with_lead}", "".join("document.get(), " for _ in call_with))
        # An enumeration setter names its getter's call in a decltype, which takes the same context.
        body += [with_context(line) for line in prepare]
        expression = with_context(call)
        for index, value in enumerate(passed):
            expression = expression.replace(f"{{arg{index}}}", value)
        if sink is None:
            body.append(f"return invoke([&]() -> decltype(auto) {{ return {expression}; }});")
        elif isinstance(sink, tuple) and sink[0] == 'copyback':
            body += [f"auto status = invoke([&]() -> decltype(auto) {{ return {expression}; }});",
                     "if (status == RV_OK)",
                     f"    copyTypedArrayView(*a{sink[1]}, {sink[2]});",
                     "return status;"]
        elif isinstance(sink, tuple):
            index = sink[1]
            body += [f"auto status = invoke([&]() -> decltype(auto) {{ return {expression}; }});",
                     "if (status == RV_OK)",
                     f"    storeHandle<{'Node' if return_value[1].kind == 'node' else 'Event'}>(a{index}.get(), result);",
                     "return status;"]
        else:
            body.append(f"return deliver([&]() -> decltype(auto) {{ return {expression}; }}, [&](auto&& value) {{ return {sink}; }});")
        function.params = params
        function.body = body
        function.arguments = list(zip(arguments, mapped_args))
        function.returns = returns
        function.conditional = self.conditional(member)
        if function.conditional:
            notes.append(f"RV_ERR_UNSUPPORTED where WebKit builds without {member.attrs['Conditional']}")
        function.comment += "".join(f"; {note}" for note in notes)
        self.functions.append(function)

    def setter_value_checks(self, function, mapped_args):
        if function.kind != 'setter':
            return []
        label = f'{function.interface}.{function.member.name}'
        kind = self.world.config.get('setterValueChecks', {}).get(label)
        if kind is None:
            return []
        mapped = mapped_args[0]
        if kind == 'css-length-or-percentage':
            if mapped.kind != 'object' or mapped.interface != 'CSSNumericValue' or mapped.nullable:
                raise SystemExit(f'{label}: setter check requires CSSNumericValue')
            predicate = 'a0->type().matchesTypeOrPercentage<CSSNumericBaseType::Length>()'
        elif kind == 'css-numberish-number':
            if (mapped.kind != 'union' or mapped.nullable or len(mapped.subtypes) != 2
                    or mapped.subtypes[0].kind != 'number' or mapped.subtypes[0].ctype != 'double'
                    or mapped.subtypes[1].interface != 'CSSNumericValue'):
                raise SystemExit(f'{label}: setter check requires a double/CSSNumericValue union')
            predicate = ('WTF::switchOn(*a0, [](double) { return true; }, '
                         '[](const Ref<CSSNumericValue>& numeric) { return numeric->type().matchesNumber(); })')
        else:
            raise SystemExit(f'{label}: unknown setter check {kind}')
        self.setter_checks_used.add(label)
        return [f'if (!({predicate}))',
                '    return Ranvier::recordException(Exception { ExceptionCode::TypeError, "A compatible numeric value is required."_s });']

    # Output.

    @staticmethod
    def describe_mapping(mapped):
        result = {
            "kind": mapped.kind, "ctype": mapped.ctype, "interface": mapped.interface,
            "root": mapped.root, "class": mapped.cls, "enum": mapped.enum,
            "label": mapped.label, "nullable": mapped.nullable, "atom": mapped.atom,
            "subtypes": [Generator.describe_mapping(child) for child in mapped.subtypes],
        }
        if mapped.kind == 'string' and mapped.string_spans:
            result['stringTransport'] = 'utf8-lengths'
        if mapped.finite_input:
            result['finiteInput'] = True
        return result

    def api_model(self):
        def describe_idl(value):
            value = self.world.resolve(value)
            return {"name": value.name, "nullable": value.nullable,
                    "subtypes": [describe_idl(child) for child in value.subtypes]}

        def argument(member, mapped):
            described = {
                "name": member.name, "idlType": str(member.type), "idl": describe_idl(member.type),
                "optional": member.optional, "default": member.default,
                "variadic": member.variadic, "mapping": self.describe_mapping(mapped),
            }
            # A null value converts to the empty string, where other strings convert it to "null".
            if mapped.kind == "string" and ("LegacyNullToEmptyString" in member.attrs or "LegacyNullToEmptyString" in member.type.attrs):
                described["legacyNullToEmptyString"] = True
            return described

        functions = []
        for function in self.functions:
            if function.unused:
                continue
            functions.append({
                "interface": function.interface, "member": function.member.name,
                "contractOwner": (function.namespace if function.kind == "namespace_operation" else
                                  getattr(function, 'context_owner', 'Window') if function.kind == 'context_operation' else
                                  self.world.contract_owner(function.interface, function.member)),
                "kind": function.kind, "function": "rv_dom_" + function.name,
                "conditional": function.conditional,
                "parameters": [{"ctype": ctype, "name": name} for ctype, name in function.params],
                "arguments": [argument(member, mapped) for member, mapped in function.arguments],
                "returnIdl": describe_idl(idl.Type("undefined") if function.kind == "setter" else
                                          idl.Type(function.interface) if function.kind == "constructor" else function.member.type),
                "returns": self.describe_mapping(function.returns),
            })
            if function.kind == "constructor":
                functions[-1]["receiver"] = self.world.config["constructors"][function.interface]["receiver"]
                functions[-1]["feature"] = f"dom-constructor:{function.interface}"
                functions[-1]['stringInputs'] = 'utf8-lengths'
            if function.kind == "namespace_operation":
                functions[-1].update(receiver=function.receiver, namespace=function.namespace, feature=function.feature,
                                     binding="facade", stringInputs="utf8-lengths")
            if function.kind == 'context_operation':
                functions[-1].update(receiver=function.receiver, context='Window', feature=function.feature,
                                     binding='facade', stringInputs='utf8-lengths-nullable')
            if function.kind == 'static_operation':
                functions[-1].update(receiver=function.receiver, feature=function.feature,
                                     binding='facade', stringInputs='utf8-lengths')
            if function.kind == 'iterator_snapshot':
                functions[-1].update(binding='facade', feature=function.feature, sourceKind='iterable')
            if function.kind in ('operation', 'setter'):
                functions[-1]['stringInputs'] = 'utf8-lengths'
            if getattr(function, 'context_receiver', None):
                functions[-1].update(contextReceiver=function.context_receiver, contextParameter='context')
            bridge = self.world.config.get("attributeBridges", {}).get(f"{function.interface}.{function.member.name}")
            if bridge:
                functions[-1]["binding"] = "facade"
                functions[-1]["feature"] = bridge["feature"]
        model = {
            "schemaVersion": 1,
            "runtimeTypeQueries": self.runtime_queries,
            "interfaces": [{"name": name, "base": self.world.interfaces[name].base}
                           for name in self.world.scope],
            "contractInterfaces": [{"name": self.world.public_name(name), "idlName": name,
                                    "base": self.world.public_name(self.world.interfaces[name].base),
                                    "mixins": [self.world.public_name(mixin) for mixin in self.world.contract_mixins(name)],
                                    "mixin": self.world.interfaces[name].mixin,
                                    "contractOnly": name not in self.world.scope,
                                    "source": self.world.interfaces[name].file}
                                   for name in self.world.contract_types],
            "tagInterfaces": self.world.tag_interfaces,
            "contractDictionaries": {
                name: {"base": self.world.dictionaries[name].base, "contractOnly": name not in self.dicts_used,
                       "omittedFields": sorted(field.split(".", 1)[1] for field in self.world.dictionary_exclusions
                                               if field.startswith(name + ".")),
                       "fields": [{"name": member.name, "required": member.required,
                                   "default": member.default, "idl": describe_idl(member.type),
                                   "mapping": self.describe_mapping(mapped)} for member, mapped in fields]}
                for name, fields in self.world.contract_dictionary_fields.items()},
            "functions": functions,
            "enumerations": self.enums_used,
            "containers": [{"mapping": self.describe_mapping(mapped),
                            "releaseFunction": "rv_dom_" + transport_token(name) + "_release"}
                           for name, mapped in self.complex_used.items()],
            "resultDictionaries": {name: {"struct": struct, "releaseFunction": f"rv_dom_{snake(name)}_release"}
                                   for name, struct in self.result_dicts.items()},
            "dictionaries": {name: [{"name": member.name, "field": c_name(member.name),
                                     "ctype": self.field_ctype(member, mapped, name), "required": member.required,
                                     "default": member.default, "mapping": self.describe_mapping(mapped)}
                                    for member, mapped in fields]
                             for name, fields in self.dicts_used.items()},
        }
        return json.dumps(model, indent=2, ensure_ascii=False) + "\n"

    def header(self):
        lines = [
            "/*",
            " * Ranvier native WebCore C ABI: the generated DOM functions, one per IDL attribute getter, attribute setter",
            " * and operation of the interfaces gen/dom.json lists. Generated by gen/domgen.py from WebKit's IDL files;",
            " * edit gen/dom.json or the generator, then run it. docs/GENERATOR.md describes the conventions:",
            " *",
            " * - Each function returns RV_OK or a negative status and writes its result through the last parameters.",
            " * - target is the object the member belongs to. A node handle of another interface returns",
            " *   RV_ERR_WRONG_INTERFACE, as does a node argument of another interface.",
            " * - String inputs are UTF-8 with an explicit byte count, so a string may hold U+0000: a pointer and a",
            " *   length, -1 for null or absent; RvDomUtf8StringSpan in a union or sequence; RvDomUtf8StringInput in a",
            " *   dictionary, present 0 for the default. String outputs copy into buffer as RanvierWebCoreAbi.h describes.",
            " * - Booleans are int32_t 0 or 1. Any other argument that is nullable or optional without a default is a",
            " *   pointer, NULL for null or absent.",
            " * - Handles out are new references: rv_node_release, rv_event_release, or the rv_dom_*_release of the type.",
            " * - A member that throws returns RV_ERR_DOM_EXCEPTION, with the exception in rv_last_exception.",
            " * - A string union with Trusted Types, such as (TrustedHTML or DOMString), is a string. A dictionary is a",
            " *   pointer to an RvDom<Dictionary> struct whose first field, size, is the struct's sizeof; NULL for an",
            " *   optional dictionary takes the IDL defaults.",
            " * - A member WebKit compiles out on the platform, or whose [EnabledBySetting] setting is off, returns",
            " *   RV_ERR_UNSUPPORTED. So does a stub: a function this header had for a member WebKit's IDL no longer has.",
            " * - rv_abi_has(\"dom-generated\") is 1 when the library has these functions, and rv_abi_has(\"dom:<Interface>\")",
            " *   when it has those of an interface.",
            " */",
            "#pragma once",
            "",
            '#include "RanvierWebCoreAbi.h"',
            "",
            "#ifdef __cplusplus",
            'extern "C" {',
            "#endif",
            "",
        ]
        for name in self.handles:
            if name not in self.world.config.get('callbackObjectRoots', {}):  # declared by RanvierWebCoreAbi.h
                lines.append(f"typedef struct Rv{name} Rv{name};")
        lines += [f"typedef struct {name} {name};" for name in self.complex_used]
        lines.append("")
        if self.constants:
            lines.append("/* Constants of the interfaces. */")
            lines.append("enum {")
            for macro, value, comment in self.constants:
                if int(value, 0) <= 0x7FFFFFFF:
                    lines.append(f"    {macro} = {value}, /* {comment} */")
            lines.append("};")
            lines.append("")
            wide = [(macro, value, comment) for macro, value, comment in self.constants if int(value, 0) > 0x7FFFFFFF]
            for macro, value, comment in wide:
                lines.append(f"#define {macro} {value}u /* {comment} */")
            if wide:
                lines.append("")
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            lines.append(f"/* The values of the IDL enumeration {enum}. */")
            lines.append("enum {")
            for index, value in enumerate(values):
                lines.append(f"    RV_DOM_{snake(enum).upper()}_{re.sub(r'[^A-Za-z0-9]+', '_', value).upper() or 'EMPTY'} = {index}, /* \"{value}\" */")
            lines.append("};")
            lines.append("")
        if self.uses_dictionary_string_spans():
            lines += ["/* A present UTF-8 dictionary string; length is a byte count and may include NUL. */",
                      "typedef struct RvDomUtf8StringInput {", "    int32_t present;",
                      "    const uint8_t* data;", "    int32_t length;", "} RvDomUtf8StringInput;", ""]
        for name, fields in self.dicts_used.items():
            struct = f"RvDom{name}"
            lines.append(f"/* The IDL dictionary {name}. size is sizeof({struct}) as the caller compiles it; a field past")
            if name in self.result_dicts:
                lines.append(" * size takes its IDL default, so fields can be added at the end. As a result, the glue allocates it,")
                lines.append(f" * sets size, owns every field and nested value, and rv_dom_{snake(name)}_release frees it. */")
            else:
                lines.append(" * size takes its IDL default, so fields can be added at the end. */")
            lines.append(f"typedef struct {struct} {{")
            lines.append("    uint32_t size;")
            for member, mapped in fields:
                ctype = self.field_ctype(member, mapped, name)
                note = f"{member.type}"
                if member.required:
                    note += ", required"
                elif member.default is not None:
                    note += f", default {member.default}"
                elif ctype.endswith("*"):
                    note += ", NULL for absent"
                if mapped.kind == "enum":
                    note += f", RV_DOM_{snake(mapped.enum).upper()}_*"
                lines.append(f"    {ctype} {c_name(member.name)}; /* {note} */")
            lines.append(f"}} {struct};")
            lines.append("")
        lines += self.transport_structs()
        lines += self.complex_release_declarations("rv_dom_", "RV_EXPORT")
        for name, struct in self.result_dicts.items():
            lines.append(f"/* Releases an owned {name} result, its strings and nested values, and the struct. */")
            lines.append(f"RV_EXPORT void rv_dom_{snake(name)}_release({struct}* value);")
        for name in self.handles:
            lines.append(f"/* Releases a handle to a {name}. */")
            lines.append(f"RV_EXPORT void rv_dom_{snake(name)}_release(Rv{name}*);")
            lines.append(f"/* Adds a reference to a {name} and returns it. */")
            lines.append(f"RV_EXPORT Rv{name}* rv_dom_{snake(name)}_retain(Rv{name}*);")
        for query in self.runtime_queries:
            parameters = [(row['ctype'], row['name']) for row in query['parameters']]
            if query['names'] != query['interfaces']:
                lines.append(f"/* The exposed interface name of a {query['root']}, or of its nearest generated base; borrows target. */")
            else:
                lines.append(f"/* Concrete scoped interface name of a {query['root']} handle; borrows target. */")
            lines.append(f"RV_EXPORT int32_t {query['function']}({params_text(parameters)});")
        lines.append("")
        current = None
        for function in self.functions:
            if function.interface != current:
                current = function.interface
                lines += [f"/* {current} */", ""]
            lines.append(wrap_comment(function.comment))
            lines.append(f"RV_EXPORT int32_t rv_dom_{function.name}({params_text(function.params)});")
        lines += ["", "#ifdef __cplusplus", "}", "#endif", ""]
        return "\n".join(lines)

    def glue_header(self):
        lines = [
            "// The DOM functions WebCore exports for RanvierWebCoreHost, which re-exports each under its rv_dom_ name",
            "// (host/RanvierWebCoreDom.cpp). Generated by gen/domgen.py; do not edit.",
            "#pragma once",
            "",
            '#include "../RanvierWebCoreDom.h"',
            "#include <WebCore/ExceptionCode.h>",
            "#include <optional>",
            "#include <wtf/text/WTFString.h>",
            "",
            "namespace WebCore {",
            "class Exception;",
            "}",
            "",
            "// The latest DOM exception of a call on the owning thread, from the host's functions or these, which",
            "// rv_last_exception reports.",
            "namespace Ranvier {",
            "// Stores the exception and returns RV_ERR_DOM_EXCEPTION.",
            "WEBCORE_EXPORT int32_t recordException(const WebCore::Exception&);",
            "WEBCORE_EXPORT std::optional<WebCore::ExceptionCode> lastExceptionCode();",
            "WEBCORE_EXPORT String lastExceptionMessage();",
            "}",
            "",
            'extern "C" {',
            "",
            "// 1 for \"dom-generated\" and for \"dom:<Interface>\" of each generated interface, else 0.",
            "WEBCORE_EXPORT int32_t ranvier_dom_has(const char* feature);",
        ]
        for name in self.handles:
            lines.append(f"WEBCORE_EXPORT void ranvier_dom_{snake(name)}_release(Rv{name}*);")
            lines.append(f"WEBCORE_EXPORT Rv{name}* ranvier_dom_{snake(name)}_retain(Rv{name}*);")
        lines += self.complex_release_declarations("ranvier_dom_", "WEBCORE_EXPORT")
        for name, struct in self.result_dicts.items():
            lines.append(f"WEBCORE_EXPORT void ranvier_dom_{snake(name)}_release({struct}* value);")
        for query in self.runtime_queries:
            parameters = [(row['ctype'], row['name']) for row in query['parameters']]
            name = query['function'].replace('rv_dom_', 'ranvier_dom_', 1)
            lines.append(f"WEBCORE_EXPORT int32_t {name}({params_text(parameters)});")
        for function in self.functions:
            lines.append(f"WEBCORE_EXPORT int32_t ranvier_dom_{function.name}({params_text(function.params)});")
        lines += ["", "}", ""]
        return "\n".join(lines)

    def host(self):
        lines = [
            "// The rv_dom_* functions of RanvierWebCoreDom.h: each calls its twin in WebCore, where the generated glue",
            "// reaches members WebCore does not export. Generated by gen/domgen.py; do not edit.",
            '#include "config.h"',
            '#include "RanvierWebCoreDom.h"',
            '#include "dom/RanvierDomGlue.h"',
            "",
        ]
        for name in self.handles:
            lines.append(f"void rv_dom_{snake(name)}_release(Rv{name}* handle) {{ ranvier_dom_{snake(name)}_release(handle); }}")
            lines.append(f"Rv{name}* rv_dom_{snake(name)}_retain(Rv{name}* handle) {{ return ranvier_dom_{snake(name)}_retain(handle); }}")
        for name in self.complex_used:
            lines.append(f"void rv_dom_{transport_token(name)}_release({name}* value) {{ ranvier_dom_{transport_token(name)}_release(value); }}")
        for name, struct in self.result_dicts.items():
            lines.append(f"void rv_dom_{snake(name)}_release({struct}* value) {{ ranvier_dom_{snake(name)}_release(value); }}")
        for query in self.runtime_queries:
            parameters = [(row['ctype'], row['name']) for row in query['parameters']]
            name = query['function']
            twin = name.replace('rv_dom_', 'ranvier_dom_', 1)
            lines.append(f"int32_t {name}({params_text(parameters)}) {{ return {twin}(target, buffer, capacity, length); }}")
        for function in self.functions:
            args = ", ".join(n for _, n in function.params)
            lines.append(f"int32_t rv_dom_{function.name}({params_text(function.params)}) {{ return ranvier_dom_{function.name}({args}); }}")
        return "\n".join(lines) + "\n"

    def glue(self):
        lines = [
            "// The glue of the generated DOM functions, compiled into WebCore by patch 0012 (config/common.cmake names this",
            "// file). Each function checks its arguments and thread, calls the member as WebKit's JavaScript bindings call",
            "// it, and converts the result. Generated by gen/domgen.py from WebKit's IDL files; do not edit.",
            '#include "config.h"',
            '#include "RanvierDomGlue.h"',
            "",
        ]
        lines += [f'#include "{h}"' for h in sorted({self.interface_headers.get(header, header) for header in self.headers})]
        for enum, (_, _, file) in sorted(self.enums_used.items()):
            lines.append(f'#include "JS{pathlib.PurePosixPath(file).stem}.h"')
        lines += ["", RUNTIME, ""]
        lines += self.tracked_handle_runtime()
        lines += self.const_getter_runtime()
        lines += self.typed_array_view_runtime()
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            quoted = ", ".join(f'"{v}"_s' for v in values)
            lines.append(f"static constexpr ASCIILiteral {enum_table(enum)}[] = {{ {quoted} }};")
        lines += self.complex_runtime()
        lines += ["", "using namespace WebCore;", "", 'extern "C" {', ""]
        lines.append("int32_t ranvier_dom_has(const char* feature)")
        lines.append("{")
        lines.append("    if (!feature)")
        lines.append("        return 0;")
        groups = ["dom-generated"] + [f"dom:{name}" for name in self.world.scope] + [query['feature'] for query in self.runtime_queries]
        groups += [f"dom-constructor:{function.interface}" for function in self.functions if function.kind == "constructor"]
        for label, bridge in self.world.config.get("attributeBridges", {}).items():
            kinds = {function.kind for function in self.functions
                     if f"{function.interface}.{function.member.name if function.member else ''}" == label}
            if {"getter", "setter"}.issubset(kinds):
                groups.append(bridge["feature"])
        lines.append("    for (auto* name : { " + ", ".join(f'"{g}"' for g in groups) + " }) {")
        lines.append("        if (!std::strcmp(feature, name))")
        lines.append("            return 1;")
        lines.append("    }")
        for feature, conditions in self.namespace_features:
            if conditions:
                lines.append("#if " + " && ".join(f"({condition})" for condition in sorted(set(conditions))))
            lines += [f'    if (!std::strcmp(feature, "{feature}"))', "        return 1;"]
            if conditions:
                lines.append("#endif")
        lines.append("    return 0;")
        lines.append("}")
        lines.append("")
        for name in self.complex_used:
            lines += [f"void ranvier_dom_{transport_token(name)}_release({name}* value)", "{",
                      f"    if (isMainThread()) clear{name}(value);", "}", ""]
        for name, struct in self.result_dicts.items():
            lines += [f"void ranvier_dom_{snake(name)}_release({struct}* value)", "{",
                      f"    if (isMainThread()) releaseDict{struct}(value);", "}", ""]
        for name in self.handles:
            cls = self.world.cpp_class(name)
            release = (f'releaseTrackedHandle(reinterpret_cast<{cls}*>(handle));' if cls in self.tracked_roots
                       else f'reinterpret_cast<{cls}*>(handle)->deref();')
            retain = (f'retainTrackedHandle(reinterpret_cast<{cls}*>(handle));' if cls in self.tracked_roots
                      else f'reinterpret_cast<{cls}*>(handle)->ref();')
            lines += [
                f"void ranvier_dom_{snake(name)}_release(Rv{name}* handle)",
                "{",
                "    if (handle && isMainThread())",
                f"        {release}",
                "}",
                "",
                f"Rv{name}* ranvier_dom_{snake(name)}_retain(Rv{name}* handle)",
                "{",
                "    if (!handle || !isMainThread())",
                "        return nullptr;",
                f"    {retain}",
                "    return handle;",
                "}",
                "",
            ]
        for function in self.functions:
            lines.append(f"// {function.comment}")
            lines.append(f"int32_t ranvier_dom_{function.name}({params_text(function.params)})")
            lines.append("{")
            if function.unused:
                lines += [f"    UNUSED_PARAM({n});" for _, n in function.params]
            if function.conditional:
                lines.append(f"#if {function.conditional}")
            lines += ["    " + line if line else "" for line in function.body]
            if function.conditional:
                lines.append("#else")
                lines += [f"    UNUSED_PARAM({n});" for _, n in function.params]
                lines.append("    return RV_ERR_UNSUPPORTED;")
                lines.append("#endif")
            lines.append("}")
            lines.append("")
        for query in self.runtime_queries:
            parameters = [(row['ctype'], row['name']) for row in query['parameters']]
            name = query['function'].replace('rv_dom_', 'ranvier_dom_', 1)
            root = query['root']
            lines += [f"int32_t {name}({params_text(parameters)})", "{",
                      "    if (!target || !length)", "        return RV_ERR_NULL_ARGUMENT;",
                      "    if (!isMainThread())", "        return RV_ERR_WRONG_THREAD;",
                      f"    auto* impl = reinterpret_cast<{self.world.cpp_class(root)}*>(target);"]
            for interface, exposed in zip(query['interfaces'][:-1], query['names']):
                conditional = self.conditional(self.world.interfaces[interface])
                if conditional:
                    lines.append(f"#if {conditional}")
                cast = self.cast_expression(self.world.cpp_class(interface), self.world.cpp_class(root), "*impl")
                lines += [f"    if ({cast})", f'        return copyString("{exposed}"_s, buffer, capacity, length);']
                if conditional:
                    lines.append("#endif")
            lines += [f'    return copyString("{query["names"][-1]}"_s, buffer, capacity, length);', "}", ""]
        lines += ["} // extern \"C\"", ""]
        return "\n".join(lines)

    def const_getter_runtime(self):
        if not self.const_getters_used:
            return []
        return [r'''
namespace {
template<typename Root, typename Declared, typename Handle, typename V>
int32_t storeConstGetter(V&& value, Handle** result)
{
    static_assert(std::is_lvalue_reference_v<V> && std::is_const_v<std::remove_reference_t<V>>);
    static_assert(std::is_same_v<std::remove_cvref_t<V>, Declared>);
    static_assert(std::is_polymorphic_v<Root>);
    auto* pointer = static_cast<Root*>(const_cast<Declared*>(&value));
    pointer->ref();
    *result = reinterpret_cast<Handle*>(pointer);
    return RV_OK;
}
} // namespace
''']

    def tracked_handle_runtime(self):
        if not self.tracked_roots:
            return []
        lines = ['#include <unordered_map>', 'namespace {',
                 'template<typename Root> struct TrackedHandleTraits;']
        for root, concrete in self.tracked_roots.items():
            lines.append(f'template<> struct TrackedHandleTraits<{root}> {{ using Mutable = {concrete}; }};')
        lines.append(r'''
// Metadata owns no engine references. Entries count only references exported through this ABI.
struct TrackedHandleState {
    size_t references { 0 };
    bool mutableType { false };
};

template<typename Root> auto& trackedHandles()
{
    static std::unordered_map<const Root*, TrackedHandleState> handles;
    return handles;
}

template<typename Root, typename Concrete, typename Handle, typename V>
int32_t storeTrackedHandle(V&& value, Handle** result)
{
    using Mutable = typename TrackedHandleTraits<Root>::Mutable;
    static_assert(std::is_same_v<Concrete, Root> || std::is_same_v<Concrete, Mutable>);
    const Concrete* concrete = rawPointer<const Concrete>(std::forward<V>(value));
    auto* pointer = const_cast<Root*>(static_cast<const Root*>(concrete));
    if (pointer) {
        pointer->ref();
        auto& state = trackedHandles<Root>()[pointer];
        ++state.references;
        state.mutableType |= std::is_same_v<Concrete, Mutable>;
    }
    *result = reinterpret_cast<Handle*>(pointer);
    return RV_OK;
}

template<typename Root> void retainTrackedHandle(Root* pointer)
{
    pointer->ref();
    ++trackedHandles<Root>()[pointer].references;
}

template<typename Root> void releaseTrackedHandle(Root* pointer)
{
    auto& handles = trackedHandles<Root>();
    auto found = handles.find(pointer);
    if (found != handles.end()) {
        if (!--found->second.references)
            handles.erase(found);
    }
    pointer->deref();
}

template<typename Concrete, typename Root> Concrete* castTrackedHandle(Root& value)
{
    static_assert(std::is_same_v<Concrete, typename TrackedHandleTraits<Root>::Mutable>);
    auto& handles = trackedHandles<Root>();
    auto found = handles.find(&value);
    return found != handles.end() && found->second.mutableType ? static_cast<Concrete*>(&value) : nullptr;
}
} // namespace
''')
        return lines

    def interfaces(self):
        from interfaces import emit_interfaces
        return emit_interfaces(self)

    def fsharp(self):
        lines = [
            "/// P/Invoke declarations of host/RanvierWebCoreDom.h, the generated DOM functions. Generated by gen/domgen.py;",
            "/// do not edit.",
            "module RanvierWebCoreAbi.NativeDom",
            "",
            "open System.Runtime.InteropServices",
            "",
            "[<Literal>]",
            'let private Lib = "RanvierWebCoreHost"',
            "",
            "/// <summary>RV_ERR_WRONG_INTERFACE: a handle's object does not implement the member's interface.</summary>",
            "[<Literal>]",
            "let WrongInterface = -11",
        ]
        for macro, value, _ in self.constants:
            lines += ["", "[<Literal>]", f"let {macro} = {int(value, 0)}{'u' if int(value, 0) > 0x7FFFFFFF else ''}"]
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            for index, value in enumerate(values):
                macro = f"RV_DOM_{snake(enum).upper()}_{re.sub(r'[^A-Za-z0-9]+', '_', value).upper() or 'EMPTY'}"
                lines += ["", "[<Literal>]", f"let {macro} = {index}"]
        if self.uses_dictionary_string_spans():
            lines += ["", "/// <summary>A present UTF-8 dictionary string with an explicit byte count.</summary>",
                      "[<Struct; StructLayout(LayoutKind.Sequential)>]", "type RvDomUtf8StringInput =",
                      "    val mutable present: int32", "    val mutable data: nativeint", "    val mutable length: int32"]
        for name, fields in self.dicts_used.items():
            lines += ["", f"/// <summary>The IDL dictionary {name}; set <c>size</c> to <c>Marshal.SizeOf</c> of the struct.</summary>",
                      "[<Struct; StructLayout(LayoutKind.Sequential)>]", f"type RvDom{name} =", "    val mutable size: uint32"]
            for member, mapped in fields:
                ctype = self.field_ctype(member, mapped, name)
                field = c_name(member.name)
                field = f"``{field}``" if field in FSHARP_KEYWORDS else field
                if ctype.endswith("*"):
                    lines.append(f"    val mutable {field}: nativeint")
                elif ctype == "RvDomUtf8StringInput":
                    lines.append(f"    val mutable {field}: RvDomUtf8StringInput")
                else:
                    lines.append(f"    val mutable {field}: {FSHARP_NUMBERS[ctype]}")
        lines += self.complex_fsharp()
        for name in self.result_dicts:
            lines += ["", "[<DllImport(Lib)>]", f"extern void rv_dom_{snake(name)}_release(nativeint value)"]
        for name in self.handles:
            lines += ["", "[<DllImport(Lib)>]", f"extern void rv_dom_{snake(name)}_release(nativeint handle)"]
            lines += ["", "[<DllImport(Lib)>]", f"extern nativeint rv_dom_{snake(name)}_retain(nativeint handle)"]
        for query in self.runtime_queries:
            rendered = [fsharp_param(row['ctype'], row['name']) for row in query['parameters']]
            lines += ["", "[<DllImport(Lib)>]", f"extern int {query['function']}({', '.join(rendered)})"]
        for function in self.functions:
            rendered = []
            for ctype, name in function.params:
                rendered.append(fsharp_param(ctype, name))
            lines += ["", "[<DllImport(Lib)>]", f"extern int rv_dom_{function.name}({', '.join(rendered)})"]
        return "\n".join(lines) + "\n"

    def report(self):
        interfaces = sorted({f.interface for f in self.functions})
        lines = [
            "Generated by gen/domgen.py: the members of gen/dom.json's interfaces, and those left out with the reason.",
            "",
            f"interfaces {len(self.world.scope)}, functions {len(self.functions)} "
            f"(getters {sum(f.kind == 'getter' for f in self.functions)}, setters {sum(f.kind == 'setter' for f in self.functions)}, "
            f"operations {sum(f.kind == 'operation' for f in self.functions)}, "
            f"constructors {sum(f.kind == 'constructor' for f in self.functions)}, "
            f"namespace operations {sum(f.kind == 'namespace_operation' for f in self.functions)}, "
            f"static operations {sum(f.kind == 'static_operation' for f in self.functions)}, "
            f"iterator snapshots {sum(f.kind == 'iterator_snapshot' for f in self.functions)}, "
            f"context operations {sum(f.kind == 'context_operation' for f in self.functions)}), handle types {len(self.handles)}, "
            f"constants {len(self.constants)}, enumerations {len(self.enums_used)}, dictionaries {len(self.dicts_used)}, "
            f"stubs {len(self.stubs)}, left out {len(self.excluded)}",
            f"Runtime type queries: {len(self.runtime_queries)} (separate from the IDL member count)",
            "",
            "Functions per interface:",
        ]
        for name in self.world.scope:
            lines.append(f"  {name}: {sum(f.interface == name for f in self.functions)}")
        for name in self.world.config.get("namespaceBindings", {}):
            lines.append(f"  namespace {name}: {sum(f.interface == name for f in self.functions)}")
        lines += ["", "Stubs, for members of the lock that WebKit's IDL no longer has:"]
        lines += [f"  rv_dom_{f.name}" for f in self.stubs] or ["  (none)"]
        lines += ["", "Left out:"]
        for label, reason in sorted(self.excluded + [(name, "excluded dictionary field by gen/dom.json") for name in self.world.dictionary_exclusions]):
            lines.append(f"  {label}: {reason}")
        lines += ["", "Contract-only interfaces (own members have no native exports):"]
        for name in self.world.contract_types:
            if name in self.world.scope or self.world.interfaces[name].mixin or name == "EventTarget":
                continue
            lines.append(f"  {self.world.public_name(name)}: {self.world.interfaces[name].file}")
            for member in self.world.interfaces[name].members:
                label = member.name or member.special or member.kind
                lines.append(f"    {name}.{label}: contract-only interface; member omitted")
        lines += ["", "Contract mixins (only members mapped by scoped concrete interfaces are declared):"]
        for name in self.world.contract_types:
            if not self.world.interfaces[name].mixin:
                continue
            public = self.world.public_name(name)
            mapped = {self.world.member_key(function.member) for function in self.functions
                      if function.member and self.world.contract_owner(function.interface, function.member) == public}
            lines.append(f"  {public}: {self.world.interfaces[name].file}")
            for member in self.world.members(name):
                if self.world.member_key(member) not in mapped:
                    label = member.name or member.special or member.kind
                    lines.append(f"    {public}.{label}: no scoped concrete native export; member omitted")
        del interfaces
        return "\n".join(lines) + "\n"


RUNTIME = r"""#include <cmath>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <optional>
#include <type_traits>
#include <variant>
#include <wtf/FixedVector.h>
#include <wtf/MainThread.h>

namespace Ranvier {

static std::optional<WebCore::ExceptionCode> latestCode;
static String latestMessage;

int32_t recordException(const WebCore::Exception& exception)
{
    latestCode = exception.code();
    latestMessage = exception.message();
    return RV_ERR_DOM_EXCEPTION;
}

std::optional<WebCore::ExceptionCode> lastExceptionCode() { return latestCode; }
String lastExceptionMessage() { return latestMessage; }

} // namespace Ranvier

namespace {

using namespace WebCore;

Node* nodeOf(RvNode* handle) { return reinterpret_cast<Node*>(handle); }
Event* eventOf(RvEvent* handle) { return reinterpret_cast<Event*>(handle); }

template<typename> struct IsExceptionOr : std::false_type { };
template<typename T> struct IsExceptionOr<ExceptionOr<T>> : std::true_type { };
template<typename> struct IsOptional : std::false_type { };
template<typename T> struct IsOptional<std::optional<T>> : std::true_type { };
template<typename> struct IsRef : std::false_type { };
template<typename T, typename... A> struct IsRef<Ref<T, A...>> : std::true_type { };
template<typename> struct IsRefPtr : std::false_type { };
template<typename T, typename... A> struct IsRefPtr<RefPtr<T, A...>> : std::true_type { };

// Runs a call whose C++ result is discarded: void, or ExceptionOr<void>, or a value.
template<typename Call> int32_t invoke(Call&& call)
{
    using Result = std::remove_cvref_t<decltype(call())>;
    if constexpr (IsExceptionOr<Result>::value) {
        auto result = call();
        if (result.hasException())
            return Ranvier::recordException(result.releaseException());
        return RV_OK;
    } else if constexpr (std::is_void_v<Result>) {
        call();
        return RV_OK;
    } else {
        call();
        return RV_OK;
    }
}

// Runs a call and passes its value, unwrapped from ExceptionOr, to sink.
template<typename Call, typename Sink> int32_t deliver(Call&& call, Sink&& sink)
{
    using Result = std::remove_cvref_t<decltype(call())>;
    if constexpr (IsExceptionOr<Result>::value) {
        auto result = call();
        if (result.hasException())
            return Ranvier::recordException(result.releaseException());
        return sink(result.releaseReturnValue());
    } else
        return sink(call());
}

int32_t copyString(const String& value, char* buffer, int32_t capacity, int32_t* length)
{
    if (value.isNull()) {
        *length = -1;
        return RV_OK;
    }
    auto bytes = value.utf8();
    *length = static_cast<int32_t>(bytes.length());
    if (!buffer || capacity < *length)
        return RV_ERR_BUFFER_TOO_SMALL;
    std::memcpy(buffer, bytes.data(), bytes.length());
    return RV_OK;
}

int32_t copyRequiredString(const String& value, char* buffer, int32_t capacity, int32_t* length)
{
    return copyString(value.isNull() ? emptyString() : value, buffer, capacity, length);
}

template<typename V> String asString(const V& value)
{
    if constexpr (IsOptional<V>::value)
        return value ? asString(*value) : String { };
    else if constexpr (std::is_convertible_v<const V&, const String&>)
        return value;
    else if constexpr (std::is_convertible_v<const V&, String>)
        return String { value };
    else
        return value.string();
}

template<typename C, typename V> int32_t store(const V& value, C* result)
{
    *result = static_cast<C>(value);
    return RV_OK;
}

template<typename C, typename V> int32_t storeOptional(const V& value, C* result, int32_t* present)
{
    if constexpr (IsOptional<V>::value) {
        *present = value ? 1 : 0;
        if (value)
            *result = static_cast<C>(*value);
    } else {
        *present = 1;
        *result = static_cast<C>(value);
    }
    return RV_OK;
}

template<typename E, size_t N> int32_t storeEnumeration(E value, int32_t* result, const ASCIILiteral (&names)[N])
{
    auto text = convertEnumerationToString(value);
    for (size_t index = 0; index < N; ++index) {
        if (text == names[index]) {
            *result = static_cast<int32_t>(index);
            return RV_OK;
        }
    }
    return RV_ERR_UNSUPPORTED;
}

template<typename E, size_t N> std::optional<E> enumerationFromIndex(int32_t index, const ASCIILiteral (&names)[N])
{
    if (index < 0 || static_cast<size_t>(index) >= N)
        return std::nullopt;
    return parseEnumerationFromString<E>(String { names[index] });
}

template<typename T> struct Unwrapped { using Type = T; };
template<typename T> struct Unwrapped<std::optional<T>> { using Type = T; };

// Copies a dictionary field into the C++ dictionary's member, which may be optional.
template<typename T, typename V> void assignValue(T& field, V value)
{
    field = static_cast<typename Unwrapped<T>::Type>(value);
}

template<typename T> bool assignString(T& field, const uint8_t* text, int32_t length)
{
    String value = length ? String::fromUTF8(std::span<const uint8_t> { text, static_cast<size_t>(length) }) : emptyString();
    if (value.isNull())
        return false;
    using Type = typename Unwrapped<T>::Type;
    if constexpr (std::is_same_v<Type, AtomString>)
        field = AtomString { value };
    else
        field = Type { value };
    return true;
}

template<typename T, size_t N> bool assignEnumeration(T& field, int32_t index, const ASCIILiteral (&names)[N])
{
    auto value = enumerationFromIndex<typename Unwrapped<T>::Type>(index, names);
    if (!value)
        return false;
    field = *value;
    return true;
}

// The raw pointer of a pointer, reference, Ref or RefPtr result.
template<typename Root, typename V> Root* rawPointer(V&& value)
{
    using T = std::remove_cvref_t<V>;
    if constexpr (std::is_pointer_v<T>)
        return value;
    else if constexpr (IsRef<T>::value)
        return value.ptr();
    else if constexpr (IsRefPtr<T>::value)
        return value.get();
    else
        return &value;
}

template<typename Root, typename Handle, typename V> int32_t storeHandle(V&& value, Handle** result)
{
    Root* pointer = rawPointer<Root>(std::forward<V>(value));
    if (pointer)
        pointer->ref();
    *result = reinterpret_cast<Handle*>(pointer);
    return RV_OK;
}

int32_t storeNode(Node* pointer, RvNode** result)
{
    if (pointer)
        pointer->ref();
    *result = reinterpret_cast<RvNode*>(pointer);
    return RV_OK;
}

// A UTF-8 argument and its byte count, which converts to the string type the member takes. Length -1 is the null
// string, or an absent optional string.
struct StringArg {
    StringArg(const uint8_t* text, int32_t length)
        : value(length < 0 ? String() : length ? String::fromUTF8(std::span<const uint8_t> { text, static_cast<size_t>(length) }) : emptyString())
    {
    }
    operator String() const { return value; }
    operator AtomString() const { return AtomString { value }; }
    operator std::optional<String>() const { return value.isNull() ? std::nullopt : std::optional<String> { value }; }
    operator std::optional<AtomString>() const { return value.isNull() ? std::nullopt : std::optional<AtomString> { AtomString { value } }; }
    AtomString atom() const { return AtomString { value }; }
    String string() const { return value; }
    String value;
};

// A nullable or optional scalar argument: NULL is null or absent.
template<typename C> struct OptionalArg {
    const C* pointer;
    template<typename U> operator std::optional<U>() const { return pointer ? std::optional<U> { static_cast<U>(*pointer) } : std::nullopt; }
};

// A handle argument, which converts to the reference, pointer, Ref or RefPtr the member takes.
template<typename T> struct HandleArg {
    T* pointer;
    operator T&() const { return *pointer; }
    operator T*() const { return pointer; }
    operator Ref<T>() const { return *pointer; }
    operator RefPtr<T>() const { return pointer; }
};

} // namespace"""


def to_method_name(name):
    """CodeGeneratorJS.pm's ToMethodName: a setting's accessor on SettingsValues."""
    if name.startswith("CSSOM"):
        return name
    result = name[:1].lower() + name[1:]
    for prefix, lower in (("cSS", "css"), ("dOM", "dom"), ("hTML", "html"), ("hDR", "hdr"), ("jS", "js"), ("uRL", "url"),
                          ("xML", "xml"), ("xSLT", "xslt")):
        if result.startswith(prefix):
            result = lower + result[len(prefix):]
    return result


def read_lock(path):
    """The committed header's functions, as name -> {params, comment}, and its dictionary structs, as struct name ->
    [field names]: the lock that keeps the ABI's functions and field order as WebKit changes."""
    if not path.exists():
        return {}, {}
    text = path.read_text(encoding="utf-8")
    functions = {}
    for match in re.finditer(r"(/\*(?:(?!\*/).)*\*/)\nRV_EXPORT int32_t rv_dom_(\w+)\((.*?)\);", text, re.S):
        comment = " ".join(re.sub(r"^(/\*|\*/|\*)|\*/$", "", line.strip()) for line in match.group(1).splitlines())
        comment = " ".join(comment.split())
        params = []
        for part in match.group(3).split(", "):
            ctype, name = part.rsplit(" ", 1)
            params.append((ctype, name))
        functions[match.group(2)] = {"params": params, "comment": comment}
    structs = {}
    for match in re.finditer(r"typedef struct (RvDom\w+) \{(.*?)\} \1;", text, re.S):
        names = re.findall(r"^\s+[^;/]*?(\w+);", match.group(2), re.M)
        structs[match.group(1)] = [n for n in names if n != "size"]
    return functions, structs


def enum_table(name):
    return f"enumeration{name}"


def params_text(params):
    return ", ".join(f"{ctype} {name}" for ctype, name in params)


def wrap_comment(text, width=118):
    words = text.split(" ")
    lines, current = [], "/*"
    for word in words:
        if len(current) + 1 + len(word) > width:
            lines.append(current)
            current = " *"
        current += " " + word
    lines.append(current + " */")
    return "\n".join(lines)


def fsharp_param(ctype, name):
    fname = f"``{name}``" if name in FSHARP_KEYWORDS else name
    if ctype in ("char*", "uint8_t*"):
        return f"byte[] {fname}"
    if ctype == "int32_t*" and name == "length":
        return f"int[] {fname}"
    if ctype.startswith("const RvDom") and ctype.endswith("*"):
        return f"[<In>] {ctype[6:-1]}[] {fname}"
    if ctype.startswith("const ") and ctype.endswith("*"):
        return f"{FSHARP_NUMBERS[ctype[6:-1]]}[] {fname}"
    if ctype.endswith("**"):
        return f"nativeint& {fname}"
    if ctype.startswith("Rv") and ctype.endswith("*"):
        if ctype.startswith(("RvDomUnion", "RvDomSequence")):
            return f"{ctype[:-1]}& {fname}"
        return f"nativeint {fname}"
    if ctype.endswith("*"):
        return f"{FSHARP_NUMBERS[ctype[:-1]]}& {fname}"
    return f"{FSHARP_NUMBERS[ctype]} {fname}"


def outputs(generator):
    return {
        OUT_HEADER: generator.header(),
        OUT_HOST: generator.host(),
        OUT_GLUE_HEADER: generator.glue_header(),
        OUT_GLUE: generator.glue(),
        OUT_FSHARP: generator.fsharp(),
        OUT_REPORT: generator.report(),
        ROOT / "gen" / "Ranvier.Dom.fs": generator.interfaces(),
        ROOT / "gen" / "dom-api.json": generator.api_model(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["write", "check"])
    parser.add_argument("--source", required=True, help="the WebKit checkout")
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    world = World(pathlib.Path(args.source), config)
    generator = Generator(world)
    generator.run()
    files = outputs(generator)
    differ = 0
    for path, text in files.items():
        if args.mode == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            print(f"differs from the generator's output: {path.relative_to(ROOT).as_posix()}")
            differ += 1
    print(generator.report().splitlines()[2])
    for stub in generator.stubs:
        print(f"stub: rv_dom_{stub.name} ({stub.comment.split(' ', 1)[0]} is gone from WebKit's IDL)")
    for name in generator.changed:
        print(f"signature changed against the committed header: rv_dom_{name}")
    if args.mode == "check" and differ:
        print("run: python -I gen/domgen.py write --source <webkit>")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
