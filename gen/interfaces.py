"""Shared F# DOM interfaces and Fable adapters from the scoped Web IDL model."""

import itertools
import re

import idl

NUMBERS = {'byte': 'sbyte', 'octet': 'byte', 'short': 'int16', 'unsigned short': 'uint16',
           'long': 'int', 'unsigned long': 'uint32', 'long long': 'int64', 'unsigned long long': 'uint64',
           'float': 'float32', 'unrestricted float': 'float32', 'double': 'float', 'unrestricted double': 'float'}
KEYWORDS = set('abstract and as assert base begin class default delegate do done downcast downto elif else end exception extern false finally fixed for fun function global if in inherit inline interface internal lazy let match member module mutable namespace new not null of open or override private public rec return select sig static struct then to true try type upcast use val void when while with yield break checked component const constraint continue event external include mixin parallel process protected pure sealed tailcall trait virtual is'.split())
STRINGS = {'DOMString', 'USVString', 'ByteString'}
WIDE_INTEGERS = {'long long', 'unsigned long long'}


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
        self.shadowed = set()
        self.attribute_access = {}
        self.enums = set()
        self.matrix_flag_adapters_used = set()
        self.svg_matrix_dictionary_adapters_used = set()
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
        elif value.name in self.world.config.get('byteSpanTypes', []):
            result = 'byte array'
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
                # The placeholder ends a recursive reference; a member type outside the contract removes the dictionary.
                self.dictionaries[result] = []
                try:
                    self.dictionaries[result] = [(member, self.type(member.type)) for member, _ in self.world.dictionary_fields(result)]
                except self.generator.unsupported_type:
                    del self.dictionaries[result]
                    raise
        elif value.name == 'EventListener':
            result = value.name
            self.callbacks.add(result)
        elif value.name in self.world.enums:
            result = value.name
            self.enums.add(result)
        elif value.name in self.world.config.get('callbackObjectRoots', {}):
            result = value.name
            self.callbacks.add(result)
        elif self.world.public_name(value.name) in self.names:
            result = self.world.public_name(value.name)
        else:
            raise self.generator.unsupported_type(f'interface surface type {value.name} outside scope')
        if (value.nullable and value.name in NUMBERS | {'boolean': ''} or value.nullable and value.name == 'union'
                or value.nullable and value.name in self.world.config.get('callbackObjectRoots', {})):
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
        # An omitted optional union omits the later optional arguments too: F# cannot tell `test(baseURL)` from
        # `test(input)`. A variadic argument stays, since its array keeps the call distinct.
        combinations = []
        for combination in itertools.product(*variants):
            if None in combination:
                first = combination.index(None)
                combination = combination[:first] + tuple(
                    None if argument.optional and not argument.variadic else chosen
                    for argument, chosen in zip(arguments[first:], combination[first:]))
            if combination not in combinations:
                combinations.append(combination)
        return combinations

    def parameters(self, arguments, selected, raw=False):
        params = []
        for argument, t in zip(arguments, selected):
            if t is None:
                continue
            ftype = self.type(t)
            if argument.optional and self.world.resolve(t).name in self.world.config.get('callbackObjectRoots', {}):
                ftype = self.world.resolve(t).name
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

    def browser_property_expression(self, owner, member):
        if owner in ('CSSUnparsedValue', 'CSSTransformValue') and member.name == 'setItem' and member.special == 'setter':
            return "((v,i,s)=>{if(i===4294967295)throw new RangeError('Index out of range.');v[i]=s;})($0,$1,$2)"
        if owner == 'StyleSheetList' and member.name == 'namedItem' and member.special == 'getter':
            return ("((s,n)=>{const k=Symbol.for('Ranvier.Dom.StyleSheetList.documents.v1');const m=globalThis[k];"
                    "let d;try{d=WeakRef.prototype.deref.call(Object.getOwnPropertyDescriptor(s,k)?.value);}catch{}"
                    "d=d||m?.get(s)?.deref()||(s.length?s.item(0)?.ownerNode?.ownerDocument:null);"
                    "if(!d||d.styleSheets!==s)return null;const e=d.getElementById(n??'');"
                    "return e&&e.namespaceURI==='http://www.w3.org/1999/xhtml'&&e.localName==='style'?e.sheet:null;})($0,$1)")
        if owner == 'DOMStringMap' and member.name == 'namedItem' and member.special == 'getter':
            return "(Object.prototype.hasOwnProperty.call($0,$1)?$0[$1]:'')"
        return {'getter': '$0[$1]', 'setter': '$0[$1] = $2', 'deleter': 'delete $0[$1]'}[member.special]

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
        needs_adapter = self.complex(member) or (owner, member.kind, member.name, len(member.arguments)) in self.shadowed
        matrix_adapter = f'{owner}.{member.name}'
        lines = ([''] if needs_adapter or anonymous_property or matrix_adapter in self.world.config.get('browserMatrixFlagAdapters', []) or matrix_adapter in self.generator.svg_matrix_bindings else []) + [f'    /// <summary>{owner}.{member.name}.</summary>']
        if member.kind == 'attribute':
            functions = self.supporting_functions(owner, member)
            getter = any(function.kind == 'getter' for function in functions)
            setter = any(function.kind == 'setter' for function in functions)
            self.attribute_access[(owner, self.world.member_key(member))] = (getter, setter)
            access = ', '.join(name for name, available in [('get', getter), ('set', setter)] if available)
            signature = f'    abstract member {identifier(member.name)}: {result} with {access}'
            if not needs_adapter:
                source = self.sources.get(owner, owner)
                if setter and self.world.resolve(member.type).name == 'USVString' and source in self.world.config.get('browserWellFormedSetters', []):
                    expression = '$0.' + member.name + "{{=((v)=>String(v==null?'null':v).toWellFormed())($1)}}"
                    return [''] + lines + ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif', signature, '']
                if getter and not setter and self.world.resolve(member.type).name in WIDE_INTEGERS:
                    # A browser returns a JavaScript number; Fable represents int64 and uint64 as BigInt.
                    return [''] + lines + ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("BigInt($0.{member.name})")>]', '#endif', signature, '']
                if owner in ('Document', 'ShadowRoot', 'DocumentOrShadowRoot') and member.name == 'styleSheets' and getter:
                    expression = ("((r)=>{const s=r.styleSheets;if(r.nodeType===9){"
                                  "const k=Symbol.for('Ranvier.Dom.StyleSheetList.documents.v1');"
                                  "const m=globalThis[k]||(globalThis[k]=new WeakMap());let v=m.get(s);"
                                  "if(!v){v=new WeakRef(r);m.set(s,v);}"
                                  "if(!Object.getOwnPropertyDescriptor(s,k))Reflect.defineProperty(s,k,{value:v});}return s;})($0)")
                    return [''] + lines + ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]',
                                          '#endif', signature, '']
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
            expression = self.browser_property_expression(owner, member)
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif']
        matrix_adapter = f'{owner}.{member.name}'
        if matrix_adapter in self.generator.svg_matrix_bindings:
            expression = ("((v,d)=>{const n=globalThis.DOMMatrix.fromMatrix(d??{});"
                          "const m=globalThis.document.createElementNS('http://www.w3.org/2000/svg','svg').createSVGMatrix();"
                          "for(const k of ['a','b','c','d','e','f'])m[k]=n[k];"
                          f"return v.{member.name}(m);}})($0,$1)")
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif']
            self.svg_matrix_dictionary_adapters_used.add(matrix_adapter)
        if matrix_adapter in self.world.config.get('browserMatrixFlagAdapters', []):
            if member.kind != 'operation' or member.name != 'toMatrix' or needs_adapter or anonymous_property or member.arguments or self.world.resolve(member.type).name != 'DOMMatrix':
                raise SystemExit(f'{matrix_adapter}: matrix flag adapter requires a plain zero-argument DOMMatrix operation')
            fields = ','.join(f'm.m{column}{row}' for column in range(1, 5) for row in range(1, 5))
            expression = ('((v)=>{const m=v.toMatrix();return v.is2D===false&&m.is2D===true?'
                          f'new m.constructor([{fields}]):m;}})($0)')
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif']
            self.matrix_flag_adapters_used.add(matrix_adapter)
        wide = [i for i, a in enumerate(member.arguments) if self.world.resolve(a.type).name in WIDE_INTEGERS]
        if wide and not needs_adapter and not anonymous_property and not member.arguments[-1].variadic:
            # Fable passes int64 arguments as BigInt, which a browser's number conversion rejects.
            names = [f'a{i}' for i in range(len(member.arguments))]
            passed = [f"{n}===void 0?void 0:Number({n})" if i in wide else n for i, n in enumerate(names)]
            expression = (f"((o,{','.join(names)})=>o.{member.name}({','.join(passed)}))"
                          f"($0,{','.join(f'${i + 1}' for i in range(len(member.arguments)))})")
            lines = ([''] if lines[0] != '' else []) + lines + ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]', '#endif']
        if needs_adapter:
            raw_params = self.parameters(member.arguments, [a.type for a in member.arguments], raw=True)
            raw_result = 'obj' if self.union(member.type) else result
            arg_expressions = [('...' if a.variadic else '') + f'${i + 1}' for i, a in enumerate(member.arguments)]
            expression = f'$0.{member.name}(' + ', '.join(arg_expressions) + ')'
            if anonymous_property:
                expression = self.browser_property_expression(owner, member)
            lines += ['#if FABLE_COMPILER', f'    [<Fable.Core.Emit("{expression}")>]',
                      f'    abstract member __ranvier_{member.name}: {raw_params} -> {raw_result}', '#else']
        for selected in selected_arguments:
            lines += [f'    abstract member {identifier(member.name)}: {self.parameters(member.arguments, selected)} -> {result}']
        if needs_adapter:
            lines += ['#endif']
            self.adapters.append((owner, member))
        if anonymous_property or matrix_adapter in self.generator.svg_matrix_bindings or (wide and not needs_adapter and lines[-1] != ''):
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
        span_unions = set(self.world.config.get('browserWellFormedUnions', []))
        reference_unions = span_unions | set(self.world.config.get('validatedReferenceUnions', []))
        if any(self.world.resolve(child).name == 'undefined' for children in self.unions.values() for child in children):
            lines += ['    [<Fable.Core.Emit("$0 === undefined")>]',
                      '    let private isUndefinedUnionValue (_: obj) : bool =', '        Fable.Core.Util.jsNative', '']
        if any(name in span_unions for name in self.unions):
            lines += ["    [<Fable.Core.Emit(\"((v)=>String(v==null?'null':v).toWellFormed())($0)\")>]",
                      '    let private normalizeUSVString (_: string) : string =', '        Fable.Core.Util.jsNative', '']
        result_interfaces = set()
        for _, member in self.adapters:
            t = self.world.resolve(member.type)
            if self.union(t):
                result_interfaces.update(child.name for child in t.subtypes if self.world.public_name(child.name) in self.names)
        strict_interfaces = {child.name for name, children in self.unions.items() if name in reference_unions
                             for child in children if self.world.public_name(child.name) in self.names}
        result_interfaces.update(strict_interfaces)
        for name in sorted(result_interfaces):
            browser_name = self.world.interfaces[name].attrs.get('InterfaceName', self.world.public_name(name))
            predicate = '$0 != null && $0.nodeType === 1' if name == 'Element' else f'Object.prototype.toString.call($0) === \'[object {browser_name}]\''
            if name == 'CSSStyleValue':
                predicate = ("((v)=>{if(v==null)return false;try{globalThis.CSSStyleValue.prototype.toString.call(v);"
                             "return true;}catch{return false;}})($0)")
            if name == 'CSSNumericValue':
                predicate = ("((v)=>{if(v==null)return false;try{globalThis.CSSNumericValue.prototype.type.call(v);"
                             "return true;}catch{return false;}})($0)")
            if name == 'CSSOMKeywordValue' and name in strict_interfaces:
                predicate = ("((v)=>{if(v==null)return false;try{Object.getOwnPropertyDescriptor("
                             "globalThis.CSSKeywordValue.prototype,'value').get.call(v);"
                             "return true;}catch{return false;}})($0)")
            if name == 'CSSOMVariableReferenceValue' and name in strict_interfaces:
                predicate = ("((v)=>{if(v==null)return false;try{Object.getOwnPropertyDescriptor("
                             "globalThis.CSSVariableReferenceValue.prototype,'variable').get.call(v);"
                             "return true;}catch{return false;} })($0)")
            lines += [f'    [<Fable.Core.Emit("{predicate}")>]',
                      f'    let private is{name} (_: obj) : bool =', '        Fable.Core.Util.jsNative', '']
        for name, children in self.unions.items():
            lines += ['', f'    let private box{name} (value: {name}) : obj =']
            if name in reference_unions:
                lines += ['        if isNull (box value) then', '            nullArg "value"', '']
            lines += ['        match value with']
            for child in children:
                boxed = 'box (normalizeUSVString value)' if name in span_unions and self.world.resolve(child).name == 'USVString' else 'box value'
                if self.world.resolve(child).name == 'undefined':
                    boxed = 'Fable.Core.JsInterop.emitJsExpr () "undefined"'
                resolved = self.world.resolve(child)
                if name in reference_unions and resolved.name in strict_interfaces:
                    lines += [f'        | {name}.{label(child)} value ->',
                              '            if isNull (box value) then', '                nullArg "value"', '',
                              f'            if not (is{resolved.name} (box value)) then',
                              f'                invalidArg "value" "Expected a {self.world.public_name(resolved.name)}."', '',
                              f'            {boxed}']
                else:
                    lines += [f'        | {name}.{label(child)} value -> {boxed}']
            if any(self.union(member.type) and label(self.world.resolve(member.type)) == name for _, member in self.adapters):
                lines += ['', f'    let private unbox{name} (value: obj) : {name} =', '        match value with']
                for child in children:
                    resolved = self.world.resolve(child)
                    ftype = self.type(child)
                    if resolved.name == 'undefined':
                        lines += [f'        | arm when isUndefinedUnionValue arm -> {name}.{label(child)} ()']
                    elif resolved.name in STRINGS or resolved.name in NUMBERS or resolved.name == 'boolean':
                        lines += [f'        | :? {ftype} as arm -> {name}.{label(child)} arm']
                    else:
                        head = f'        | arm when is{resolved.name} arm ->'
                        value = f'{name}.{label(child)} (unbox<{ftype}> arm)'
                        lines += [head, f'            {value}'] if name not in self.world.config.get('validatedReferenceUnions', []) and len(head + ' ' + value) > 120 else [head + ' ' + value]
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
                    if getter and not setter:
                        # A get-only adapter is a property with a body, as Fantomas formats it.
                        lines += [f'        member this.{identifier(member.name)}: {result} =',
                                  f'            let value = this.__ranvier_get_{member.name} ()']
                        if self.world.resolve(member.type).nullable:
                            lines += ['', '            if isNull value then', '                None', '            else',
                                      f'                Some (unbox{union_name} value)']
                        else:
                            lines += [f'            unbox{union_name} value']
                        lines += ['']
                        continue
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
                        setter_head = f'            {"and" if getter else "with"} set (value: {result}) ='
                        lines += [setter_head]
                        if self.world.resolve(member.type).nullable:
                            lines += [f'                this.__ranvier_set_{member.name} (', '                    value',
                                      f'                    |> Option.map box{union_name}', '                    |> Option.defaultValue null', '                )']
                        else:
                            setter_call = f'this.__ranvier_set_{member.name} ({boxed})'
                            if union_name in reference_unions and len(setter_head + ' ' + setter_call) <= 120:
                                lines[-1] += ' ' + setter_call
                            else:
                                lines += [f'                {setter_call}']
                    lines += ['']
                    continue
                for selected in self.choices(member.arguments):
                    declarations, passed, guards = [], [], []
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
                            if self.union(argument.type) and label(self.world.resolve(argument.type)) in span_unions and self.world.resolve(chosen).name == 'USVString':
                                expr = f'box (normalizeUSVString {name})'
                            if self.union(argument.type) and label(self.world.resolve(argument.type)) in reference_unions and self.world.resolve(chosen).name in strict_interfaces:
                                selected_interface = self.world.resolve(chosen).name
                                guards += [f'            if isNull (box {name}) then',
                                           f'                nullArg "{argument.name}"', '',
                                           f'            if not (is{selected_interface} (box {name})) then',
                                           f'                invalidArg "{argument.name}" "Expected a {self.world.public_name(selected_interface)}."', '']
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
                    lines += guards
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

    def shadowed_members(self):
        """Inherited members redeclared by a descendant's browser adapter. F# prefers an intrinsic member to any
        extension, so under Fable such an inherited member is also an extension, which the descendant's overrides."""
        found = set()
        for name in self.names:
            source = self.sources[name]
            if source not in self.world.interfaces or self.world.interfaces[source].mixin:
                continue
            for member in self.world.members(source):
                if member.kind != 'operation' or not self.complex(member) or self.world.contract_owner(source, member) != name:
                    continue
                for ancestor in self.world.chain(source)[1:]:
                    for candidate in self.world.members(ancestor):
                        if candidate.kind == 'operation' and candidate.name == member.name and len(candidate.arguments) == len(member.arguments):
                            owner = self.world.contract_owner(ancestor, candidate)
                            if owner in self.names:
                                found.add((owner, candidate.kind, candidate.name, len(candidate.arguments)))
        return found

    def emit(self):
        for name in self.world.contract_dictionary_fields:
            self.type(idl.Type(name))
        self.shadowed = self.shadowed_members()
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
            if source in self.world.config.get('callbackObjectRoots', {}):
                continue
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
            elif name in self.world.config.get('callbackObjectRoots', {}):
                callback = self.world.config['callbackObjectRoots'][name]
                result = callback['resultEnum']
                declarations.append((name, '', ['    ' + callback['contract']]))
                declarations.append((result['name'], '',
                                     [f'    | {case} = {value}' for case, value in result['cases'].items()]))
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
                elif body == ['    interface end'] or body == ['    class end'] or (attrs == '' and len(body) == 1):
                    lines += [f'{prefix}{" " + attrs if attrs else ""} {name} = {body[0].strip()}']
                    body = []
                else:
                    lines += [f'{prefix}{" " + attrs if attrs else ""} {name} =']
            lines += body + ['']
        lines += self.extensions()
        missing_matrix_adapters = set(self.world.config.get('browserMatrixFlagAdapters', [])) - self.matrix_flag_adapters_used
        if missing_matrix_adapters:
            raise SystemExit(f'configured matrix flag adapters did not match selected operations: {sorted(missing_matrix_adapters)}')
        missing_svg_matrix_adapters = self.generator.svg_matrix_bindings - self.svg_matrix_dictionary_adapters_used
        if missing_svg_matrix_adapters:
            raise SystemExit(f'configured SVG matrix dictionary adapters did not match selected operations: {sorted(missing_svg_matrix_adapters)}')
        return '\n'.join(lines) + '\n'


def emit_interfaces(generator):
    return InterfaceEmitter(generator).emit()
