"""A lean Web IDL parser for WebKit's IDL files: the definitions gen/domgen.py reads (interfaces, interface mixins,
partial interfaces, includes statements, typedefs, enums, dictionaries and callbacks), their members, types and
extended attributes, namespaces, partial namespaces, and iterable, setlike and maplike declarations. Other unmodeled
members are skipped.

WebKit's IDL files hold a few `#if` blocks (Document.idl, DeviceOrientationEvent.idl); the parser keeps the
`#else` branch of each and drops the `#if` branch, which matches a build with every such macro undefined.
"""

import re
from dataclasses import dataclass, field

TOKEN = re.compile(
    r"""
    (?P<space>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<float>-?(?:(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)(?:[Ee][+-]?[0-9]+)?|[0-9]+[Ee][+-]?[0-9]+))
  | (?P<integer>-?(?:0[Xx][0-9A-Fa-f]+|0[0-7]*|[1-9][0-9]*))
  | (?P<string>"[^"]*")
  | (?P<identifier>[_-]?[A-Za-z][0-9A-Z_a-z-]*)
  | (?P<other>\.\.\.|[^\t\n\r 0-9A-Za-z])
    """,
    re.X | re.S,
)


@dataclass
class Type:
    name: str  # a builtin such as "unsigned long", an identifier, "sequence", "union", ...
    nullable: bool = False
    subtypes: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)  # type-level extended attributes, such as [AtomString]

    def __str__(self):
        if self.name == "union":
            text = "(" + " or ".join(map(str, self.subtypes)) + ")"
        elif self.subtypes:
            text = f"{self.name}<{', '.join(map(str, self.subtypes))}>"
        else:
            text = self.name
        return text + ("?" if self.nullable else "")


@dataclass
class Argument:
    name: str
    type: Type
    optional: bool = False
    variadic: bool = False
    default: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class Member:
    kind: str  # "attribute", "operation", "const", "constructor", "other"
    name: str
    type: Type | None = None
    readonly: bool = False
    static: bool = False
    special: str = ""  # getter, setter, deleter, stringifier
    arguments: list = field(default_factory=list)
    value: str | None = None
    attrs: dict = field(default_factory=dict)
    file: str = ""
    owner: str = ""  # the interface or mixin that declares it


@dataclass
class Interface:
    name: str
    base: str | None = None
    mixin: bool = False
    partial: bool = False
    callback: bool = False
    attrs: dict = field(default_factory=dict)
    members: list = field(default_factory=list)
    file: str = ""


@dataclass
class DictionaryMember:
    name: str
    type: Type
    required: bool = False
    default: str | None = None
    attrs: dict = field(default_factory=dict)


@dataclass
class Namespace:
    name: str
    partial: bool = False
    attrs: dict = field(default_factory=dict)
    members: list = field(default_factory=list)
    file: str = ""


@dataclass
class Dictionary:
    name: str
    base: str | None = None
    partial: bool = False
    attrs: dict = field(default_factory=dict)
    members: list = field(default_factory=list)
    file: str = ""


@dataclass
class Document:
    file: str
    interfaces: list = field(default_factory=list)
    includes: list = field(default_factory=list)  # (target, mixin, attrs)
    typedefs: dict = field(default_factory=dict)
    enums: dict = field(default_factory=dict)  # name -> (values, attrs)
    dictionaries: dict = field(default_factory=dict)  # name -> Dictionary
    callbacks: set = field(default_factory=set)
    namespaces: list = field(default_factory=list)


def preprocess(text: str) -> str:
    """Keeps the #else branch of each #if block and drops the #if branch."""
    out, stack = [], []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#if"):
            stack.append(False)
            continue
        if stripped.startswith("#else"):
            stack[-1] = True
            continue
        if stripped.startswith("#endif"):
            stack.pop()
            continue
        if all(stack):
            out.append(line)
        else:
            out.append("")
    return "\n".join(out)


class Parser:
    def __init__(self, text: str, file: str):
        self.file = file
        self.tokens = []
        for match in TOKEN.finditer(preprocess(text)):
            kind = match.lastgroup
            if kind != "space":
                self.tokens.append((kind, match.group(kind)))
        self.at = 0

    # Token helpers.

    def peek(self, offset=0):
        index = self.at + offset
        return self.tokens[index][1] if index < len(self.tokens) else None

    def take(self, expected=None):
        kind, value = self.tokens[self.at]
        if expected is not None and value != expected:
            raise SyntaxError(f"{self.file}: expected {expected!r}, found {value!r} near token {self.at}")
        self.at += 1
        return value

    def accept(self, value):
        if self.peek() == value:
            self.at += 1
            return True
        return False

    def skip_balanced(self, open_, close):
        depth = 0
        while True:
            value = self.take()
            if value == open_:
                depth += 1
            elif value == close:
                depth -= 1
                if depth == 0:
                    return

    def skip_to_semicolon(self):
        depth = 0
        while True:
            value = self.take()
            if value in "{([<":
                depth += 1
            elif value in "})]>":
                depth -= 1
            elif value == ";" and depth == 0:
                return

    # Grammar.

    def extended_attributes(self):
        attrs = {}
        if not self.accept("["):
            return attrs
        while not self.accept("]"):
            name = self.take()
            if name == ",":
                continue
            value = True
            if self.accept("="):
                if self.peek() == "(":
                    self.take("(")
                    parts = []
                    while not self.accept(")"):
                        part = self.take()
                        if part != ",":
                            parts.append(part)
                    value = parts
                elif self.peek() in ("[", "{"):
                    value = self.take() + self.take()
                else:
                    parts = [self.take()]
                    # Values such as Conditional=A&B, A|B or a qualified name.
                    while self.peek() in ("&", "|", "::", ":") and self.peek(1) not in ("]", ","):
                        parts.append(self.take())
                        parts.append(self.take())
                    value = "".join(parts)
                    if self.peek() == "(":
                        self.skip_balanced("(", ")")
            elif self.peek() == "(":
                # An extended attribute with an argument list, such as LegacyFactoryFunction=Image(...).
                self.skip_balanced("(", ")")
            attrs[name] = value
        return attrs

    def type(self):
        attrs = self.extended_attributes()
        if self.peek() == "(":
            self.take("(")
            subtypes = [self.type()]
            while self.accept("or"):
                subtypes.append(self.type())
            self.take(")")
            result = Type("union", subtypes=subtypes)
        else:
            words = [self.take()]
            if words[0] == "unsigned":
                words.append(self.take())
            if words[0] == "unrestricted":
                words.append(self.take())
            if words[-1] == "long" and self.peek() == "long":
                words.append(self.take())
            result = Type(" ".join(words))
            if self.peek() == "<":
                self.take("<")
                result.subtypes.append(self.type())
                while self.accept(","):
                    result.subtypes.append(self.type())
                self.take(">")
        if self.accept("?"):
            result.nullable = True
        result.attrs = attrs
        return result

    def arguments(self):
        self.take("(")
        found = []
        while not self.accept(")"):
            if self.accept(","):
                continue
            attrs = self.extended_attributes()
            optional = self.accept("optional")
            argument_type = self.type()
            variadic = self.accept("...")
            name = self.take()
            default = None
            if self.accept("="):
                if self.peek() in ("[", "{"):
                    default = self.take() + self.take()
                else:
                    default = self.take()
            found.append(Argument(name, argument_type, optional, variadic, default, attrs))
        return found

    def collection_like(self, attrs, owner, readonly):
        """A setlike<V> or maplike<K, V> declaration, as a member whose kind is the keyword and whose type holds the
        value type, or the key and value types."""
        kind = self.take()
        self.take('<')
        children = [self.type()]
        if kind == 'maplike':
            self.take(',')
            children.append(self.type())
        self.take('>')
        self.take(';')
        return Member(kind, kind, Type(kind, subtypes=children), readonly=readonly, attrs=attrs, file=self.file, owner=owner)

    def member(self, owner):
        attrs = self.extended_attributes()
        if self.accept('iterable'):
            self.take('<')
            children = [self.type()]
            if self.accept(','):
                children.append(self.type())
            self.take('>')
            self.take(';')
            value = Type('pair', subtypes=children) if len(children) == 2 else children[0]
            return Member('iterable', 'entries', Type('sequence', subtypes=[value]), attrs=attrs, file=self.file, owner=owner)
        if self.peek() in ("maplike", "setlike"):
            return self.collection_like(attrs, owner, False)
        if self.peek() in ("iterable", "async", "async_iterable"):
            self.skip_to_semicolon()
            return None
        if self.accept("constructor"):
            arguments = self.arguments()
            self.take(";")
            return Member("constructor", "constructor", arguments=arguments, attrs=attrs, file=self.file, owner=owner)
        if self.accept("const"):
            const_type = self.type()
            name = self.take()
            self.take("=")
            value = self.take()
            self.take(";")
            return Member("const", name, const_type, value=value, attrs=attrs, file=self.file, owner=owner)
        static = readonly = False
        special = ""
        while self.peek() in ("static", "readonly", "inherit", "getter", "setter", "deleter", "stringifier"):
            word = self.take()
            if word == "static":
                static = True
            elif word == "readonly":
                readonly = True
            elif word in ("getter", "setter", "deleter", "stringifier"):
                special = word
        if self.peek() in ("maplike", "setlike") and readonly and not static and not special:
            return self.collection_like(attrs, owner, True)
        if self.peek() in ("iterable", "maplike", "setlike", "async", "async_iterable"):
            self.skip_to_semicolon()
            return None
        if special == "stringifier" and self.peek() == ";":
            self.take(";")
            return Member("operation", "toString", Type("DOMString"), special=special,
                          attrs=attrs, file=self.file, owner=owner)
        if self.accept("attribute"):
            attribute_type = self.type()
            name = self.take()
            self.take(";")
            return Member("attribute", name, attribute_type, readonly=readonly, static=static, special=special,
                          attrs=attrs, file=self.file, owner=owner)
        return_type = self.type()
        name = self.take() if self.peek() != "(" else ""
        arguments = self.arguments()
        self.take(";")
        return Member("operation", name, return_type, static=static, special=special, arguments=arguments,
                      attrs=attrs, file=self.file, owner=owner)

    def parse(self) -> Document:
        document = Document(self.file)
        while self.at < len(self.tokens):
            attrs = self.extended_attributes()
            word = self.peek()
            if word == "partial":
                self.take()
                word = self.peek()
                partial = True
            else:
                partial = False
            if word == "callback":
                self.take()
                if self.peek() == "interface":
                    self.take()
                    name = self.take()
                    document.callbacks.add(name)
                    interface = Interface(name, None, False, partial, callback=True, attrs=attrs, file=self.file)
                    self.take("{")
                    while not self.accept("}"):
                        member = self.member(name)
                        if member:
                            interface.members.append(member)
                    self.take(";")
                    document.interfaces.append(interface)
                else:
                    name = self.take()
                    document.callbacks.add(name)
                    self.skip_to_semicolon()
                continue
            if word == "interface":
                self.take()
                mixin = self.accept("mixin")
                name = self.take()
                base = None
                if self.accept(":"):
                    base = self.take()
                interface = Interface(name, base, mixin, partial, attrs=attrs, file=self.file)
                self.take("{")
                while not self.accept("}"):
                    member = self.member(name)
                    if member:
                        interface.members.append(member)
                self.take(";")
                document.interfaces.append(interface)
                continue
            if word == "dictionary":
                self.take()
                name = self.take()
                base = self.take() if self.accept(":") else None
                dictionary = Dictionary(name, base, partial, attrs, file=self.file)
                self.take("{")
                while not self.accept("}"):
                    member_attrs = self.extended_attributes()
                    required = self.accept("required")
                    member_type = self.type()
                    member_name = self.take()
                    default = None
                    if self.accept("="):
                        if self.peek() in ("[", "{"):
                            default = self.take() + self.take()
                        else:
                            default = self.take()
                    self.take(";")
                    dictionary.members.append(DictionaryMember(member_name, member_type, required, default, member_attrs))
                self.take(";")
                if partial and name in document.dictionaries:
                    document.dictionaries[name].members += dictionary.members
                else:
                    document.dictionaries.setdefault(name, dictionary) if partial else document.dictionaries.__setitem__(name, dictionary)
                continue
            if word == "enum":
                self.take()
                name = self.take()
                self.take("{")
                values = []
                while not self.accept("}"):
                    value = self.take()
                    if value != ",":
                        values.append(value[1:-1])
                self.take(";")
                document.enums[name] = (values, attrs)
                continue
            if word == "typedef":
                self.take()
                typedef_type = self.type()
                name = self.take()
                self.take(";")
                document.typedefs[name] = typedef_type
                continue
            if word == "namespace":
                self.take()
                name = self.take()
                namespace = Namespace(name, partial=partial, attrs=attrs, file=self.file)
                self.take("{")
                while not self.accept("}"):
                    member = self.member(name)
                    if member:
                        namespace.members.append(member)
                self.take(";")
                document.namespaces.append(namespace)
                continue
            # `A includes B;`
            if self.peek(1) == "includes":
                target = self.take()
                self.take("includes")
                mixin = self.take()
                self.take(";")
                document.includes.append((target, mixin, attrs))
                continue
            raise SyntaxError(f"{self.file}: unexpected {word!r}")
        return document


def parse(text: str, file: str) -> Document:
    return Parser(text, file).parse()
