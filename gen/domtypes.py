"""Owned C transport for mapped Web IDL unions and sequences."""

import re


def token(name):
    name = name.removeprefix('RvDom')
    name = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', name)
    return re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def union_arm_name(mapped):
    if mapped.kind in ('union', 'sequence', 'pair'):
        return mapped.ctype
    return mapped.interface or mapped.enum or mapped.label or mapped.kind


def fsharp_field(ctype):
    """The F# type of a transport field: a pointer is a nativeint, a C scalar its F# scalar."""
    scalar = {'int32_t': 'int', 'uint32_t': 'uint32', 'int16_t': 'int16', 'uint16_t': 'uint16',
              'int8_t': 'sbyte', 'uint8_t': 'byte', 'int64_t': 'int64', 'uint64_t': 'uint64',
              'double': 'float', 'float': 'float32'}
    return 'nativeint' if ctype.endswith('*') else scalar.get(ctype, ctype)


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
        if not input:
            self.mark_result_dictionaries(mapped)
        if mapped.kind not in ('union', 'sequence', 'pair'):
            if mapped.kind == 'dict':
                self.use_dictionary(mapped.interface)
            elif mapped.kind in ('node', 'event', 'object', 'opaque'):
                self.headers.add(f'{mapped.cls}.h')
            elif mapped.kind == 'enum':
                self.enums_used[mapped.enum] = self.world.enums[mapped.enum]
            elif mapped.kind == 'bytes':
                if not input:
                    raise self.unsupported_type(f'{mapped.label} result')
                self.headers.update({'JavaScriptCore/ArrayBuffer.h', 'JavaScriptCore/ArrayBufferView.h'})
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

    def mark_result_dictionaries(self, mapped):
        """Registers each dictionary a result container holds, so the glue emits its owned encoder."""
        if mapped.kind == 'dict':
            self.use_result_dictionary(mapped.interface)
        for child in mapped.subtypes:
            self.mark_result_dictionaries(child)

    def use_result_dictionary(self, name):
        """The C struct of a dictionary returned as an owned, heap-allocated result; registers its nested values."""
        struct = f'RvDom{name}'
        if name in self.result_dicts:
            return struct
        fields = self.use_dictionary(name)
        self.result_dicts[name] = struct
        for member, mapped in fields:
            if mapped.kind in ('node', 'event', 'object', 'opaque', 'enum'):
                raise self.unsupported_type(f'dictionary {name}: {mapped.kind} member {member.name} in a result')
            if mapped.kind in ('union', 'sequence'):
                if not self.transport_can_return(mapped):
                    raise self.unsupported_type(f'dictionary {name}: member {member.name} cannot be returned')
                self.use_complex(mapped, input=False)
            elif mapped.kind == 'dict':
                self.use_result_dictionary(mapped.interface)
        return struct

    def result_dictionary_runtime(self):
        """Forward declarations and definitions of the owned dictionary result encoders and their releases."""
        declarations, definitions = [], []
        if not self.result_dicts:
            return declarations, definitions
        declarations += ['template<typename T> const T* resultField(const T& value) { return &value; }',
                         'template<typename T> const T* resultField(const std::optional<T>& value) { return value ? &*value : nullptr; }',
                         'template<typename V, typename S, typename E> int32_t storeOptionalDictionary(V&& value, S** result, E&& encode)',
                         '{', '    *result = value ? encode(*value) : nullptr;', '    return RV_OK;', '}']
        if self.uses_dictionary_string_spans():
            declarations += ['RvDomUtf8StringInput copyOwnedDomStringInput(const String& value)', '{',
                             '    if (value.isNull()) return { 0, nullptr, 0 };', '    auto utf8 = value.utf8();',
                             '    auto* result = static_cast<uint8_t*>(std::malloc(utf8.length() + 1));',
                             '    RELEASE_ASSERT(result);', '    std::memcpy(result, utf8.data(), utf8.length());',
                             '    result[utf8.length()] = 0;',
                             '    return { 1, result, static_cast<int32_t>(utf8.length()) };', '}']
        for name, struct in self.result_dicts.items():
            cpp = self.dictionary_cpp(name)
            declarations += [f'{struct}* encodeDict{struct}(const {cpp}& value);', f'void releaseDict{struct}({struct}* value);']
            encode = ['', f'{struct}* encodeDict{struct}(const {cpp}& value)', '{',
                      f'    auto* result = static_cast<{struct}*>(std::calloc(1, sizeof({struct})));',
                      '    RELEASE_ASSERT(result);', f'    result->size = sizeof({struct});']
            release = ['', f'void releaseDict{struct}({struct}* value)', '{', '    if (!value) return;']
            for member, mapped in self.dicts_used[name]:
                field = self.result_field_name(member.name)
                cpp_field = member.attrs.get('ImplementedAs', member.name)
                ctype = self.field_ctype(member, mapped, name)
                encode += [f'    if (auto* field = resultField(value.{cpp_field})) {{']
                if mapped.kind == 'string':
                    encode += [f'        result->{field} = copyOwnedDomStringInput(asString(*field));']
                    release += [f'    std::free(const_cast<uint8_t*>(value->{field}.data));']
                elif mapped.kind == 'dict':
                    child = self.result_dicts[mapped.interface]
                    encode += [f'        result->{field} = encodeDict{child}(*field);']
                    release += [f'    releaseDict{child}(const_cast<{child}*>(value->{field}));']
                elif mapped.kind in ('union', 'sequence'):
                    encode += [f'        auto* container = static_cast<{mapped.ctype}*>(std::calloc(1, sizeof({mapped.ctype})));',
                               '        RELEASE_ASSERT(container);', f'        encode{mapped.ctype}(*field, container);',
                               f'        result->{field} = container;']
                    release += [f'    clear{mapped.ctype}(const_cast<{mapped.ctype}*>(value->{field}));',
                                f'    std::free(const_cast<{mapped.ctype}*>(value->{field}));']
                elif ctype.endswith('*'):
                    scalar = ctype.removeprefix('const ').removesuffix('*')
                    encode += [f'        auto* scalar = static_cast<{scalar}*>(std::malloc(sizeof({scalar})));',
                               '        RELEASE_ASSERT(scalar);', f'        *scalar = static_cast<{scalar}>(*field);',
                               f'        result->{field} = scalar;']
                    release += [f'    std::free(const_cast<{scalar}*>(value->{field}));']
                else:
                    encode += [f'        result->{field} = static_cast<{ctype}>(*field);']
                encode += ['    }']
            definitions += encode + ['    return result;', '}'] + release + ['    std::free(value);', '}']
        return declarations, definitions

    def transport_ctype(self, mapped):
        if mapped.kind == 'void':
            return 'int32_t'
        if mapped.kind == 'string':
            if not mapped.string_spans:
                raise SystemExit('a string inside a union or sequence must carry its byte length')
            return 'RvDomUtf8StringSpan'
        if mapped.kind in ('node', 'event', 'object'):
            return f'{mapped.handle}*'
        if mapped.kind == 'opaque':
            return 'void*'
        if mapped.kind == 'bytes':
            return 'RvDomByteSpan'
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
        if kind in ('node', 'event', 'object', 'opaque'):
            return f'{"RefPtr" if mapped.nullable else "Ref"}<{mapped.cls}>'
        if kind == 'bytes':
            return 'Ref<JSC::ArrayBuffer>'
        if kind == 'dict':
            return self.dictionary_cpp(mapped.interface)
        if kind == 'pair':
            return 'KeyValuePair<' + ', '.join(self.transport_cpp(child) for child in mapped.subtypes) + '>'
        if kind == 'union':
            value = 'Variant<' + ', '.join(self.union_alternatives(mapped)[0]) + '>'
        else:
            value = f'Vector<{self.transport_cpp(mapped.subtypes[0])}>'
        return f'std::optional<{value}>' if mapped.nullable else value

    def union_alternatives(self, mapped):
        """The C++ alternatives of a union, and the alternative each arm decodes to. A byte-span arm stands for
        WebKit's flattened BufferSource, ArrayBufferView then ArrayBuffer, and decodes to the ArrayBuffer."""
        alternatives, arms = [], []
        for child in mapped.subtypes:
            if child.kind == 'bytes' and child.label == 'BufferSource':
                arms.append(len(alternatives) + 1)
                alternatives += ['Ref<JSC::ArrayBufferView>', 'Ref<JSC::ArrayBuffer>']
            else:
                arms.append(len(alternatives))
                alternatives.append(self.transport_cpp(child))
        return alternatives, arms

    def contains_bytes(self, mapped):
        return mapped.kind == 'bytes' or any(self.contains_bytes(child) for child in mapped.subtypes)

    def uses_byte_spans(self):
        return any(self.contains_bytes(mapped) for mapped in self.complex_used.values())

    def contains_opaque(self, mapped):
        return mapped.kind == 'opaque' or any(self.contains_opaque(child) for child in mapped.subtypes)

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
        if self.uses_byte_spans():
            lines += ['/* Bytes the callee copies before it returns; data may be NULL when length is 0. */',
                      'typedef struct RvDomByteSpan {', '    const uint8_t* data;',
                      '    int32_t length;', '} RvDomByteSpan;', '']
        for name in self.complex_used:
            lines += [f'typedef struct {name} {name};']
        for name, mapped in self.complex_used.items():
            lines += ['', '/* Inputs borrow their pointers. Results own strings and handle references until the matching release.',
                      ' * present is 0 for null and 1 for a value; an empty sequence has count 0 and items NULL. */']
            if mapped.kind == 'union':
                lines += ['enum {']
                for index, child in enumerate(mapped.subtypes):
                    arm = union_arm_name(child)
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
                    note = f' /* {child.interface}: NULL; the tag identifies the arm */' if child.kind == 'opaque' else ''
                    lines += [f'    {self.transport_ctype(child)} arm{index};{note}']
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
            minimum = -1 if mapped.nullable else 0
            lines = [f'if ({expression}.length < {minimum} || ({expression}.length > 0 && !{expression}.data)) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}',
                     f'String {variable} = {expression}.length < 0 ? String() : {expression}.length ? String::fromUTF8(std::span<const uint8_t> {{ {expression}.data, static_cast<size_t>({expression}.length) }}) : emptyString();',
                     f'if ({expression}.length >= 0 && {variable}.isNull()) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}']
            return lines, variable
        if kind in ('number', 'bool', 'enum'):
            checks = []
            if mapped.finite_input:
                checks = [f'if (!std::isfinite({expression})) {{',
                          '    status = Ranvier::recordException(Exception { ExceptionCode::TypeError, "A finite numeric value is required."_s });',
                          '    return std::nullopt;', '}']
            return checks, f'static_cast<{cpp}>({expression})'
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
        if kind == 'opaque':
            raise self.unsupported_type(f'opaque {mapped.interface} input')
        if kind == 'bytes':
            return [f'if ({expression}.length < 0 || ({expression}.length > 0 && !{expression}.data)) {{ status = RV_ERR_NULL_ARGUMENT; return std::nullopt; }}',
                    f'RefPtr {variable} = JSC::ArrayBuffer::tryCreate({expression}.length ? std::span<const uint8_t> {{ {expression}.data, static_cast<size_t>({expression}.length) }} : std::span<const uint8_t> {{ }});',
                    f'if (!{variable}) {{ status = Ranvier::recordException(Exception {{ ExceptionCode::RangeError, "Out of memory"_s }}); return std::nullopt; }}'], \
                f'{variable}.releaseNonNull()'
        if kind == 'dict':
            fields = self.use_dictionary(mapped.interface)
            lines = [f'{cpp} {variable} {{ }};', f'if ({expression}) {{',
                     '    auto decodeFields = [&]() -> int32_t {']
            for member, child in fields:
                lines += ['        ' + line for line in self.dictionary_field(expression, mapped.handle, variable, member, child, mapped.interface)]
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
        if kind == 'dict':
            return [f'{target} = encodeDict{self.result_dicts[mapped.interface]}({expression});']
        if kind == 'string':
            return [f'{target} = copyOwnedDomStringSpan(asString({expression}));']
        if kind in ('number', 'bool', 'enum'):
            return [f'{target} = static_cast<{self.transport_ctype(mapped)}>({expression});']
        if kind == 'opaque':
            return [f'{target} = nullptr;']
        if kind in ('node', 'event', 'object'):
            root = {'node': 'Node', 'event': 'Event'}.get(kind) or self.world.cpp_class(mapped.root)
            if root in self.tracked_roots:
                return [f'storeTrackedHandle<{root}, {mapped.cls}>({expression}, &{target});']
            return [f'storeHandle<{root}>({expression}, &{target});']
        raise self.unsupported_type(f'{kind} result in a union or sequence')

    def clear_value(self, mapped, expression):
        if mapped.kind in ('union', 'sequence', 'pair'):
            return [f'clear{mapped.ctype}(&{expression});']
        if mapped.kind == 'dict' and mapped.interface in self.result_dicts:
            struct = self.result_dicts[mapped.interface]
            return [f'releaseDict{struct}(const_cast<{struct}*>({expression}));']
        if mapped.kind == 'string':
            return [f'std::free(const_cast<uint8_t*>({expression}.data));']
        if mapped.kind in ('node', 'event', 'object'):
            root = {'node': 'Node', 'event': 'Event'}.get(mapped.kind) or self.world.cpp_class(mapped.root)
            if root in self.tracked_roots:
                return [f'if ({expression}) releaseTrackedHandle(reinterpret_cast<{root}*>({expression}));']
            return [f'if ({expression}) reinterpret_cast<{root}*>({expression})->deref();']
        return []

    def complex_runtime(self):
        if not self.complex_used and not self.result_dicts:
            return []
        dictionary_declarations, dictionary_definitions = self.result_dictionary_runtime()
        lines = ['namespace {',
                 'template<typename T> struct DomSequenceArgument {', '    Vector<T> values;',
                 '    operator Vector<T>() && { return std::move(values); }',
                 '    template<typename U> operator FixedVector<U>() && {',
                 '        Vector<U> converted;', '        converted.reserveInitialCapacity(values.size());',
                 '        for (auto& value : values) {',
                 '            if constexpr (std::is_constructible_v<U, T&&>) converted.append(U { std::move(value) });',
                 '            else converted.append(U { value.get() });', '        }',
                 '        return FixedVector<U> { std::move(converted) };', '    }',
                 '    operator std::optional<Vector<T>>() && { return std::move(values); }', '};']
        lines += dictionary_declarations
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
            if name in self.complex_inputs:
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
                    alternatives, arms = self.union_alternatives(mapped)
                    value_cpp = 'Variant<' + ', '.join(alternatives) + '>'
                    lines += ['    switch (source->tag) {']
                    for index, child in enumerate(mapped.subtypes):
                        decoded, value = self.decode_value(child, f'source->arm{index}', f'arm{index}')
                        lines += [f'    case {index + 1}: {{'] + ['        ' + line for line in decoded]
                        lines += [f'        return {cpp} {{ {value_cpp} {{ WTF::InPlaceIndex<{arms[index]}>, {value} }} }};', '    }']
                    lines += ['    default: status = RV_ERR_UNSUPPORTED; return std::nullopt;', '    }', '}']
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
        return lines + dictionary_definitions + ['}']

    def transport_can_return(self, mapped):
        if mapped.kind == 'bytes':
            return False
        if mapped.kind == 'dict' and mapped.interface not in self.world.config.get('resultDictionaries', []):
            return False
        return all(self.transport_can_return(child) for child in mapped.subtypes)

    def complex_fsharp(self):
        lines = []
        if self.uses_complex_string_spans():
            lines += ['', '/// <summary>Length-delimited UTF-8; compound results own data until their matching release call.</summary>',
                      '[<Struct; StructLayout(LayoutKind.Sequential)>]', 'type RvDomUtf8StringSpan =',
                      '    val mutable data: nativeint', '    val mutable length: int']
        if self.uses_byte_spans():
            lines += ['', '/// <summary>Bytes the callee copies before it returns.</summary>',
                      '[<Struct; StructLayout(LayoutKind.Sequential)>]', 'type RvDomByteSpan =',
                      '    val mutable data: nativeint', '    val mutable length: int']
        for name, mapped in self.complex_used.items():
            if mapped.kind == 'union':
                for index, child in enumerate(mapped.subtypes):
                    arm = union_arm_name(child)
                    constant = f'RV_DOM_{token(name).upper()}_{token(arm).upper()}'
                    lines += ['', '[<Literal>]', f'let {constant} = {index + 1}']
            lines += ['', f'/// <summary>ABI transport for {mapped.label}; result contents are owned until the matching release call.</summary>',
                      '[<Struct; StructLayout(LayoutKind.Sequential)>]', f'type {name} =', '    val mutable present: int']
            if mapped.kind == 'sequence':
                lines += ['    val mutable count: int', '    val mutable items: nativeint']
            elif mapped.kind == 'pair':
                lines += [f'    val mutable key: {fsharp_field(self.transport_ctype(mapped.subtypes[0]))}',
                          f'    val mutable value: {fsharp_field(self.transport_ctype(mapped.subtypes[1]))}']
            else:
                lines += ['    val mutable tag: int']
                for index, child in enumerate(mapped.subtypes):
                    lines += [f'    val mutable arm{index}: {fsharp_field(self.transport_ctype(child))}']
        for name in self.complex_used:
            lines += ['', '[<DllImport(Lib)>]', f'extern void rv_dom_{token(name)}_release({name}& value)']
        return lines
