"""Owned C transport for mapped Web IDL unions and sequences."""

import re


def token(name):
    name = name.removeprefix('RvDom')
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()


class ComplexGeneratorMixin:
    def complex_default(self, mapped, value):
        cpp = self.transport_cpp(mapped)
        if mapped.kind == 'sequence':
            return f'{cpp} {{ }}'
        for index, child in enumerate(mapped.subtypes):
            if value == '{}' and child.kind == 'dict':
                return f'{cpp} {{ WTF::InPlaceIndex<{index}>, {self.transport_cpp(child)} {{ }} }}'
            if value in ('true', 'false') and child.kind == 'bool':
                return f'{cpp} {{ WTF::InPlaceIndex<{index}>, {value} }}'
        return f'{cpp} {{ }}'

    def use_complex(self, mapped, input=True):
        if mapped.kind not in ('union', 'sequence', 'pair'):
            if mapped.kind == 'dict':
                self.use_dictionary(mapped.interface)
            elif mapped.kind in ('node', 'event', 'object'):
                self.headers.add(f'{mapped.cls}.h')
            elif mapped.kind == 'enum':
                self.enums_used[mapped.enum] = self.world.enums[mapped.enum]
            return
        if mapped.kind == 'pair':
            self.headers.add('wtf/KeyValuePair.h')
        newly_input = input and mapped.ctype not in self.complex_inputs
        if input:
            self.complex_inputs.add(mapped.ctype)
        if mapped.ctype in self.complex_used:
            if newly_input:
                for child in mapped.subtypes:
                    self.use_complex(child, input=True)
            return
        for child in mapped.subtypes:
            self.use_complex(child, input=input)
        self.complex_used[mapped.ctype] = mapped

    def transport_ctype(self, mapped):
        if mapped.kind == 'void':
            return 'int32_t'
        if mapped.kind == 'string':
            return 'RvDomUtf8StringSpan' if mapped.string_spans else 'const char*'
        if mapped.kind in ('node', 'event', 'object'):
            return f'{mapped.handle}*'
        if mapped.kind == 'dict':
            return f'const {mapped.handle}*'
        if mapped.kind in ('union', 'sequence', 'pair'):
            return mapped.ctype
        return mapped.ctype

    def transport_cpp(self, mapped):
        kind = mapped.kind
        if kind == 'void':
            return 'std::monostate'
        if kind == 'string':
            return 'String'
        if kind == 'bool':
            return 'bool'
        if kind == 'number':
            return mapped.ctype
        if kind == 'enum':
            return mapped.enum
        if kind in ('node', 'event', 'object'):
            return f'{"RefPtr" if mapped.nullable else "Ref"}<{mapped.cls}>'
        if kind == 'dict':
            return self.dictionary_cpp(mapped.interface)
        if kind == 'pair':
            return 'KeyValuePair<' + ', '.join(self.transport_cpp(child) for child in mapped.subtypes) + '>'
        if kind == 'union':
            value = 'Variant<' + ', '.join(self.transport_cpp(child) for child in mapped.subtypes) + '>'
        else:
            value = f'Vector<{self.transport_cpp(mapped.subtypes[0])}>'
        return f'std::optional<{value}>' if mapped.nullable else value

    def contains_string_spans(self, mapped):
        return mapped.kind == 'string' and mapped.string_spans or any(self.contains_string_spans(child) for child in mapped.subtypes)

    def uses_complex_string_spans(self):
        return any(self.contains_string_spans(mapped) for mapped in self.complex_used.values())

    def transport_structs(self):
        lines = []
        if self.uses_complex_string_spans():
            lines += ['/* UTF-8 byte length; -1 is null where permitted. Compound results own data until release. */',
                      'typedef struct RvDomUtf8StringSpan {', '    const uint8_t* data;',
                      '    int32_t length;', '} RvDomUtf8StringSpan;', '']
        for name in self.complex_used:
            lines += [f'typedef struct {name} {name};']
        for name, mapped in self.complex_used.items():
            lines += ['', '/* Inputs borrow their pointers. Results own strings and handle references until the matching release.',
                      ' * present is 0 for null and 1 for a value; an empty sequence has count 0 and items NULL. */']
            if mapped.kind == 'union':
                lines += ['enum {']
                for index, child in enumerate(mapped.subtypes):
                    arm = child.interface or child.enum or child.label or child.kind
                    lines += [f'    RV_DOM_{token(name).upper()}_{token(arm).upper()} = {index + 1},']
                lines += ['};']
            lines += [f'struct {name} {{', '    int32_t present;']
            if mapped.kind == 'sequence':
                lines += ['    int32_t count;', f'    {self.transport_ctype(mapped.subtypes[0])}* items;']
            elif mapped.kind == 'pair':
                lines += [f'    {self.transport_ctype(mapped.subtypes[0])} key;',
                          f'    {self.transport_ctype(mapped.subtypes[1])} value;']
            else:
                lines += ['    int32_t tag;']
                for index, child in enumerate(mapped.subtypes):
                    lines += [f'    {self.transport_ctype(child)} arm{index};']
            lines += ['};']
        return lines

    def complex_release_declarations(self, prefix, export):
        return [f'{export} void {prefix}{token(name)}_release({name}* value);' for name in self.complex_used]

    def decode_value(self, mapped, expression, variable):
        cpp = self.transport_cpp(mapped)
        kind = mapped.kind
        if kind == 'void':
            return [f'if ({expression} != 0) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}'], 'std::monostate { }'
        if kind in ('union', 'sequence', 'pair'):
            return [f'auto {variable} = decode{mapped.ctype}(&{expression}, status);',
                    'if (status != RV_OK) return std::nullopt;'], f'std::move(*{variable})'
        if kind == 'string':
            if mapped.string_spans:
                minimum = -1 if mapped.nullable else 0
                lines = [f'if ({expression}.length < {minimum} || ({expression}.length > 0 && !{expression}.data)) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}',
                         f'String {variable} = {expression}.length < 0 ? String() : {expression}.length ? String::fromUTF8(std::span<const uint8_t> {{ {expression}.data, static_cast<size_t>({expression}.length) }}) : emptyString();',
                         f'if ({expression}.length >= 0 && {variable}.isNull()) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}']
                return lines, variable
            checks = [] if mapped.nullable else [f'if (!{expression}) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}']
            return checks, f'String::fromUTF8({expression})'
        if kind in ('number', 'bool', 'enum'):
            return [], f'static_cast<{cpp}>({expression})'
        if kind in ('node', 'event', 'object'):
            if mapped.interface == 'EventTarget':
                return [f'storeNode(dynamicDowncast<Node>(rawPointer<EventTarget>({expression})), &{target});']
            root = {'node': 'Node', 'event': 'Event'}.get(kind) or self.world.cpp_class(mapped.root)
            pointer = f'reinterpret_cast<{root}*>({expression})'
            lines = []
            if not mapped.nullable:
                lines += [f'if (!{expression}) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}']
            converted = pointer if root == mapped.cls else f'{expression} ? {self.cast_expression(mapped.cls, root, "*" + pointer)} : nullptr'
            lines += [f'RefPtr<{mapped.cls}> {variable} = {converted};',
                      f'if ({expression} && !{variable}) {{ status = RV_ERR_WRONG_INTERFACE; return std::nullopt; }}']
            return lines, f'{cpp} {{ {variable}.get() }}' if mapped.nullable else f'Ref {{ *{variable} }}'
        if kind == 'dict':
            fields = self.use_dictionary(mapped.interface)
            lines = [f'{cpp} {variable} {{ }};', f'if ({expression}) {{',
                     '    auto decodeFields = [&]() -> int32_t {']
            for member, child in fields:
                lines += ['        ' + line for line in self.dictionary_field(expression, mapped.handle, variable, member, child)]
            lines += ['        return RV_OK;', '    };', '    status = decodeFields();',
                      '    if (status != RV_OK) return std::nullopt;', '}']
            return lines, f'std::move({variable})'
        raise ValueError(kind)

    def encode_value(self, mapped, expression, target):
        kind = mapped.kind
        if kind == 'void':
            return [f'{target} = 0;']
        if kind in ('union', 'sequence', 'pair'):
            return [f'encode{mapped.ctype}({expression}, &{target});']
        if kind == 'string':
            if mapped.string_spans:
                return [f'{target} = copyOwnedDomStringSpan(asString({expression}));']
            return [f'{target} = copyOwnedDomString(asString({expression}));']
        if kind in ('number', 'bool', 'enum'):
            return [f'{target} = static_cast<{self.transport_ctype(mapped)}>({expression});']
        if kind in ('node', 'event', 'object'):
            root = {'node': 'Node', 'event': 'Event'}.get(kind) or self.world.cpp_class(mapped.root)
            return [f'storeHandle<{root}>({expression}, &{target});']
        raise self.unsupported_type(f'{kind} result in a union or sequence')

    def clear_value(self, mapped, expression):
        if mapped.kind in ('union', 'sequence', 'pair'):
            return [f'clear{mapped.ctype}(&{expression});']
        if mapped.kind == 'string':
            if mapped.string_spans:
                return [f'std::free(const_cast<uint8_t*>({expression}.data));']
            return [f'std::free(const_cast<char*>({expression}));']
        if mapped.kind in ('node', 'event', 'object'):
            root = {'node': 'Node', 'event': 'Event'}.get(mapped.kind) or self.world.cpp_class(mapped.root)
            return [f'if ({expression}) reinterpret_cast<{root}*>({expression})->deref();']
        return []

    def complex_runtime(self):
        if not self.complex_used:
            return []
        lines = ['namespace {',
                 'char* copyOwnedDomString(const String& value)', '{',
                 '    if (value.isNull()) return nullptr;',
                 '    auto utf8 = value.utf8();', '    auto* result = static_cast<char*>(std::malloc(utf8.length() + 1));',
                 '    RELEASE_ASSERT(result);', '    std::memcpy(result, utf8.data(), utf8.length());',
                 '    result[utf8.length()] = 0;', '    return result;', '}',
                 'template<typename T> struct DomSequenceArgument {', '    Vector<T> values;',
                 '    operator Vector<T>() && { return std::move(values); }',
                 '    template<typename U> operator FixedVector<U>() && {',
                 '        Vector<U> converted;', '        converted.reserveInitialCapacity(values.size());',
                 '        for (auto& value : values) {',
                 '            if constexpr (std::is_constructible_v<U, T&&>) converted.append(U { std::move(value) });',
                 '            else converted.append(U { value.get() });', '        }',
                 '        return FixedVector<U> { std::move(converted) };', '    }',
                 '    operator std::optional<Vector<T>>() && { return std::move(values); }', '};']
        if self.uses_complex_string_spans():
            lines += ['RvDomUtf8StringSpan copyOwnedDomStringSpan(const String& value)', '{',
                      '    if (value.isNull()) return { nullptr, -1 };',
                      '    auto utf8 = value.utf8();',
                      '    auto* result = static_cast<uint8_t*>(std::malloc(utf8.length() + 1));',
                      '    RELEASE_ASSERT(result);', '    std::memcpy(result, utf8.data(), utf8.length());',
                      '    result[utf8.length()] = 0;',
                      '    return { result, static_cast<int32_t>(utf8.length()) };', '}']
        for name, mapped in self.complex_used.items():
            cpp = self.transport_cpp(mapped)
            decoder_start = len(lines)
            lines += ['', f'std::optional<{cpp}> decode{name}(const {name}* source, int32_t& status)', '{']
            if self.contains_string_spans(mapped):
                lines += ['    if (source && source->present != 0 && source->present != 1) { status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }']
            if mapped.nullable:
                lines += [f'    if (!source || !source->present) return std::optional<{cpp}> {{ std::in_place, std::nullopt }};']
            else:
                lines += ['    if (!source || !source->present) { status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }']
            if mapped.kind == 'sequence':
                element = mapped.subtypes[0]
                value_cpp = f'Vector<{self.transport_cpp(element)}>'
                lines += ['    if (source->count < 0 || (source->count && !source->items)) { status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }',
                          f'    {value_cpp} result;', '    result.reserveInitialCapacity(source->count);',
                          '    for (int32_t i = 0; i < source->count; ++i) {']
                decoded, value = self.decode_value(element, 'source->items[i]', 'item')
                lines += ['        ' + line for line in decoded] + [f'        result.append({value});', '    }',
                          f'    return {cpp} {{ std::move(result) }};', '}']
            elif mapped.kind == 'pair':
                for index, field in enumerate(['key', 'value']):
                    decoded, value = self.decode_value(mapped.subtypes[index], f'source->{field}', field)
                    lines += ['    ' + line for line in decoded]
                    lines += [f'    auto decoded{index} = {value};']
                lines += [f'    return {cpp} {{ std::move(decoded0), std::move(decoded1) }};', '}']
            else:
                value_cpp = 'Variant<' + ', '.join(self.transport_cpp(child) for child in mapped.subtypes) + '>'
                lines += ['    switch (source->tag) {']
                for index, child in enumerate(mapped.subtypes):
                    decoded, value = self.decode_value(child, f'source->arm{index}', f'arm{index}')
                    lines += [f'    case {index + 1}: {{'] + ['        ' + line for line in decoded]
                    lines += [f'        return {cpp} {{ {value_cpp} {{ WTF::InPlaceIndex<{index}>, {value} }} }};', '    }']
                lines += ['    default: status = RV_ERR_UNSUPPORTED; return std::nullopt;', '    }', '}']
            if name not in self.complex_inputs:
                del lines[decoder_start:]
            lines += ['', f'void clear{name}({name}* value)', '{', '    if (!value) return;']
            if mapped.kind == 'sequence':
                lines += ['    for (int32_t i = 0; i < value->count; ++i) {']
                lines += ['        ' + line for line in self.clear_value(mapped.subtypes[0], 'value->items[i]')]
                lines += ['    }', '    std::free(value->items);']
            elif mapped.kind == 'pair':
                for index, field in enumerate(['key', 'value']):
                    lines += ['    ' + line for line in self.clear_value(mapped.subtypes[index], f'value->{field}')]
            else:
                lines += ['    switch (value->tag) {']
                for index, child in enumerate(mapped.subtypes):
                    lines += [f'    case {index + 1}:'] + ['        ' + line for line in self.clear_value(child, f'value->arm{index}')]
                    lines += ['        break;']
                lines += ['    }']
            lines += ['    *value = { };', '}']
            if not self.transport_can_return(mapped):
                continue
            if mapped.kind == 'union':
                lines += [f'template<size_t I = 0, typename V> void encodeArms{name}(V&& value, {name}* result)', '{',
                          f'    if constexpr (I < {len(mapped.subtypes)}) {{', '        if (value.index() == I) {']
                for index, child in enumerate(mapped.subtypes):
                    lines += [f'            {"if" if index == 0 else "else if"} constexpr (I == {index}) {{']
                    lines += ['                ' + line for line in self.encode_value(child, 'std::get<I>(value)', f'result->arm{index}')]
                    lines += ['            }']
                lines += ['        } else encodeArms' + name + '<I + 1>(std::forward<V>(value), result);', '    }', '}']
            lines += [f'template<typename V> int32_t encode{name}(V&& input, {name}* result)', '{', '    *result = { };']
            if mapped.nullable:
                lines += ['    if (!input) return RV_OK;', '    auto&& value = *input;']
            else:
                lines += ['    auto&& value = input;']
            lines += ['    result->present = 1;']
            if mapped.kind == 'sequence':
                ctype = self.transport_ctype(mapped.subtypes[0])
                lines += ['    result->count = static_cast<int32_t>(value.size());',
                          f'    result->items = value.size() ? static_cast<{ctype}*>(std::calloc(value.size(), sizeof({ctype}))) : nullptr;',
                          '    RELEASE_ASSERT(!value.size() || result->items);',
                          '    for (int32_t i = 0; i < result->count; ++i) {']
                lines += ['        ' + line for line in self.encode_value(mapped.subtypes[0], 'value[i]', 'result->items[i]')]
                lines += ['    }']
            elif mapped.kind == 'pair':
                for index, field in enumerate(['key', 'value']):
                    lines += ['    ' + line for line in self.encode_value(mapped.subtypes[index], f'value.{field}', f'result->{field}')]
            else:
                lines += ['    result->tag = static_cast<int32_t>(value.index()) + 1;', f'    encodeArms{name}(value, result);']
            lines += ['    return RV_OK;', '}']
        return lines + ['}']

    def transport_can_return(self, mapped):
        return mapped.kind != 'dict' and all(self.transport_can_return(child) for child in mapped.subtypes)

    def complex_fsharp(self):
        lines = []
        if self.uses_complex_string_spans():
            lines += ['', '/// <summary>Length-delimited UTF-8; compound results own data until their matching release call.</summary>',
                      '[<Struct; StructLayout(LayoutKind.Sequential)>]', 'type RvDomUtf8StringSpan =',
                      '    val mutable data: nativeint', '    val mutable length: int']
        for name, mapped in self.complex_used.items():
            if mapped.kind == 'union':
                for index, child in enumerate(mapped.subtypes):
                    arm = child.interface or child.enum or child.label or child.kind
                    constant = f'RV_DOM_{token(name).upper()}_{token(arm).upper()}'
                    lines += ['', '[<Literal>]', f'let {constant} = {index + 1}']
            lines += ['', f'/// <summary>ABI transport for {mapped.label}; result contents are owned until the matching release call.</summary>',
                      '[<Struct; StructLayout(LayoutKind.Sequential)>]', f'type {name} =', '    val mutable present: int']
            if mapped.kind == 'sequence':
                lines += ['    val mutable count: int', '    val mutable items: nativeint']
            elif mapped.kind == 'pair':
                lines += [f'    val mutable key: {self.transport_ctype(mapped.subtypes[0])}',
                          f'    val mutable value: {self.transport_ctype(mapped.subtypes[1])}']
            else:
                lines += ['    val mutable tag: int']
                for index, child in enumerate(mapped.subtypes):
                    ctype = self.transport_ctype(child)
                    scalar = {'int32_t': 'int', 'uint32_t': 'uint32', 'int16_t': 'int16', 'uint16_t': 'uint16',
                              'int8_t': 'sbyte', 'uint8_t': 'byte', 'int64_t': 'int64', 'uint64_t': 'uint64',
                              'double': 'float', 'float': 'float32'}
                    lines += [f'    val mutable arm{index}: {"nativeint" if ctype.endswith("*") else scalar.get(ctype, ctype)}']
        for name in self.complex_used:
            lines += ['', '[<DllImport(Lib)>]', f'extern void rv_dom_{token(name)}_release({name}& value)']
        return lines
