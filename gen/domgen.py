"""Generates the per-member DOM C ABI from WebKit's IDL files: one C function per IDL attribute getter, attribute
setter and operation of the interfaces gen/dom.json lists. docs/GENERATOR.md describes the design.

Usage:
  python -I gen/domgen.py write --source <webkit>   writes the files below from the checkout's IDL files
  python -I gen/domgen.py check --source <webkit>   exits 1 when a file below differs from what write would write

Outputs:
  host/RanvierWebCoreDom.h        the public C header: handle types, constants and the rv_dom_* functions
  host/RanvierWebCoreDom.cpp      the host's rv_dom_* functions, each calling its ranvier_dom_* twin in WebCore
  host/dom/RanvierDomGlue.h       the ranvier_dom_* functions WebCore exports, for the host
  host/dom/RanvierDomGlue.cpp     their definitions, compiled into WebCore by patch 0011
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
              "delete", "class", "template", "this", "namespace", "operator", "private", "public", "protected"}
# The names generated functions give their own parameters, which an IDL argument does not take.
RESERVED = {"target", "buffer", "capacity", "length", "result", "present"}
# Extended attributes of a member that the generator does not map.
UNMAPPED = ["Custom", "EnabledForWorld", "EnabledByQuirk", "ForwardToMapLike", "ForwardToSetLike", "CustomBinding",
            "PrivateIdentifier", "LegacyFactoryFunction"]
# CallWith values the glue supplies from the node's document.
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

    def __init__(self, kind, nullable=False, ctype=None, interface=None, root=None, cls=None, enum=None):
        self.kind = kind  # string, bool, number, enum, node, event, object, void
        self.nullable = nullable
        self.ctype = ctype
        self.interface = interface
        self.root = root  # the handle struct's interface for object handles
        self.cls = cls  # the C++ class
        self.enum = enum

    @property
    def handle(self):
        return {"node": "RvNode", "event": "RvEvent"}.get(self.kind) or f"Rv{self.root}"


class Unsupported(Exception):
    pass


class World:
    def __init__(self, source: pathlib.Path, config: dict):
        self.webcore = source / "Source" / "WebCore"
        self.config = config
        self.skip = config["skipDirectories"]
        self.interfaces = {}  # name -> Interface (the non-partial definition)
        self.partials = {}  # name -> [Interface]
        self.includes = {}  # target -> [(mixin, attrs)]
        self.typedefs = {}
        self.enums = {}  # name -> (values, attrs, file)
        self.dictionaries = set()
        self.callbacks = set()
        for path in sorted(self.webcore.rglob("*.idl")):
            relative = path.relative_to(self.webcore).as_posix()
            if relative.startswith("bindings/scripts/test/"):
                continue
            document = idl.parse(path.read_text(encoding="utf-8"), relative)
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
            self.dictionaries |= document.dictionaries
            self.callbacks |= document.callbacks
        self.scope = config["interfaces"]
        missing = [name for name in self.scope if name not in self.interfaces]
        if missing:
            raise SystemExit(f"gen/dom.json names interfaces the IDL files do not define: {missing}")

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
        attributes of the partial, mixin and includes statement merged into each, as CodeGenerator.pm does."""
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
        return found

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
        while t.name in self.typedefs:
            target = self.typedefs[t.name]
            t = idl.Type(target.name, t.nullable or target.nullable, target.subtypes, {**target.attrs, **t.attrs})
        return t

    def map(self, t: idl.Type) -> Mapped:
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
        if t.name in self.interfaces and not self.interfaces[t.name].mixin:
            if self.interfaces[t.name].callback:
                raise Unsupported(f"callback interface {t.name}")
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
            if root not in self.scope:
                raise Unsupported(f"interface {t.name} outside gen/dom.json")
            return Mapped("object", t.nullable, interface=t.name, root=root, cls=self.cpp_class(t.name))
        if t.name == "union":
            raise Unsupported(f"union {t}")
        if t.name in ("sequence", "FrozenArray", "record", "Promise", "ObservableArray"):
            raise Unsupported(f"{t.name} type {t}")
        if t.name in self.dictionaries:
            raise Unsupported(f"dictionary {t.name}")
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


def c_name(name):
    name = snake(name) if not name.isupper() else name.lower()
    return name + "_" if name in RESERVED or name in C_KEYWORDS else name


class Generator:
    def __init__(self, world: World):
        self.world = world
        self.functions = []
        self.excluded = []  # (Interface.member, reason)
        self.constants = []  # (macro, value, comment)
        self.enums_used = {}
        self.handles = []  # object handle roots
        self.headers = {"HTMLNames.h", "ElementInlines.h", "NodeInlines.h", "Exception.h", "ExceptionOr.h"}
        excludes = world.config["exclude"]
        self.exclude = set(excludes)

    def run(self):
        for name in self.world.scope:
            interface = self.world.interfaces[name]
            self.headers.add(f"{self.world.cpp_class(name)}.h")
            chain = self.world.chain(name)
            if "Node" not in chain and "Event" not in chain:
                root = chain[-1]
                if root != name:
                    raise SystemExit(f"{name}: gen/dom.json lists an interface whose base {root} has the handle")
                self.handles.append(name)
            self.interface(name)
        names = [f.name for f in self.functions]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise SystemExit(f"generated names collide: {sorted(duplicates)}")

    def skip(self, interface, member, reason):
        label = member.name or member.special or member.kind
        self.excluded.append((f"{interface}.{label}", reason))

    def interface(self, name):
        members = self.world.members(name)
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
                self.skip(name, member, "constructor")
                continue
            if member.kind == "operation":
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
                    supported.append((member, [self.world.map(a.type) for a in member.arguments],
                                      self.world.map(member.type)))
                except Unsupported as error:
                    self.skip(name, member, str(error))
            for member, args, returns in supported:
                suffix = f"_{len(member.arguments)}" if len(supported) > 1 else ""
                self.operation(name, member, args, returns, suffix)

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
        if any(a.variadic for a in member.arguments):
            return "variadic arguments"
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
        attribute = self.reflect(member, False)
        name = member.attrs.get("ImplementedAs", member.name)
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
        if mapped.kind != "string":
            raise Unsupported(f"[Reflect] of type {t}")
        if attribute == "HTMLNames::idAttr":
            return "impl->getIdAttribute()"
        if attribute == "HTMLNames::nameAttr":
            return "impl->getNameAttribute()"
        return f"impl->attributeWithoutSynchronization({attribute})"

    def setter_call(self, interface, member, mapped, value):
        attribute = self.reflect(member, True)
        if not attribute:
            name = "set" + wk_ucfirst(member.attrs.get("ImplementedAs", member.name))
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
        if mapped.kind != "string":
            raise Unsupported(f"[Reflect] of type {t}")
        return f"impl->setAttributeWithoutSynchronization({attribute}, AtomString {{ {value} }})"

    def attribute(self, interface, member):
        reason = self.member_reason(interface, member)
        if reason:
            self.skip(interface, member, reason)
            return
        try:
            mapped = self.world.map(member.type)
        except Unsupported as error:
            self.skip(interface, member, str(error))
            return
        base = f"{snake(interface)}_{{}}_{snake(member.name)}"
        idl_text = f"{'readonly ' if member.readonly else ''}attribute {member.type} {member.name}"
        # Getter.
        if "CustomGetter" in member.attrs:
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
        self_type = self.self_param(interface)
        params = [(self_type, "target")]
        checks = ["target"]
        prepare = []
        passed = []
        notes = []
        return_value = None
        for index, (argument, mapped) in enumerate(zip(arguments, mapped_args)):
            name = c_name(argument.name)
            optional_no_default = argument.optional and argument.default is None
            maybe_null = mapped.nullable or optional_no_default
            if argument.optional and argument.default is not None:
                notes.append(f"{name} defaults to {argument.default} in IDL")
            if mapped.kind == "string":
                params.append(("const char*", name))
                if not maybe_null:
                    checks.append(name)
                prepare.append(f"StringArg a{index} {{ {name} }};")
                atom = ("AtomString" in argument.attrs or "AtomString" in argument.type.attrs
                        or f"{interface}.{member.name}" in self.world.config["atomArguments"])
                if optional_no_default:
                    passed.append(f"a{index}")
                else:
                    passed.append(f"a{index}.atom()" if atom else f"a{index}.string()")
                if maybe_null:
                    notes.append(f"{name} may be NULL" + (" (absent)" if optional_no_default else " (null)"))
            elif mapped.kind in ("bool", "number"):
                ctype = mapped.ctype
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
            elif mapped.kind in ("node", "event", "object"):
                if mapped.kind == "object" or mapped.interface == "EventTarget":
                    raise Unsupported(f"{mapped.interface} argument")
                self.headers.add(f"{mapped.cls}.h")
                params.append((f"{mapped.handle}*", name))
                accessor = "nodeOf" if mapped.kind == "node" else "eventOf"
                base = "Node" if mapped.kind == "node" else "Event"
                if not maybe_null:
                    checks.append(name)
                if mapped.cls == base:
                    prepare.append(f"RefPtr<{base}> a{index} = {accessor}({name});")
                else:
                    prepare.append(f"RefPtr<{mapped.cls}> a{index} = {name} ? dynamicDowncast<{mapped.cls}>(*{accessor}({name})) : nullptr;")
                    prepare.append(f"if ({name} && !a{index})")
                    prepare.append("    return RV_ERR_WRONG_INTERFACE;")
                passed.append(f"a{index}.get()" if maybe_null else f"HandleArg<{mapped.cls}> {{ a{index}.get() }}")
                if maybe_null:
                    notes.append(f"{name} may be NULL")
                if "ReturnValue" in argument.attrs:
                    return_value = (index, mapped)
            else:
                raise Unsupported(f"{mapped.kind} argument")
        # The result.
        sink = None
        if return_value is not None:
            index, mapped = return_value
            params.append((f"{mapped.handle}**", "result"))
            checks.append("result")
            sink = ("returnvalue", index)
        elif returns.kind == "string":
            params += [("char*", "buffer"), ("int32_t", "capacity"), ("int32_t*", "length")]
            checks.append("length")
            sink = "copyString(asString(value), buffer, capacity, length)"
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
                sink = f"storeHandle<{root}>(value, result)"
            notes.append("*result is a new reference" + (", or NULL" if returns.nullable or returns.interface == "EventTarget" else ""))
        # The body.
        cls = self.world.cpp_class(interface)
        chain = self.world.chain(interface)
        body = [f"if ({' || '.join('!' + c for c in checks)})", "    return RV_ERR_NULL_ARGUMENT;",
                "if (!isMainThread())", "    return RV_ERR_WRONG_THREAD;"]
        if "Node" in chain:
            if cls == "Node":
                body.append("RefPtr<Node> impl = nodeOf(target);")
            else:
                body += [f"RefPtr impl = dynamicDowncast<{cls}>(*nodeOf(target));", "if (!impl)", "    return RV_ERR_WRONG_INTERFACE;"]
        elif "Event" in chain:
            if cls == "Event":
                body.append("RefPtr<Event> impl = eventOf(target);")
            else:
                body += [f"RefPtr impl = dynamicDowncast<{cls}>(*eventOf(target));", "if (!impl)", "    return RV_ERR_WRONG_INTERFACE;"]
        else:
            body.append(f"RefPtr<{cls}> impl = reinterpret_cast<{cls}*>(target);")
        if call_with:
            if "Node" not in chain:
                raise Unsupported("[CallWith] on an interface other than a node")
            body.append("Ref document = impl->document();")
        body += prepare
        expression = call
        expression = expression.replace("{call_with}", "".join(", document.get()" for _ in call_with))
        expression = expression.replace("{call_with_bare}", ", ".join("document.get()" for _ in call_with))
        expression = expression.replace("{call_with_lead}", "".join("document.get(), " for _ in call_with))
        for index, value in enumerate(passed):
            expression = expression.replace(f"{{arg{index}}}", value)
        if sink is None:
            body.append(f"return invoke([&]() -> decltype(auto) {{ return {expression}; }});")
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
        function.conditional = self.conditional(member)
        if function.conditional:
            notes.append(f"RV_ERR_UNSUPPORTED where WebKit builds without {member.attrs['Conditional']}")
        function.comment += "".join(f"; {note}" for note in notes)
        self.functions.append(function)

    # Output.

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
            " * - Strings in are NUL-terminated UTF-8. Strings out copy into buffer as RanvierWebCoreAbi.h describes.",
            " * - Booleans are int32_t 0 or 1. An argument that is nullable or optional without a default is a pointer,",
            " *   NULL for null or absent.",
            " * - Handles out are new references: rv_node_release, rv_event_release, or the rv_dom_*_release of the type.",
            " * - A member that throws returns RV_ERR_DOM_EXCEPTION, with the exception in rv_last_exception.",
            " * - A member WebKit compiles out on the platform returns RV_ERR_UNSUPPORTED.",
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
            lines.append(f"typedef struct Rv{name} Rv{name};")
        lines.append("")
        if self.constants:
            lines.append("/* Constants of the interfaces. */")
            lines.append("enum {")
            for macro, value, comment in self.constants:
                lines.append(f"    {macro} = {value}, /* {comment} */")
            lines.append("};")
            lines.append("")
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            lines.append(f"/* The values of the IDL enumeration {enum}. */")
            lines.append("enum {")
            for index, value in enumerate(values):
                lines.append(f"    RV_DOM_{snake(enum).upper()}_{re.sub(r'[^A-Za-z0-9]+', '_', value).upper() or 'EMPTY'} = {index}, /* \"{value}\" */")
            lines.append("};")
            lines.append("")
        for name in self.handles:
            lines.append(f"/* Releases a handle to a {name}. */")
            lines.append(f"RV_EXPORT void rv_dom_{snake(name)}_release(Rv{name}*);")
            lines.append(f"/* Adds a reference to a {name} and returns it. */")
            lines.append(f"RV_EXPORT Rv{name}* rv_dom_{snake(name)}_retain(Rv{name}*);")
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
        for function in self.functions:
            args = ", ".join(n for _, n in function.params)
            lines.append(f"int32_t rv_dom_{function.name}({params_text(function.params)}) {{ return ranvier_dom_{function.name}({args}); }}")
        return "\n".join(lines) + "\n"

    def glue(self):
        lines = [
            "// The glue of the generated DOM functions, compiled into WebCore by patch 0011 (config/common.cmake names this",
            "// file). Each function checks its arguments and thread, calls the member as WebKit's JavaScript bindings call",
            "// it, and converts the result. Generated by gen/domgen.py from WebKit's IDL files; do not edit.",
            '#include "config.h"',
            '#include "RanvierDomGlue.h"',
            "",
        ]
        lines += [f'#include "{h}"' for h in sorted(self.headers)]
        for enum, (_, _, file) in sorted(self.enums_used.items()):
            lines.append(f'#include "JS{pathlib.PurePosixPath(file).stem}.h"')
        lines += ["", RUNTIME, ""]
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            quoted = ", ".join(f'"{v}"_s' for v in values)
            lines.append(f"static constexpr ASCIILiteral {enum_table(enum)}[] = {{ {quoted} }};")
        lines += ["", "using namespace WebCore;", "", 'extern "C" {', ""]
        lines.append("int32_t ranvier_dom_has(const char* feature)")
        lines.append("{")
        lines.append("    if (!feature)")
        lines.append("        return 0;")
        groups = ["dom-generated"] + [f"dom:{name}" for name in self.world.scope]
        lines.append("    for (auto* name : { " + ", ".join(f'"{g}"' for g in groups) + " }) {")
        lines.append("        if (!std::strcmp(feature, name))")
        lines.append("            return 1;")
        lines.append("    }")
        lines.append("    return 0;")
        lines.append("}")
        lines.append("")
        for name in self.handles:
            cls = self.world.cpp_class(name)
            lines += [
                f"void ranvier_dom_{snake(name)}_release(Rv{name}* handle)",
                "{",
                "    if (handle && isMainThread())",
                f"        reinterpret_cast<{cls}*>(handle)->deref();",
                "}",
                "",
                f"Rv{name}* ranvier_dom_{snake(name)}_retain(Rv{name}* handle)",
                "{",
                "    if (!handle || !isMainThread())",
                "        return nullptr;",
                f"    reinterpret_cast<{cls}*>(handle)->ref();",
                "    return handle;",
                "}",
                "",
            ]
        for function in self.functions:
            lines.append(f"// {function.comment}")
            lines.append(f"int32_t ranvier_dom_{function.name}({params_text(function.params)})")
            lines.append("{")
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
        lines += ["} // extern \"C\"", ""]
        return "\n".join(lines)

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
            "let WrongInterface = -10",
        ]
        for macro, value, _ in self.constants:
            lines += ["", "[<Literal>]", f"let {macro} = {int(value, 0)}"]
        for enum, (values, _, _) in sorted(self.enums_used.items()):
            for index, value in enumerate(values):
                macro = f"RV_DOM_{snake(enum).upper()}_{re.sub(r'[^A-Za-z0-9]+', '_', value).upper() or 'EMPTY'}"
                lines += ["", "[<Literal>]", f"let {macro} = {index}"]
        for name in self.handles:
            lines += ["", "[<DllImport(Lib)>]", f"extern void rv_dom_{snake(name)}_release(nativeint handle)"]
            lines += ["", "[<DllImport(Lib)>]", f"extern nativeint rv_dom_{snake(name)}_retain(nativeint handle)"]
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
            f"operations {sum(f.kind == 'operation' for f in self.functions)}), handle types {len(self.handles)}, "
            f"constants {len(self.constants)}, enumerations {len(self.enums_used)}, left out {len(self.excluded)}",
            "",
            "Functions per interface:",
        ]
        for name in self.world.scope:
            lines.append(f"  {name}: {sum(f.interface == name for f in self.functions)}")
        lines += ["", "Left out:"]
        for label, reason in sorted(self.excluded):
            lines.append(f"  {label}: {reason}")
        del interfaces
        return "\n".join(lines) + "\n"


RUNTIME = r"""#include <cstring>
#include <optional>
#include <type_traits>
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

// A UTF-8 argument, which converts to the string type the member takes. NULL is the null string, or an absent
// optional string.
struct StringArg {
    explicit StringArg(const char* text)
        : value(text ? String::fromUTF8(text) : String { })
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
    if ctype == "const char*":
        return f"[<MarshalAs(UnmanagedType.LPUTF8Str)>] string {fname}"
    if ctype == "char*":
        return f"byte[] {fname}"
    if ctype == "int32_t*" and name == "length":
        return f"int[] {fname}"
    if ctype.startswith("const ") and ctype.endswith("*"):
        return f"{FSHARP_NUMBERS[ctype[6:-1]]}[] {fname}"
    if ctype.endswith("**"):
        return f"nativeint& {fname}"
    if ctype.startswith("Rv") and ctype.endswith("*"):
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
    if args.mode == "check" and differ:
        print("run: python -I gen/domgen.py write --source <webkit>")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
