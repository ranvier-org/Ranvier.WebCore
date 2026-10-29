"""Shared F# DOM interfaces and Fable adapters from the scoped Web IDL model."""

import itertools
import re

import idl

NUMBERS = {'byte': 'sbyte', 'octet': 'byte', 'short': 'int16', 'unsigned short': 'uint16',
           'long': 'int', 'unsigned long': 'uint32', 'long long': 'int64', 'unsigned long long': 'uint64',
           'float': 'float32', 'unrestricted float': 'float32', 'double': 'float', 'unrestricted double': 'float'}
KEYWORDS = set('abstract and as assert base begin class default delegate do done downcast downto elif else end exception extern false finally fixed for fun function global if in inherit inline interface internal lazy let match member module mutable namespace new not null of open or override private public rec return select sig static struct then to true try type upcast use val void when while with yield break checked component const constraint continue event external include mixin parallel process protected pure sealed tailcall trait virtual is'.split())
STRINGS = {'DOMString', 'USVString', 'ByteString'}


def identifier(name):
    return f'``{name}``' if name in KEYWORDS or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) else name


def label(t):
    if t.name == 'union':
        return 'Or'.join(label(child) for child in t.subtypes)
    if t.subtypes:
        return t.name[:1].upper() + t.name[1:] + 'Of' + 'And'.join(label(child) for child in t.subtypes)
    return ''.join(word[:1].upper() + word[1:] for word in t.name.split())


def case_name(value):
    return ''.join(part[:1].upper() + part[1:] for part in re.split(r'[^A-Za-z0-9]+', value) if part) or 'Empty'


class InterfaceEmitter:
    def __init__(self, generator):
        self.generator = generator
        self.world = generator.world
        self.unions = {}
        self.dictionaries = {}
        self.callbacks = set()
        self.adapters = []
        self.attribute_access = {}
        self.enums = set()
        self.sources = {self.world.public_name(name): name for name in self.world.contract_types}
        self.names = list(self.sources)

    def type(self, value):
        value = self.world.resolve(value)
        if value.name in STRINGS or self.world.string_union(value) is not None and value.name == 'union':
            result = 'string'
        elif value.name in NUMBERS:
            result = NUMBERS[value.name]
        elif value.name == 'boolean':
            result = 'bool'
        elif value.name == 'undefined':
            result = 'unit'
        elif value.name in ('sequence', 'FrozenArray'):
            result = f'({self.type(value.subtypes[0])}) array'
        elif value.name == 'union':
            result = label(value)
            for child in value.subtypes:
                self.type(child)
            self.unions[result] = value.subtypes
        elif value.name in self.world.dictionaries:
            result = value.name
            if result not in self.dictionaries:
                self.dictionaries[result] = []
                self.dictionaries[result] = [(member, self.type(member.type)) for member, _ in self.world.dictionary_fields(result)]
        elif value.name == 'EventListener':
            result = value.name
            self.callbacks.add(result)
        elif value.name in self.world.enums:
            result = value.name
            self.enums.add(result)
        elif value.name in self.names:
            result = value.name
        else:
            raise self.generator.unsupported_type(f'interface surface type {value.name} outside scope')
        if value.nullable and value.name in NUMBERS | {'boolean': ''} or value.nullable and value.name == 'union':
            result = f'({result}) option'
        return result

    def union(self, value):
        value = self.world.resolve(value)
        return value.name == 'union' and self.world.string_union(value) is None

    def complex(self, member):
        return self.union(member.type) or any(self.union(arg.type) for arg in member.arguments)

    def choices(self, arguments):
        variants = []
        for argument in arguments:
            t = self.world.resolve(argument.type)
            alternatives = list(t.subtypes) if self.union(t) and not argument.variadic else [argument.type]
            if argument.optional and self.union(t):
                alternatives = [None] + alternatives
            variants.append(alternatives)
        return itertools.product(*variants)

    def parameters(self, arguments, selected, raw=False):
        params = []
        for argument, t in zip(arguments, selected):
            if t is None:
                continue
            ftype = self.type(t)
            if raw and self.union(argument.type):
                ftype = 'obj'
            if argument.variadic:
                ftype += ' array'
            optional = argument.optional and (raw or not self.union(argument.type))
            name = ('?' if optional else '') + identifier(argument.name)
            params.append(('[<System.ParamArray>] ' if argument.variadic and not raw else '') + f'{name}: {ftype}')
        return ' * '.join(params) or 'unit'

    def supporting_functions(self, owner, member):
        source = self.sources.get(owner, owner)
        key = self.world.member_key(member)
        owners = [source]
        if self.world.interfaces[source].mixin:
            owners = [name for name in self.world.scope if source in self.world.contract_mixins(name)]
        return [function for function in self.generator.functions
                if function.interface in owners and function.member
                and self.world.member_key(function.member) == key and not function.unused]

    def emit_member(self, owner, member):
        if member.kind not in ('attribute', 'operation'):
            return []
        anonymous_property = not member.name and member.special in ('getter', 'setter', 'deleter')
        if anonymous_property:
            member = self.generator.special_name(member)
        special_listener = owner == 'EventTarget' and member.name in ('addEventListener', 'removeEventListener', 'dispatchEvent')
        if special_listener and member.name in ('addEventListener', 'removeEventListener'):
            self.callbacks.add('EventListener')
            lines = [f'    /// <summary>{owner}.{member.name} registers or removes an event callback.</summary>',
                     f'    abstract member {member.name}: eventType: string * listener: EventListener * ?capture: bool -> unit',
                     f'    abstract member {member.name}: eventType: string * listener: EventListenerObject * ?capture: bool -> unit']
            if len(member.arguments) >= 3:
                options = self.world.resolve(member.arguments[2].type)
                for choice in options.subtypes if options.name == 'union' else [options]:
                    if choice.name not in self.world.contract_dictionary_fields:
                        continue
                    option_type = self.type(choice)
                    lines += [f'    abstract member {member.name}: eventType: string * listener: {listener} * options: {option_type} -> unit'
                              for listener in ['EventListener', 'EventListenerObject']]
            return lines
        if not special_listener and self.generator.member_reason(owner, member):
            return []
        if not special_listener and not self.supporting_functions(owner, member):
            return []
        try:
            result = self.type(member.type)
            for argument in member.arguments:
                self.type(argument.type)
        except self.generator.unsupported_type:
            return []
        needs_adapter = self.complex(member)
        lines = ([''] if needs_adapter or anonymous_property else []) + [f'    /// <summary>{owner}.{member.name}.</summary>']
        if member.kind == 'attribute':
            functions = self.supporting_functions(owner, member)
            getter = any(function.kind == 'getter' for function in functions)
            setter = any(function.kind == 'setter' for function in functions)
            self.attribute_access[(owner, self.world.member_key(member))] = (getter, setter)
            access = ', '.join(name for name, available in [('get', getter), ('set', setter)] if available)
            signature = f'    abstract member {identifier(member.name)}: {result} with {access}'
            if not needs_adapter:
                return lines + [signature]
            lines += ['#if FABLE_COMPILER']
            if getter:
                lines += [f'    [<Fable.Core.Emit("$0.{member.name}")>]',
                          f'    abstract member __ranvier_get_{member.name}: unit -> obj']
            if setter:
                lines += ['', f'    [<Fable.Core.Emit("$0.{member.name} = $1")>]',
                          f'    abstract member __ranvier_set_{member.name}: value: obj -> unit']
            lines += ['#else', signature, '#endif']
            self.adapters.append((owner, member))
            return lines
        selected_arguments = list(self.choices(member.arguments))
        if anonymous_property and not needs_adapter:
            expression = {'getter': '$0[$1]', 'setter': '$0[$1] = $2', 'deleter': 'delete $0[$1]'}[member.special]
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif']
        if needs_adapter:
            raw_params = self.parameters(member.arguments, [a.type for a in member.arguments], raw=True)
            raw_result = 'obj' if self.union(member.type) else result
            arg_expressions = [('...' if a.variadic else '') + f'${i + 1}' for i, a in enumerate(member.arguments)]
            expression = f'$0.{member.name}(' + ', '.join(arg_expressions) + ')'
            if anonymous_property:
                expression = {'getter': '$0[$1]', 'setter': '$0[$1] = $2', 'deleter': 'delete $0[$1]'}[member.special]
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]',
                      f'    abstract member __ranvier_{member.name}: {raw_params} -> {raw_result}', '#else']
        for selected in selected_arguments:
            lines += [f'    abstract member {identifier(member.name)}: {self.parameters(member.arguments, selected)} -> {result}']
        if needs_adapter:
            lines += ['#endif']
            self.adapters.append((owner, member))
        if anonymous_property:
            lines += ['']
        return lines

    def box_union(self, value, expression):
        t = self.world.resolve(value)
        if not self.union(t):
            return f'box ({expression})'
        name = label(t)
        if t.nullable:
            plain = idl.Type(t.name, False, t.subtypes, t.attrs)
            return f'(match {expression} with None -> null | Some unionValue -> {self.box_union(plain, "unionValue")})'
        return f'(match {expression} with ' + ' | '.join(f'{name}.{label(child)} value -> box value' for child in t.subtypes) + ')'

    def unbox_union(self, value, expression):
        t = self.world.resolve(value)
        if not self.union(t):
            return expression
        name = label(t)
        arms = []
        for child in t.subtypes:
            child = self.world.resolve(child)
            ftype = self.type(child)
            if child.name in STRINGS or child.name in NUMBERS or child.name == 'boolean':
                test = f':? {ftype} as arm'
                arms.append(f'| {test} -> {name}.{label(child)} arm')
            else:
                arms.append(f'| arm when is{child.name} arm -> {name}.{label(child)} (unbox<{ftype}> arm)')
        body = f'(match ({expression}: obj) with ' + ' '.join(arms) + ' | _ -> failwith "Unexpected DOM union result")'
        return f'(let value = {expression} in if isNull value then None else Some {body.replace(expression, "value")})' if t.nullable else body

    def extensions(self):
        if not self.adapters:
            return []
        lines = ['', '#if FABLE_COMPILER', '[<AutoOpen>]', 'module BrowserUnionAdapters =']
        result_interfaces = set()
        for _, member in self.adapters:
            t = self.world.resolve(member.type)
            if self.union(t):
                result_interfaces.update(child.name for child in t.subtypes if child.name in self.names)
        for name in sorted(result_interfaces):
            predicate = '$0 != null && $0.nodeType === 1' if name == 'Element' else f'Object.prototype.toString.call($0) === \'[object {name}]\''
            lines += [f'    [<Fable.Core.Emit("{predicate}")>]',
                      f'    let private is{name} (_: obj) : bool =', '        Fable.Core.Util.jsNative', '']
        for name, children in self.unions.items():
            lines += ['', f'    let private box{name} (value: {name}) : obj =', '        match value with']
            for child in children:
                lines += [f'        | {name}.{label(child)} value -> box value']
            if any(self.union(member.type) and label(self.world.resolve(member.type)) == name for _, member in self.adapters):
                lines += ['', f'    let private unbox{name} (value: obj) : {name} =', '        match value with']
                for child in children:
                    resolved = self.world.resolve(child)
                    ftype = self.type(child)
                    if resolved.name in STRINGS or resolved.name in NUMBERS or resolved.name == 'boolean':
                        lines += [f'        | :? {ftype} as arm -> {name}.{label(child)} arm']
                    else:
                        lines += [f'        | arm when is{resolved.name} arm -> {name}.{label(child)} (unbox<{ftype}> arm)']
                lines += ['        | _ -> failwith "Unexpected DOM union result"']
        for owner in dict.fromkeys(owner for owner, _ in self.adapters):
            lines += ['', f'    type {owner} with']
            for current, member in self.adapters:
                if current != owner:
                    continue
                result = self.type(member.type)
                if member.kind == 'attribute':
                    getter, setter = self.attribute_access[(owner, self.world.member_key(member))]
                    union_name = label(self.world.resolve(member.type))
                    lines += [f'        member this.{identifier(member.name)}']
                    if getter:
                        lines += [f'            with get (): {result} =',
                                  f'                let value = this.__ranvier_get_{member.name} ()']
                        if self.world.resolve(member.type).nullable:
                            lines += ['', '                if isNull value then', '                    None', '                else',
                                      f'                    Some (unbox{union_name} value)']
                        else:
                            lines += [f'                unbox{union_name} value']
                    if setter:
                        boxed = f'value |> Option.map box{union_name} |> Option.defaultValue null' if self.world.resolve(member.type).nullable else f'box{union_name} value'
                        lines += [f'            {"and" if getter else "with"} set (value: {result}) =']
                        if self.world.resolve(member.type).nullable:
                            lines += [f'                this.__ranvier_set_{member.name} (', '                    value',
                                      f'                    |> Option.map box{union_name}', '                    |> Option.defaultValue null', '                )']
                        else:
                            lines += [f'                this.__ranvier_set_{member.name} ({boxed})']
                    lines += ['']
                    continue
                for selected in self.choices(member.arguments):
                    declarations, passed = [], []
                    for argument_index, (argument, chosen) in enumerate(zip(member.arguments, selected)):
                        name = identifier(argument.name)
                        if chosen is None:
                            passed.append(f'?{name} = None')
                            continue
                        ftype = self.type(chosen)
                        optional = argument.optional and not self.union(argument.type)
                        if argument.variadic:
                            declarations.append(f'[<System.ParamArray>] {name}: {ftype} array')
                            expr = f'{name} |> Array.map box{label(self.world.resolve(argument.type))}' if self.union(argument.type) else name
                        else:
                            declarations.append(f'{"?" if optional else ""}{name}: {ftype}')
                            expr = f'box {name}' if self.union(argument.type) else name
                        if argument.optional:
                            if self.union(argument.type):
                                expr = f'?{name} = Some ({expr})'
                            else:
                                expr = f'?{name} = {expr}'
                        elif any(previous.optional for previous in member.arguments[:argument_index]):
                            expr = f'{name} = {expr}'
                        passed.append(expr)
                    raw_call = f'this.__ranvier_{member.name} (' + ', '.join(passed) + ')'
                    lines += [f'        member this.{identifier(member.name)}(' + ', '.join(declarations) + f') : {result} =']
                    if self.union(member.type):
                        union_name = label(self.world.resolve(member.type))
                        lines += [f'            let value = {raw_call}', '']
                        if self.world.resolve(member.type).nullable:
                            lines += ['            if isNull value then', '                None', '            else',
                                      f'                Some (unbox{union_name} value)']
                        else:
                            lines += [f'            unbox{union_name} value']
                    else:
                        lines += [f'            {raw_call}']
                    lines += ['']
        return lines + ['#endif']

    def emit(self):
        for name in self.world.contract_dictionary_fields:
            self.type(idl.Type(name))
        bodies = []
        for name in self.names:
            members = []
            source = self.sources[name]
            if source in self.world.scope or self.world.interfaces[source].mixin or source == 'EventTarget':
                for member in self.world.members(source):
                    if not self.world.interfaces[source].mixin and self.world.contract_owner(source, member) != name:
                        continue
                    members += self.emit_member(name, member)
            bodies.append((name, members))
        lines = ['// <auto-generated>', 'namespace Ranvier.Dom', '', 'open System', '',
                 '#if FABLE_COMPILER', 'type internal DomStringEnumAttribute = Fable.Core.StringEnumAttribute',
                 'type internal DomDictionaryAttribute = Fable.Core.AttachMembersAttribute',
                 '#else', '[<AttributeUsage(AttributeTargets.Class)>]',
                 'type internal DomStringEnumAttribute() =', '    inherit Attribute()', '',
                 '[<AttributeUsage(AttributeTargets.Class)>]', 'type internal DomDictionaryAttribute() =',
                 '    inherit Attribute()', '#endif', '']
        declarations = []
        for name, members in bodies:
            source = self.sources[name]
            base = self.world.public_name(self.world.interfaces[source].base)
            mixins = [self.world.public_name(mixin) for mixin in self.world.contract_mixins(source)]
            body = ([f'    inherit {base}'] if base in self.names else []) + [f'    inherit {mixin}' for mixin in mixins] + members
            declarations.append((name, '[<AllowNullLiteral>]', body or ['    interface end']))
        for name, children in self.unions.items():
            declarations.append((name, '[<RequireQualifiedAccess>]', [f'    | {label(child)} of {self.type(child)}' for child in children]))
        for name, fields in self.dictionaries.items():
            body = []
            base = self.world.dictionaries[name].base
            inherited = set()
            if name in self.world.contract_dictionary_fields and base in self.dictionaries:
                body += [f'    inherit {base}()']
                inherited = {member.name for member, _ in self.world.dictionary_fields(base)}
            for member, ftype in fields:
                if member.name in inherited:
                    continue
                t = self.world.resolve(member.type)
                default = member.default
                if not member.required and default is None:
                    ftype = f'({ftype}) option' if not ftype.endswith(' option') else ftype
                    value = 'None'
                elif default == 'null':
                    value = 'None' if ftype.endswith(' option') else 'null'
                elif default == '[]':
                    value = '[||]'
                elif t.name in self.world.enums and default is not None:
                    value = f'{t.name}.{case_name(default.strip(chr(34)))}'
                elif default is not None:
                    suffix = {'sbyte': 'y', 'byte': 'uy', 'int16': 's', 'uint16': 'us', 'uint32': 'u', 'int64': 'L', 'uint64': 'UL', 'float32': 'f'}.get(ftype, '')
                    value = default + suffix
                else:
                    value = 'Unchecked.defaultof<_>'
                body += [f'    member val {identifier(member.name)}: {ftype} = {value} with get, set']
            declarations.append((name + '()', '[<AllowNullLiteral; DomDictionary>]', body or ['    class end']))
        for name in sorted(self.callbacks):
            if name == 'EventListener':
                declarations.append((name, '', ['    Event -> unit']))
                declarations.append(('EventListenerObject', '[<AllowNullLiteral>]', ['    abstract member handleEvent: event: Event -> unit']))
        for name, (values, _, _) in self.world.enums.items():
            if name in self.enums:
                declarations.append((name, '[<RequireQualifiedAccess>]', [f'    | [<CompiledName("{value}")>] {case_name(value)}' for value in values]))
        for index, (name, attrs, body) in enumerate(declarations):
            lines += [f'/// <summary>{name.removesuffix("()")} in the scoped DOM interface model.</summary>']
            dictionary = name.removesuffix('()')
            if dictionary in self.world.contract_dictionary_fields:
                omitted = sorted(field.split('.', 1)[1] for field in self.world.dictionary_exclusions if field.startswith(dictionary + '.'))
                if omitted:
                    lines += [f'/// <remarks>Fields omitted from the shared contract: {", ".join(omitted)}.</remarks>']
            prefix = "type" if index == 0 else "and"
            if name in self.world.enums:
                lines += [f'{prefix} [<DomStringEnum; RequireQualifiedAccess>] {name} =']
            else:
                if index == 0:
                    if body == ['    interface end'] or body == ['    class end']:
                        lines += [attrs, f'type {name} = {body[0].strip()}']
                        body = []
                    else:
                        lines += [attrs, f'type {name} =']
                elif body == ['    interface end'] or body == ['    class end'] or attrs == '':
                    lines += [f'{prefix}{" " + attrs if attrs else ""} {name} = {body[0].strip()}']
                    body = []
                else:
                    lines += [f'{prefix} {attrs} {name} =']
            lines += body + ['']
        lines += self.extensions()
        return '\n'.join(lines) + '\n'


def emit_interfaces(generator):
    return InterfaceEmitter(generator).emit()
