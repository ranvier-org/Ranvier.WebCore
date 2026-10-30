import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'gen'))
import domgen


IDL = '''
enum Mode { "open", "closed" };
dictionary ProbeOptions { boolean enabled = true; DOMString label; };
dictionary EventListenerOptions { boolean capture = false; };
dictionary AddEventListenerOptions : EventListenerOptions {
    boolean passive; boolean once = false; Outside signal; boolean webkitTrustedOnly = false;
};
interface EventTarget {
    undefined addEventListener(DOMString type, EventListener? listener, optional (AddEventListenerOptions or boolean) options = false);
    undefined removeEventListener(DOMString type, EventListener? listener, optional (EventListenerOptions or boolean) options = false);
    boolean dispatchEvent(Event event);
};
callback EventListener = undefined(Event event);
interface Event { readonly attribute DOMString type; };
interface Node : EventTarget {
    [CustomGetter] readonly attribute unsigned short nodeType;
    [CustomGetter] attribute DOMString writeOnly;
    boolean checkOptions(optional ProbeOptions options = {});
    readonly attribute Mode mode;
    attribute (boolean or DOMString) state;
    undefined append((Node or DOMString)... nodes);
    sequence<DOMString> labels();
    sequence<Node> descendants();
    undefined take(sequence<Node> nodes);
};
dictionary ElementCreationOptions { DOMString is; };
interface mixin AriaAttributes { attribute DOMString ariaLabel; };
interface mixin ParentNode { undefined replaceChildren((Node or DOMString)... nodes); };
interface Element : Node { attribute DOMString id; };
Element includes AriaAttributes;
Element includes ParentNode;
interface HTMLElement : Element {};
interface HTMLMediaElement : HTMLElement { undefined play(); };
interface HTMLAudioElement : HTMLMediaElement {};
interface HTMLHeadingElement : HTMLElement {};
interface SVGElement : Element {};
interface SVGSVGElement : SVGElement {};
dictionary ImportNodeOptions { boolean selfOnly = false; Outside customElementRegistry; };
interface Document : Node {
    readonly attribute DOMImplementation implementation;
    Element createElementNS(DOMString? namespaceURI, DOMString name, optional (DOMString or ElementCreationOptions) options = {});
    Node importNode(Node node, optional (boolean or ImportNodeOptions) options = false);
};
interface HTMLDocument : Document {};
interface DOMImplementation { HTMLDocument createHTMLDocument(optional DOMString title); };
interface DOMStringMap { getter DOMString (DOMString name); setter undefined (DOMString name, DOMString value); };
'''


class GeneratorTests(unittest.TestCase):
    def test_configured_geometry_factories_mutation_and_quad_copies_use_engine_operations(self):
        configured = json.loads((ROOT / 'gen/dom.json').read_text())
        selected = ['DOMRectReadOnly', 'DOMRect', 'DOMPointReadOnly', 'DOMPoint', 'DOMQuad']
        self.assertTrue(set(selected).issubset(configured['interfaces']))
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
dictionary DOMRectInit { unrestricted double x = 0; unrestricted double y = 0; unrestricted double width = 0; unrestricted double height = 0; };
dictionary DOMPointInit { unrestricted double x = 0; unrestricted double y = 0; unrestricted double z = 0; unrestricted double w = 1; };
dictionary DOMQuadInit {
    [ImplementationDefaultValue={}] DOMPointInit p1;
    [ImplementationDefaultValue={}] DOMPointInit p2;
    [ImplementationDefaultValue={}] DOMPointInit p3;
    [ImplementationDefaultValue={}] DOMPointInit p4;
};
interface DOMRectReadOnly {
    constructor(optional unrestricted double x = 0, optional unrestricted double y = 0, optional unrestricted double width = 0, optional unrestricted double height = 0);
    static DOMRectReadOnly fromRect(optional DOMRectInit other = {});
    readonly attribute unrestricted double x;
};
interface DOMRect : DOMRectReadOnly {
    constructor(optional unrestricted double x = 0, optional unrestricted double y = 0, optional unrestricted double width = 0, optional unrestricted double height = 0);
    static DOMRect fromRect(optional DOMRectInit other = {});
    inherit attribute unrestricted double x;
};
interface DOMPointReadOnly {
    constructor(optional unrestricted double x = 0, optional unrestricted double y = 0, optional unrestricted double z = 0, optional unrestricted double w = 1);
    static DOMPointReadOnly fromPoint(optional DOMPointInit other = {});
    readonly attribute unrestricted double w;
};
interface DOMPoint : DOMPointReadOnly {
    constructor(optional unrestricted double x = 0, optional unrestricted double y = 0, optional unrestricted double z = 0, optional unrestricted double w = 1);
    static DOMPoint fromPoint(optional DOMPointInit other = {});
    inherit attribute unrestricted double w;
};
interface DOMQuad {
    constructor(optional DOMPointInit p1 = {}, optional DOMPointInit p2 = {}, optional DOMPointInit p3 = {}, optional DOMPointInit p4 = {});
    static DOMQuad fromRect(optional DOMRectInit other = {});
    static DOMQuad fromQuad(optional DOMQuadInit other = {});
    [SameObject] readonly attribute DOMPoint p1;
    DOMRect getBounds();
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + selected
        config['constructors'] = {name: configured['constructors'][name] for name in selected}
        config['staticBindings'] = {name: configured['staticBindings'][name] for name in selected}
        config['trackedHandleRoots'] = configured['trackedHandleRoots']
        config['nestedDictionaries'] = configured['nestedDictionaries']
        config['runtimeTypeRoots'] = list(config['trackedHandleRoots'])
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        for name in selected:
            self.assertIn('rv_dom_' + domgen.snake(name) + '_create', functions)
        for name, operation in [('DOMRect', 'from_rect'), ('DOMRectReadOnly', 'from_rect'),
                                ('DOMPoint', 'from_point'), ('DOMPointReadOnly', 'from_point'),
                                ('DOMQuad', 'from_rect'), ('DOMQuad', 'from_quad')]:
            self.assertIn('rv_dom_' + domgen.snake(name) + '_' + operation, functions)
        self.assertIn('rv_dom_dom_rect_set_x', functions)
        self.assertIn('rv_dom_dom_point_set_w', functions)
        self.assertNotIn('rv_dom_dom_rect_read_only_set_x', functions)
        self.assertNotIn('rv_dom_dom_point_read_only_set_w', functions)
        glue = generator.glue()
        self.assertIn('DOMQuad::create(std::move(a0), std::move(a1), std::move(a2), std::move(a3))', glue)
        self.assertIn('DOMQuad::fromQuad(std::move(a0))', glue)
        self.assertIn('impl->getBounds()', glue)
        geometry_bodies = '\n'.join('\n'.join(function.body) for function in generator.functions if function.interface in selected)
        self.assertNotIn('std::isfinite', geometry_bodies)

    def test_tracked_geometry_handles_classify_only_trusted_mutable_producers_and_pair_releases(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface DOMRectReadOnly { readonly attribute unrestricted double x; };
interface DOMRect : DOMRectReadOnly { attribute unrestricted double x; };
partial interface Node {
    DOMRect makeRect();
    DOMRectReadOnly makeReadOnlyRect();
    sequence<DOMRect> rects();
    undefined takeRect(DOMRect rect);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['DOMRectReadOnly', 'DOMRect']
        config['trackedHandleRoots'] = {'DOMRectReadOnly': 'DOMRect'}
        config['runtimeTypeRoots'] = ['DOMRectReadOnly']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        self.assertIn('storeTrackedHandle<DOMRectReadOnly, DOMRect>(value, result)', glue)
        self.assertIn('storeTrackedHandle<DOMRectReadOnly, DOMRectReadOnly>(value, result)', glue)
        self.assertIn('storeTrackedHandle<DOMRectReadOnly, DOMRect>(value[i], &result->items[i])', glue)
        self.assertIn('castTrackedHandle<DOMRect>(*reinterpret_cast<DOMRectReadOnly*>(target))', glue)
        self.assertIn('retainTrackedHandle(reinterpret_cast<DOMRectReadOnly*>(handle))', glue)
        self.assertIn('releaseTrackedHandle(reinterpret_cast<DOMRectReadOnly*>(handle))', glue)
        self.assertIn('releaseTrackedHandle(reinterpret_cast<DOMRectReadOnly*>(value->items[i]))', glue)
        self.assertNotIn('dynamicDowncast<DOMRect>', glue)
        self.assertIn('auto found = handles.find(&value);', glue)
        self.assertIn('found->second.mutableType', glue)
        self.assertIn('if (!--found->second.references)', glue)
        self.assertIn('handles.erase(found);', glue)
        self.assertIn('const_cast<Root*>(static_cast<const Root*>(concrete))', glue)
        self.assertIn('static_assert(std::is_same_v<Concrete, Root> || std::is_same_v<Concrete, Mutable>);', glue)

    def test_opted_in_nested_geometry_dictionary_preserves_defaults_and_input_layouts(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
dictionary DOMPointInit { unrestricted double x = 0; unrestricted double w = 1; };
dictionary DOMQuadInit { DOMPointInit p1 = {}; DOMPointInit p2 = {}; };
partial interface Node { undefined takeQuad(optional DOMQuadInit quad = {}); };
''')
        config = dict(self.world.config)
        config['nestedDictionaries'] = ['DOMQuadInit']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        functions = {item['function']: item for item in model['functions']}
        self.assertIn('rv_dom_node_take_quad', functions)
        self.assertEqual([field['ctype'] for field in model['dictionaries']['DOMQuadInit']],
                         ['const RvDomDOMPointInit*', 'const RvDomDOMPointInit*'])
        self.assertEqual([field['default'] for field in model['dictionaries']['DOMPointInit']], ['0', '1'])
        self.assertIn('const char* label;', generator.header())
        self.assertLess(generator.header().index('typedef struct RvDomDOMPointInit {'),
                        generator.header().index('typedef struct RvDomDOMQuadInit {'))
        glue = generator.glue()
        self.assertIn('DOMQuadInit a0 { };', glue)
        self.assertIn('const auto* nested_a0_p1 = quad->p1;', glue)
        self.assertIn('offsetof(RvDomDOMPointInit, w)', glue)
        self.assertIn('assignValue(a0.p1.w, nested_a0_p1->w)', glue)
        self.assertIn('val mutable p1: nativeint', generator.fsharp())

    def test_nested_dictionary_transport_rejects_presence_semantics_it_cannot_represent(self):
        for member in ['DOMPointInit p1;', 'required DOMPointInit p1;', 'DOMPointInit? p1 = null;']:
            with self.subTest(member=member):
                fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
                fixture.write_text(IDL + '''
dictionary DOMPointInit { unrestricted double w = 1; };
dictionary DOMQuadInit { ''' + member + ''' };
partial interface Node { undefined takeQuad(optional DOMQuadInit quad = {}); };
''')
                config = dict(self.world.config)
                config['nestedDictionaries'] = ['DOMQuadInit']
                generator = domgen.Generator(domgen.World(self.source, config))
                generator.lock = {}
                generator.lock_structs = {}
                generator.run()
                functions = [item['function'] for item in json.loads(generator.api_model())['functions']]
                self.assertNotIn('rv_dom_node_take_quad', functions)
                self.assertIn('requires an opted-in nonnullable empty default', generator.report())

    def test_selected_variadic_style_values_validate_reference_arms_before_webidl_coercion(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface StylePropertyMap { undefined set(USVString property, (CSSStyleValue or USVString)... values); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'StylePropertyMap']
        config['complexStringSpans'] = ['CSSStyleValueOrUSVString']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        interfaces = generator.interfaces()
        self.assertTrue('if isNull (box value) then\n            nullArg "value"' in interfaces)
        self.assertTrue('if not (isCSSStyleValue (box value)) then' in interfaces)
        self.assertTrue('invalidArg "value" "Expected a CSSStyleValue."' in interfaces)
        self.assertTrue('CSSStyleValueOrUSVString.USVString value -> box (normalizeUSVString value)' in interfaces)

    def test_configured_iterable_snapshot_owns_keys_and_nullable_value_arrays(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface StylePropertyMapReadOnly {
    iterable<USVString, sequence<CSSStyleValue?>>;
    readonly attribute unsigned long size;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'StylePropertyMapReadOnly']
        config['objectContexts'] = {'StylePropertyMapReadOnly': 'Document'}
        config['complexNullableElements'] = ['CSSStyleValue']
        config['iterableBindings'] = {'StylePropertyMapReadOnly': {'feature': 'dom-css-style-map-entries'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        function = next(item for item in generator.functions if item.name == 'style_property_map_read_only_entries')
        self.assertEqual('iterator_snapshot', function.kind)
        self.assertEqual([('RvStylePropertyMapReadOnly*', 'target'), ('RvNode*', 'context')], function.params[:2])
        self.assertEqual('pair', function.returns.subtypes[0].kind)
        pair = function.returns.subtypes[0]
        self.assertTrue(pair.subtypes[0].string_spans)
        self.assertTrue(pair.subtypes[1].subtypes[0].nullable)
        glue = generator.glue()
        self.assertTrue('impl->createIterator(&document.get())' in glue)
        self.assertTrue('entries.append(WTF::move(*entry))' in glue)
        self.assertTrue('value.key' in glue and 'value.value' in glue)
        self.assertTrue('std::free(const_cast<uint8_t*>(value->key.data))' in glue)
        self.assertTrue('clearRvDomSequenceCSSStyleValueNullableElement(&value->value)' in glue)
        self.assertNotIn('abstract member entries', generator.interfaces())
        model = json.loads(generator.api_model())
        operation = next(item for item in model['functions'] if item['function'] == 'rv_dom_style_property_map_read_only_entries')
        self.assertEqual('facade', operation['binding'])
        self.assertEqual('iterable', operation['sourceKind'])

    def test_selected_nullable_sequence_elements_do_not_reuse_the_nonnullable_container(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
partial interface Node {
    sequence<CSSStyleValue> values();
    sequence<CSSStyleValue?> nullableValues();
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue']
        config['complexNullableElements'] = ['CSSStyleValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        plain = next(item.returns for item in generator.functions if item.name == 'node_values')
        nullable = next(item.returns for item in generator.functions if item.name == 'node_nullable_values')
        self.assertEqual('RvDomSequenceCSSStyleValue', plain.ctype)
        self.assertEqual('RvDomSequenceCSSStyleValueNullableElement', nullable.ctype)
        self.assertFalse(generator.complex_used[plain.ctype].subtypes[0].nullable)
        self.assertTrue(generator.complex_used[nullable.ctype].subtypes[0].nullable)

    def test_configured_non_node_callwith_uses_an_explicit_checked_document(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface StylePropertyMapReadOnly {
    [CallWith=CurrentScriptExecutionContext] boolean has(USVString property);
    readonly attribute unsigned long size;
};
partial interface Node { [CallWith=CurrentDocument] boolean hasInDocument(USVString property); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['StylePropertyMapReadOnly']
        unconfigured = domgen.Generator(domgen.World(self.source, config))
        unconfigured.lock = {}
        unconfigured.lock_structs = {}
        unconfigured.run()
        self.assertFalse(any(item.name == 'style_property_map_read_only_has' for item in unconfigured.functions))
        config['objectContexts'] = {'StylePropertyMapReadOnly': 'Document'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        function = next(item for item in generator.functions if item.name == 'style_property_map_read_only_has')
        self.assertEqual([('RvStylePropertyMapReadOnly*', 'target'), ('RvNode*', 'context')], function.params[:2])
        body = '\n'.join(function.body)
        self.assertTrue('!context' in body)
        self.assertTrue('dynamicDowncast<Document>(*nodeOf(context))' in body)
        self.assertTrue('return RV_ERR_WRONG_INTERFACE;' in body)
        self.assertTrue('Ref document = contextDocument.releaseNonNull();' in body)
        self.assertTrue('impl->has(document.get(),' in body)
        model = json.loads(generator.api_model())
        operation = next(item for item in model['functions'] if item['function'] == 'rv_dom_style_property_map_read_only_has')
        self.assertEqual('Document', operation['contextReceiver'])
        size = next(item for item in generator.functions if item.name == 'style_property_map_read_only_get_size')
        self.assertFalse(any(name == 'context' for _, name in size.params))
        node = next(item for item in generator.functions if item.name == 'node_has_in_document')
        self.assertFalse(any(name == 'context' for _, name in node.params))
        self.assertTrue('Ref document = impl->document();' in '\n'.join(node.body))
        config['objectContexts'] = {'StylePropertyMapReadOnly': 'Element'}
        invalid = domgen.Generator(domgen.World(self.source, config))
        invalid.lock = {}
        invalid.lock_structs = {}
        with self.assertRaisesRegex(SystemExit, 'object context must be a scoped Document'):
            invalid.run()

    def test_undefined_result_union_preserves_a_tagged_monostate_without_a_handle(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
partial interface Node { (undefined or CSSStyleValue) maybeValue(); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        header = generator.header()
        interfaces = generator.interfaces()
        result = next(item.returns for item in generator.functions if item.name == 'node_maybe_value')
        self.assertEqual('Variant<std::monostate, Ref<CSSStyleValue>>', generator.transport_cpp(result))
        self.assertIn('int32_t arm0;', header)
        self.assertIn('result->arm0 = 0;', glue)
        self.assertIn('UndefinedOrCSSStyleValue.Undefined ()', interfaces)
        self.assertNotIn('isUndefined arm', interfaces)
        self.assertIn('$0 === undefined', interfaces)
        self.assertTrue("globalThis.CSSStyleValue.prototype.toString.call(v)" in interfaces)

    def test_selected_reference_segment_overload_rejects_null_and_checks_the_engine_brand(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef (USVString or CSSOMVariableReferenceValue) CSSUnparsedSegment;
interface CSSStyleValue {};
[InterfaceName=CSSVariableReferenceValue] interface CSSOMVariableReferenceValue { attribute USVString variable; };
interface CSSUnparsedValue : CSSStyleValue { setter undefined (unsigned long index, CSSUnparsedSegment reference); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMVariableReferenceValue', 'CSSUnparsedValue']
        config['complexStringSpans'] = ['USVStringOrCSSOMVariableReferenceValue']
        config['contract'] = {'aliases': {'CSSOMVariableReferenceValue': 'CSSVariableReferenceValue'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        interfaces = generator.interfaces()
        self.assertTrue('if isNull (box reference) then\n                nullArg "reference"' in interfaces)
        self.assertTrue('if not (isCSSOMVariableReferenceValue (box reference)) then' in interfaces)
        self.assertTrue("getOwnPropertyDescriptor(globalThis.CSSVariableReferenceValue.prototype,'variable').get.call(v)" in interfaces)
        self.assertTrue('box (normalizeUSVString reference)' in interfaces)
        self.assertTrue("if(i===4294967295)throw new RangeError('Index out of range.');v[i]=s;" in interfaces)

    def test_selected_unit_value_rejects_nonfinite_double_inputs_but_keeps_unrestricted_inputs(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
interface CSSUnitValue : CSSNumericValue {
    constructor(double value, USVString unit);
    attribute double value;
    attribute unrestricted double unrestricted;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSUnitValue']
        config['finiteNumberInputs'] = ['CSSUnitValue']
        config['constructors'] = {'CSSUnitValue': {
            'receiver': 'Document', 'factory': 'CSSUnitValue::create', 'passReceiver': False,
            'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        for name in ['css_unit_value_create', 'css_unit_value_set_value']:
            function = next(item for item in generator.functions if item.name == name)
            self.assertTrue('!std::isfinite(value)' in '\n'.join(function.body))
            self.assertTrue('ExceptionCode::TypeError' in '\n'.join(function.body))
        unrestricted = next(item for item in generator.functions if item.name == 'css_unit_value_set_unrestricted')
        self.assertNotIn('isfinite', '\n'.join(unrestricted.body))
        self.assertTrue('#include <cmath>' in generator.glue())

    def test_selected_usv_property_setter_normalizes_once_in_the_browser(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue { attribute USVString value; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMKeywordValue']
        config['interfaceStringInputs'] = {'CSSOMKeywordValue': 'utf8-lengths'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        self.assertTrue("$0.value{{=((v)=>String(v==null?'null':v).toWellFormed())($1)}}" in generator.interfaces())

    def test_selected_usv_segment_setter_normalizes_its_string_overload(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef (USVString or CSSOMVariableReferenceValue) CSSUnparsedSegment;
interface CSSStyleValue {};
interface CSSOMVariableReferenceValue { readonly attribute USVString variable; };
interface CSSUnparsedValue : CSSStyleValue { setter undefined (unsigned long index, CSSUnparsedSegment value); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMVariableReferenceValue', 'CSSUnparsedValue']
        config['complexStringSpans'] = ['USVStringOrCSSOMVariableReferenceValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        interfaces = generator.interfaces()
        self.assertTrue('box (normalizeUSVString value)' in interfaces)
        self.assertTrue('let private normalizeUSVString' in interfaces)

    def test_aliased_segment_interfaces_keep_the_browser_tag_and_typed_union_arm(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef (USVString or CSSOMVariableReferenceValue) CSSUnparsedSegment;
interface CSSStyleValue {};
[InterfaceName=CSSVariableReferenceValue] interface CSSOMVariableReferenceValue { readonly attribute USVString variable; };
interface CSSUnparsedValue : CSSStyleValue { getter CSSUnparsedSegment? (unsigned long index); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMVariableReferenceValue', 'CSSUnparsedValue']
        config['contract'] = {'aliases': {'CSSOMVariableReferenceValue': 'CSSVariableReferenceValue'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        interfaces = generator.interfaces()
        self.assertTrue('CSSOMVariableReferenceValue of CSSVariableReferenceValue' in interfaces)
        self.assertTrue('[object CSSVariableReferenceValue]' in interfaces)
        self.assertTrue('let private isCSSOMVariableReferenceValue' in interfaces)

    def test_selected_value_setters_use_string_spans_while_old_setters_keep_their_signatures(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue { attribute USVString value; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMKeywordValue']
        config['interfaceStringInputs'] = {'CSSOMKeywordValue': 'utf8-lengths'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        setter = functions['rv_dom_cssom_keyword_value_set_value']
        self.assertEqual(setter['parameters'][1:], [
            {'ctype': 'const uint8_t*', 'name': 'value'},
            {'ctype': 'int32_t', 'name': 'value_length'},
        ])
        self.assertEqual(setter['stringInputs'], 'utf8-lengths')
        self.assertEqual(functions['rv_dom_element_set_id']['parameters'][1], {'ctype': 'const char*', 'name': 'value'})

    def test_selected_unparsed_segment_transport_preserves_string_lengths_without_changing_old_unions(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef (USVString or CSSOMVariableReferenceValue) CSSUnparsedSegment;
interface CSSStyleValue {};
interface CSSOMVariableReferenceValue { readonly attribute USVString variable; };
interface CSSUnparsedValue : CSSStyleValue {
    constructor(sequence<CSSUnparsedSegment> members);
    readonly attribute unsigned long length;
    getter CSSUnparsedSegment? (unsigned long index);
    setter undefined (unsigned long index, CSSUnparsedSegment val);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMVariableReferenceValue', 'CSSUnparsedValue']
        config['complexStringSpans'] = ['USVStringOrCSSOMVariableReferenceValue']
        config['constructors'] = {'CSSUnparsedValue': {
            'receiver': 'Document', 'factory': 'CSSUnparsedValue::create', 'passReceiver': False,
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        header = generator.header()
        self.assertTrue('RvDomUtf8StringSpan arm0;' in header)
        self.assertTrue('const char* arm1;' in header)
        model = json.loads(generator.api_model())
        functions = {item['function']: item for item in model['functions']}
        item = functions['rv_dom_css_unparsed_value_item']
        self.assertTrue(item['returns']['nullable'])
        self.assertEqual(item['returns']['subtypes'][0]['stringTransport'], 'utf8-lengths')
        old = functions['rv_dom_node_get_state']['returns']['subtypes'][1]
        self.assertNotIn('stringTransport', old)
        glue = generator.glue()
        self.assertTrue('source->arm0.length < 0' in glue)
        self.assertTrue('source->arm0.length > 0 && !source->arm0.data' in glue)
        self.assertTrue('source->present != 0 && source->present != 1' in glue)
        self.assertTrue('result->arm0 = copyOwnedDomStringSpan' in glue)
        self.assertTrue('std::free(const_cast<uint8_t*>(value->arm0.data))' in glue)
        self.assertTrue('impl->setItem(' in glue)
        self.assertTrue('type RvDomUtf8StringSpan =' in generator.fsharp())

    def test_value_factory_constructor_can_validate_document_without_passing_it_to_cpp(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue { constructor(USVString value); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMKeywordValue']
        config['constructors'] = {'CSSOMKeywordValue': {
            'receiver': 'Document', 'factory': 'CSSOMKeywordValue::create',
            'passReceiver': False, 'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        constructor = functions['rv_dom_cssom_keyword_value_create']
        self.assertEqual(constructor['parameters'][:3], [
            {'ctype': 'RvNode*', 'name': 'target'},
            {'ctype': 'const uint8_t*', 'name': 'value'},
            {'ctype': 'int32_t', 'name': 'value_length'},
        ])
        self.assertEqual(constructor['stringInputs'], 'utf8-lengths')
        self.assertEqual(constructor['receiver'], 'Document')
        glue = generator.glue()
        self.assertTrue('CSSOMKeywordValue::create(a0.string())' in glue)
        self.assertTrue('dynamicDowncast<Document>(*nodeOf(target))' in glue)

    def test_configured_bare_stringifier_exports_engine_serialization_only_for_selected_types(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue { stringifier; };
interface OtherValue { stringifier; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'OtherValue']
        config['stringifiers'] = ['CSSStyleValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertIn('rv_dom_css_style_value_to_string', functions.keys())
        self.assertNotIn('rv_dom_other_value_to_string', functions.keys())
        self.assertTrue('impl->toString()' in generator.glue())
        self.assertTrue('abstract member toString: unit -> string' in generator.interfaces())

    def test_configured_static_value_parsers_use_document_and_length_delimited_inputs(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {
    [Exposed=Window, CallWith=CurrentDocument] static CSSStyleValue parse([AtomString] USVString property, USVString cssText);
    [Exposed=Window, CallWith=CurrentDocument] static sequence<CSSStyleValue> parseAll([AtomString] USVString property, USVString cssText);
    static boolean unrelated();
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue']
        config['staticBindings'] = {'CSSStyleValue': {
            'receiver': 'Document', 'members': ['parse', 'parseAll'],
            'feature': 'dom-css-style-values', 'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertIn('rv_dom_css_style_value_parse', functions.keys())
        self.assertIn('rv_dom_css_style_value_parse_all', functions.keys())
        self.assertNotIn('rv_dom_css_style_value_unrelated', functions)
        single = functions['rv_dom_css_style_value_parse']
        self.assertEqual(single['kind'], 'static_operation')
        self.assertEqual(single['receiver'], 'Document')
        self.assertEqual(single['binding'], 'facade')
        self.assertEqual(single['feature'], 'dom-css-style-values')
        self.assertEqual(single['parameters'][:5], [
            {'ctype': 'RvNode*', 'name': 'target'},
            {'ctype': 'const uint8_t*', 'name': 'property'},
            {'ctype': 'int32_t', 'name': 'property_length'},
            {'ctype': 'const uint8_t*', 'name': 'css_text'},
            {'ctype': 'int32_t', 'name': 'css_text_length'},
        ])
        self.assertEqual(single['returns']['interface'], 'CSSStyleValue')
        self.assertEqual(functions['rv_dom_css_style_value_parse_all']['returns']['kind'], 'sequence')
        glue = generator.glue()
        self.assertTrue('CSSStyleValue::parse(document.get(), a0.atom(), a1.string())' in glue)
        self.assertTrue('CSSStyleValue::parseAll(document.get(), a0.atom(), a1.string())' in glue)
        self.assertIn('dynamicDowncast<Document>(*nodeOf(target))', glue)
        self.assertIn('property_length >= 0', glue)

    def test_registration_dictionary_has_lossless_spans_and_independent_capability(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
dictionary DOMCSSCustomPropertyDescriptor {
    required [AtomString] DOMString name;
    DOMString syntax = "*";
    required boolean inherits;
    DOMString initialValue;
};
[InterfaceName=CSS] namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(DOMString condition);
};
[ImplementedBy=DOMCSSRegisterCustomProperty, Conditional=REGISTRATION]
partial namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] undefined registerProperty(DOMCSSCustomPropertyDescriptor descriptor);
};
interface CSSRule {};
interface CSSPropertyRule : CSSRule {
    readonly attribute DOMString name;
    readonly attribute DOMString syntax;
    readonly attribute boolean inherits;
    readonly attribute DOMString? initialValue;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSRule', 'CSSPropertyRule']
        config['dictionaryStringInputs'] = {'DOMCSSCustomPropertyDescriptor': 'utf8-lengths-presence'}
        config['namespaceBindings'] = {'DOMCSSNamespace': {
            'receiver': 'Document', 'members': ['supports', 'registerProperty'],
            'feature': 'dom-css-supports', 'memberFeatures': {'registerProperty': 'dom-css-register-property'},
            'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        functions = {item['function']: item for item in model['functions']}
        self.assertEqual(functions['rv_dom_css_register_property']['feature'], 'dom-css-register-property')
        self.assertEqual(functions['rv_dom_css_supports']['feature'], 'dom-css-supports')
        self.assertTrue(functions['rv_dom_css_property_rule_get_initial_value']['returns']['nullable'])
        fields = model['dictionaries']['DOMCSSCustomPropertyDescriptor']
        self.assertEqual([field['ctype'] for field in fields],
                         ['RvDomUtf8StringInput', 'RvDomUtf8StringInput', 'int32_t', 'RvDomUtf8StringInput'])
        header = generator.header()
        self.assertIn('int32_t present;', header)
        self.assertIn('const uint8_t* data;', header)
        self.assertIn('int32_t length;', header)
        self.assertIn('const char* label;', header)
        glue = generator.glue()
        self.assertIn('DOMCSSRegisterCustomProperty::registerProperty(document.get(), std::move(a0))', glue)
        self.assertIn('descriptor->name.present != 1', glue)
        self.assertIn('descriptor->initial_value.length < 0', glue)
        self.assertIn('descriptor->initial_value.length > 0 && !descriptor->initial_value.data', glue)
        self.assertIn('assignString(a0.initialValue, descriptor->initial_value.data, descriptor->initial_value.length)', glue)
        self.assertIn('length ? String::fromUTF8(std::span<const uint8_t>', glue)
        self.assertIn('val mutable initial_value: RvDomUtf8StringInput', generator.fsharp())
        features = dict(generator.namespace_features)
        self.assertEqual(features['dom-css-supports'], [])
        self.assertEqual(features['dom-css-register-property'], ['ENABLE(REGISTRATION)'])

    def test_fragment_rectangle_lists_select_real_element_and_range_geometry(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface DOMRectReadOnly { readonly attribute unrestricted double x; };
interface DOMRect : DOMRectReadOnly {};
interface DOMRectList {
    readonly attribute unsigned long length;
    getter DOMRect? item(unsigned long index);
};
partial interface Element { DOMRectList getClientRects(); };
interface Range { DOMRectList getClientRects(); };
''')
        configured = json.loads((ROOT / 'gen/dom.json').read_text())['interfaces']
        self.assertIn('DOMRectList', configured)
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'Range', 'DOMRectReadOnly', 'DOMRect', 'DOMRectList']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {f['function']: f for f in json.loads(generator.api_model())['functions']}
        for name in ['rv_dom_element_get_client_rects', 'rv_dom_range_get_client_rects',
                     'rv_dom_dom_rect_list_get_length', 'rv_dom_dom_rect_list_item']:
            self.assertIn(name, functions)
        item = functions['rv_dom_dom_rect_list_item']
        self.assertTrue(item['returns']['nullable'])
        self.assertEqual(item['returns']['interface'], 'DOMRect')
        self.assertEqual(functions['rv_dom_element_get_client_rects']['returns']['interface'], 'DOMRectList')
        self.assertIn('abstract member getClientRects:', generator.interfaces())

    def test_required_dom_strings_normalize_null_engine_values_but_nullable_strings_preserve_null(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
partial interface Element {
    DOMString requiredText();
    DOMString? nullableText();
};
''')
        generator = domgen.Generator(domgen.World(self.source, self.world.config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        required = next(f for f in generator.functions if f.name == 'element_required_text')
        nullable = next(f for f in generator.functions if f.name == 'element_nullable_text')
        self.assertTrue('copyRequiredString(asString(value), buffer, capacity, length)' in '\n'.join(required.body))
        self.assertTrue('copyString(asString(value), buffer, capacity, length)' in '\n'.join(nullable.body))
        self.assertTrue('value.isNull() ? emptyString() : value' in generator.glue())

    def test_window_computed_style_context_binding_uses_real_window_and_nullable_spans(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef USVString CSSOMString;
interface CSSStyleDeclaration { DOMString getPropertyValue(DOMString property); };
[InterfaceName=Window, Exposed=Window, Conditional=OUTER] interface DOMWindow : EventTarget {};
[Conditional=LEFT|RIGHT] partial interface DOMWindow {
    [NewObject, Conditional=MEMBER|OTHER] CSSStyleDeclaration getComputedStyle(Element element, optional CSSOMString? pseudoElement = null);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleDeclaration']
        config['windowBindings'] = {'DOMWindow': {
            'receiver': 'Document', 'members': ['getComputedStyle'],
            'feature': 'dom-computed-style', 'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertIn('rv_dom_window_get_computed_style', functions)
        operation = functions['rv_dom_window_get_computed_style']
        self.assertEqual(operation['kind'], 'context_operation')
        self.assertEqual(operation['receiver'], 'Document')
        self.assertEqual(operation['contractOwner'], 'Window')
        self.assertEqual(operation['feature'], 'dom-computed-style')
        import itertools
        for values in itertools.product([False, True], repeat=5):
            flags = dict(zip(['OUTER', 'LEFT', 'RIGHT', 'MEMBER', 'OTHER'], values))
            expression = operation['conditional'].replace('&&', ' and ').replace('||', ' or ')
            for name, value in flags.items():
                expression = expression.replace(f'ENABLE({name})', str(value))
            expected = flags['OUTER'] and (flags['LEFT'] or flags['RIGHT']) and (flags['MEMBER'] or flags['OTHER'])
            self.assertEqual(eval(expression, {'__builtins__': {}}), expected, flags)
        self.assertIn({'ctype': 'const uint8_t*', 'name': 'pseudo_element'}, operation['parameters'])
        self.assertIn({'ctype': 'int32_t', 'name': 'pseudo_element_length'}, operation['parameters'])
        self.assertEqual(operation['parameters'][-1], {'ctype': 'RvCSSStyleDeclaration**', 'name': 'result'})
        glue = generator.glue()
        self.assertTrue('impl->window()->getComputedStyle(HandleArg<Element> { a0.get() }, a1.string())' in glue)
        self.assertIn('if (!impl->window())', glue)
        self.assertIn('pseudo_element_length >= -1', glue)
        self.assertIn('pseudo_element_length >= 0 && a1.string().isNull()', glue)
        self.assertNotIn('type Window =', generator.interfaces())

    def test_namespace_support_queries_use_checked_document_and_complete_input_spans(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=CSS, Exposed=Window, Conditional=NAMESPACE]
namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(DOMString property, DOMString value);
    DOMString escape(DOMString ident);
};
[Conditional=PARTIAL, ImplementedBy=ProbeSupport] partial namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(DOMString conditionText);
    boolean unused();
};
''')
        config = dict(self.world.config)
        config['namespaceBindings'] = {'DOMCSSNamespace': {
            'receiver': 'Document', 'members': ['supports'], 'feature': 'dom-css-supports',
            'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        functions = {item['function']: item for item in model['functions']}
        self.assertIn('rv_dom_css_supports_2', functions)
        self.assertIn('rv_dom_css_supports_1', functions)
        self.assertNotIn('rv_dom_css_escape', functions)
        for name in ['rv_dom_css_supports_2', 'rv_dom_css_supports_1']:
            item = functions[name]
            self.assertEqual(item['parameters'][0], {'ctype': 'RvNode*', 'name': 'target'})
            self.assertEqual(item['parameters'][1]['ctype'], 'const uint8_t*')
            self.assertEqual(item['parameters'][2]['ctype'], 'int32_t')
            self.assertEqual(item['receiver'], 'Document')
            self.assertEqual(item['namespace'], 'CSS')
            self.assertEqual(item['stringInputs'], 'utf8-lengths')
            self.assertEqual(item['kind'], 'namespace_operation')
            self.assertIn('ENABLE(NAMESPACE)', item['conditional'])
        self.assertIn('ENABLE(PARTIAL)', functions['rv_dom_css_supports_1']['conditional'])
        self.assertNotIn('ENABLE(PARTIAL)', functions['rv_dom_css_supports_2']['conditional'])
        glue = generator.glue()
        self.assertIn('dynamicDowncast<Document>(*nodeOf(target))', glue)
        self.assertIn('DOMCSSNamespace::supports(document.get(), a0.string(), a1.string())', glue)
        self.assertIn('ProbeSupport::supports(document.get(), a0.string())', glue)
        self.assertIn('StringArg a0 { property, property_length }', glue)
        self.assertIn('property_length >= 0', glue)
        self.assertIn('std::span<const uint8_t>', glue)
        self.assertIn('"dom-css-supports"', glue)
        feature_guard = glue[:glue.index('    if (!std::strcmp(feature, "dom-css-supports"))')].rsplit('#if ', 1)[1]
        self.assertIn('ENABLE(NAMESPACE)', feature_guard)
        self.assertIn('ENABLE(PARTIAL)', feature_guard)
        self.assertNotIn('interface DOMCSSNamespace', generator.interfaces())

    def test_namespace_configuration_fails_closed_for_missing_or_unsupported_operations(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=CSS] namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(optional DOMString conditionText);
};
''')
        binding = {'receiver': 'Document', 'members': ['supports'],
                   'feature': 'dom-css-supports', 'stringInputs': 'utf8-lengths'}
        cases = [
            ('AbsentNamespace', binding, 'configured IDL namespace was not found'),
            ('DOMCSSNamespace', dict(binding, receiver='Event'), 'receiver must be a scoped node'),
            ('DOMCSSNamespace', dict(binding, stringInputs='cstring'), 'require explicit UTF-8 lengths'),
            ('DOMCSSNamespace', dict(binding, members=['missing']), 'missing configured namespace operations'),
            ('DOMCSSNamespace', binding, 'optional or nullable namespace strings need an explicit presence'),
        ]
        for name, configured, reason in cases:
            with self.subTest(reason=reason):
                config = dict(self.world.config)
                config['namespaceBindings'] = {name: configured}
                generator = domgen.Generator(domgen.World(self.source, config))
                generator.lock = {}
                generator.lock_structs = {}
                with self.assertRaisesRegex(SystemExit, reason):
                    generator.run()

    def test_namespace_compound_gates_preserve_all_enclosing_conditions(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=CSS, Conditional=OUTER] namespace DOMCSSNamespace {};
[Conditional=LEFT|RIGHT] partial namespace DOMCSSNamespace {
    [Conditional=MEMBER|OTHER, CallWith=CurrentDocument] boolean supports(DOMString conditionText);
};
''')
        config = dict(self.world.config)
        config['namespaceBindings'] = {'DOMCSSNamespace': {
            'receiver': 'Document', 'members': ['supports'], 'feature': 'dom-css-supports',
            'stringInputs': 'utf8-lengths',
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        operation = next(f for f in generator.functions if f.kind == 'namespace_operation')
        self.assertIn(f'#if ({operation.conditional})\n    if (!std::strcmp(feature, "dom-css-supports"))', generator.glue())
        import itertools
        for values in itertools.product([False, True], repeat=5):
            flags = dict(zip(['OUTER', 'LEFT', 'RIGHT', 'MEMBER', 'OTHER'], values))
            expression = operation.conditional.replace('&&', ' and ').replace('||', ' or ')
            for name, value in flags.items():
                expression = expression.replace(f'ENABLE({name})', str(value))
            expected = flags['OUTER'] and (flags['LEFT'] or flags['RIGHT']) and (flags['MEMBER'] or flags['OTHER'])
            self.assertEqual(eval(expression, {'__builtins__': {}}), expected, flags)

    def test_adopted_stylesheet_native_bridges_preserve_js_wrapper_contract(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface StyleSheet {};
interface CSSStyleSheet : StyleSheet {};
interface ShadowRoot : Node {};
interface mixin DocumentOrShadowRoot {
    [CallWith=CurrentGlobalObject, ImplementedAs=adoptedStyleSheetWrapper, CachedAttribute, CustomSetter]
    attribute any adoptedStyleSheets;
};
Document includes DocumentOrShadowRoot;
ShadowRoot includes DocumentOrShadowRoot;
''')
        config = dict(self.world.config)
        selected = json.loads((ROOT / 'gen/dom.json').read_text())
        config['interfaces'] = ['Node', 'Document', 'ShadowRoot', 'StyleSheet', 'CSSStyleSheet']
        config['attributeBridges'] = selected.get('attributeBridges', {})
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {function['function']: function for function in json.loads(generator.api_model())['functions']}
        for scope in ['document', 'shadow_root']:
            get = functions[f'rv_dom_{scope}_get_adopted_style_sheets']
            put = functions[f'rv_dom_{scope}_set_adopted_style_sheets']
            self.assertEqual(get['returns']['kind'], 'sequence')
            self.assertEqual(get['returns']['subtypes'][0]['interface'], 'CSSStyleSheet')
            self.assertEqual(put['arguments'][0]['mapping']['kind'], 'sequence')
            self.assertEqual(get['binding'], 'facade')
            self.assertEqual(get['feature'], 'dom-adopted-style-sheets')
        glue = generator.glue()
        self.assertIn('impl->adoptedStyleSheets()', glue)
        self.assertIn('impl->setAdoptedStyleSheets(', glue)
        self.assertIn('"dom-adopted-style-sheets"', glue)
        self.assertNotIn('adoptedStyleSheetWrapper(', glue)
        self.assertNotIn('abstract member adoptedStyleSheets:', generator.interfaces())

    def test_configured_stylesheet_constructor_uses_document_receiver_and_cpp_init(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface StyleSheet {};
interface CSSStyleSheet : StyleSheet {
    [CallWith=CurrentDocument] constructor(optional CSSStyleSheetInit options = {});
};
dictionary CSSStyleSheetInit { DOMString baseURL = null; boolean disabled = false; };
''')
        config = dict(self.world.config)
        selected = json.loads((ROOT / 'gen/dom.json').read_text())
        config['interfaces'] = ['Node', 'Document', 'StyleSheet', 'CSSStyleSheet']
        config['constructors'] = selected.get('constructors', {})
        config['dictionaryCppTypes'] = selected.get('dictionaryCppTypes', {})
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {function['function']: function for function in json.loads(generator.api_model())['functions']}
        factory = functions['rv_dom_css_style_sheet_create']
        self.assertEqual(factory['parameters'][0], {'ctype': 'RvNode*', 'name': 'target'})
        self.assertEqual(factory['returns']['interface'], 'CSSStyleSheet')
        self.assertEqual(factory['kind'], 'constructor')
        self.assertEqual(factory['feature'], 'dom-constructor:CSSStyleSheet')
        glue = generator.glue()
        self.assertIn('dynamicDowncast<Document>(*nodeOf(target))', glue)
        self.assertIn('CSSStyleSheet::Init a0', glue)
        self.assertIn('CSSStyleSheet::create(*impl, std::move(a0))', glue)
        self.assertIn('"dom-constructor:CSSStyleSheet"', glue)

    def test_runtime_type_queries_classify_derived_interfaces_without_changing_dom_members(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSRule {};
interface CSSGroupingRule : CSSRule {};
[Conditional=PROBE] interface CSSStartingStyleRule : CSSGroupingRule {};
''')
        config = dict(self.world.config)
        config['interfaces'] = ['CSSRule', 'CSSGroupingRule', 'CSSStartingStyleRule']
        config['runtimeTypeRoots'] = ['CSSRule']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        query = model['runtimeTypeQueries'][0]
        self.assertEqual(query['root'], 'CSSRule')
        self.assertEqual(query['function'], 'rv_dom_css_rule_get_interface_name')
        self.assertEqual(query['feature'], 'dom-type-query:CSSRule')
        self.assertEqual(model['functions'], [])
        self.assertNotIn('get_interface_name', generator.interfaces())
        for output in [generator.header(), generator.host(), generator.fsharp()]:
            self.assertIn('rv_dom_css_rule_get_interface_name', output)
        glue = generator.glue()
        self.assertIn('#if ENABLE(PROBE)', glue)
        self.assertIn('"dom-type-query:CSSRule"', glue)
        self.assertLess(glue.index('dynamicDowncast<CSSStartingStyleRule>'), glue.index('dynamicDowncast<CSSGroupingRule>'))
        self.assertIn('return copyString("CSSRule"_s, buffer, capacity, length)', glue)

    def test_css_rule_and_descriptor_settings_use_retained_binding_document(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSRule {};
[EnabledBySetting=CSSAnchorPositioningEnabled] interface CSSPositionTryRule : CSSRule {
    readonly attribute DOMString name;
};
interface CSSStyleDeclaration {};
interface CSSFontFaceDescriptors : CSSStyleDeclaration {
    [EnabledBySetting=CSSFontFaceMetricOverrideDescriptorsEnabled] attribute DOMString ascentOverride;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = ['CSSRule', 'CSSPositionTryRule', 'CSSStyleDeclaration', 'CSSFontFaceDescriptors']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        self.assertEqual(len(generator.functions), 3)
        glue = generator.glue()
        self.assertEqual(glue.count('RefPtr<Document> settingsDocument = impl->documentForBindings();'), 3)
        self.assertNotIn('settingsSheet->ownerDocument()', glue)
        self.assertIn('if (!settingsDocument)\n        return RV_ERR_UNSUPPORTED;', glue)
        self.assertIn('settings.cssAnchorPositioningEnabled', glue)
        self.assertIn('settings.cssFontFaceMetricOverrideDescriptorsEnabled', glue)

    def test_css_descriptor_aliases_have_distinct_exports_and_valid_fsharp_names(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleDeclaration {};
interface CSSFontFaceDescriptors : CSSStyleDeclaration {
    attribute DOMString fontFamily;
    attribute DOMString font-family;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = ['CSSStyleDeclaration', 'CSSFontFaceDescriptors']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        self.assertEqual(len(generator.functions), 4)
        self.assertEqual(len({function.name for function in generator.functions}), 4)
        self.assertIn('abstract member ``font-family``:', generator.interfaces())
        glue = generator.glue()
        self.assertIn('impl->fontFamily()', glue)
        self.assertNotIn('impl->font-family(', glue)

    def test_css_generator_test_partials_are_not_exposed_as_runtime_properties(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '\ninterface CSSStyleProperties : HTMLElement {};')
        partial = self.source / 'Source/WebCore/css/scripts/test/Results/Probe.idl'
        partial.parent.mkdir(parents=True)
        partial.write_text('partial interface CSSStyleProperties { attribute DOMString fakeTestProperty; };')
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'HTMLElement', 'CSSStyleProperties']
        config['skipDirectories'] = json.loads((ROOT / 'gen/dom.json').read_text())['skipDirectories']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        self.assertNotIn('fake_test_property', generator.header())
        self.assertNotIn('fakeTestProperty', generator.interfaces())

    def test_area_reflection_and_url_components_are_in_native_scope(self):
        config = json.loads((ROOT / 'gen/dom.json').read_text())
        self.assertIn('HTMLAreaElement', config['interfaces'])
        self.assertIn('HTMLAreaElement.ping', config['exclude'])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = pathlib.Path(self.temp.name)
        directory = self.source / 'Source/WebCore/dom'
        directory.mkdir(parents=True)
        (directory / 'Fixture.idl').write_text(IDL)
        tags = self.source / 'Source/WebCore/html/HTMLTagNames.in'
        tags.parent.mkdir()
        tags.write_text('audio\nh1 interfaceName=HTMLHeadingElement\narticle interfaceName=HTMLArticleElement, JSInterfaceName=HTMLElement\n')
        config = dict(interfaces=['Node', 'Element', 'Document', 'HTMLDocument', 'DOMImplementation', 'Event', 'DOMStringMap'],
                      skipDirectories=[], exclude=['ImportNodeOptions.customElementRegistry', 'AddEventListenerOptions.signal', 'AddEventListenerOptions.webkitTrustedOnly'], atomArguments=[], customGetters=['Node.nodeType'],
                      contract=dict(htmlTags='html/HTMLTagNames.in', interfaces=['SVGElement', 'SVGSVGElement'],
                                    dictionaries=['EventListenerOptions', 'AddEventListenerOptions'],
                                    mixins={'AriaAttributes': 'ARIAMixin', 'ParentNode': 'ParentNode'}))
        self.world = domgen.World(self.source, config)
        self.generator = domgen.Generator(self.world)
        self.generator.lock = {}
        self.generator.lock_structs = {}
        self.generator.run()

    def test_union_attributes_and_variadic_mixed_nodes_are_exported(self):
        functions = {function.name for function in self.generator.functions}
        self.assertIn('node_get_state', functions)
        self.assertIn('node_set_state', functions)
        self.assertIn('node_append', functions)
        self.assertNotIn(('Node.append', 'variadic arguments'), self.generator.excluded)

    def test_sequence_inputs_and_owned_outputs_are_exported(self):
        functions = {function.name for function in self.generator.functions}
        self.assertIn('node_labels', functions)
        self.assertIn('node_descendants', functions)
        self.assertIn('node_take', functions)
        header = self.generator.header()
        self.assertIn('int32_t count', header)
        self.assertIn('_release(', header)

    def test_namespace_creation_and_second_document_are_exported(self):
        functions = {function.name for function in self.generator.functions}
        self.assertIn('document_create_element_ns', functions)
        self.assertIn('document_get_implementation', functions)
        self.assertIn('dom_implementation_create_html_document', functions)

    def test_public_interfaces_use_fsharp_unions_and_browser_member_names(self):
        source = self.generator.interfaces()
        self.assertIn('namespace Ranvier.Dom', source)
        self.assertIn('EventTarget =', source)
        self.assertIn('EventListener', source)
        self.assertIn('abstract member createElementNS', source)
        self.assertIn('ParamArray', source)
        self.assertIn('NodeOrDOMString', source)
        self.assertNotIn('U2<', source)

    def test_out_of_scope_union_arm_remains_reported(self):
        mapped = domgen.idl.Type('union', subtypes=[domgen.idl.Type('Node'), domgen.idl.Type('Outside')])
        with self.assertRaises(domgen.Unsupported):
            self.world.map(mapped)

    def test_named_property_accessors_are_present_on_browser_interfaces(self):
        source = self.generator.interfaces()
        self.assertIn('abstract member namedItem:', source)
        self.assertIn('$0[$1]', source)

    def test_dataset_named_lookup_uses_own_keys_and_missing_string(self):
        source = self.generator.interfaces()
        start = source.index('and [<AllowNullLiteral>] DOMStringMap =')
        section = source[start:].split('\n/// <summary>', 1)[0]
        self.assertIn('Object.prototype.hasOwnProperty.call', section)
        self.assertIn("?$0[$1]:''", section)

    def test_stylesheet_named_lookup_uses_document_id_semantics(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface StyleSheet {};
interface CSSStyleSheet : StyleSheet {};
interface StyleSheetList {
    readonly attribute unsigned long length;
    getter CSSStyleSheet? item(unsigned long index);
    getter CSSStyleSheet? (DOMString name);
};
partial interface Document { readonly attribute StyleSheetList styleSheets; };
''')
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Document', 'DOMImplementation', 'StyleSheet', 'CSSStyleSheet', 'StyleSheetList']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        source = generator.interfaces()
        start = source.index('and [<AllowNullLiteral>] StyleSheetList =')
        section = source[start:]
        section = section.split('\n/// <summary>', 1)[0]
        self.assertIn('getElementById', section)
        self.assertIn('styleSheets', section)
        self.assertNotIn('Emit("$0[$1]")', section)
        self.assertIn('new WeakMap()', source)
        self.assertIn('new WeakRef(r)', source)
        self.assertIn('Reflect.defineProperty(s,k,{value:v})', source)

    def test_explicit_custom_getter_override_maps_node_type_only(self):
        self.assertIn('node_get_node_type', {function.name for function in self.generator.functions})

    def test_interface_accessors_match_the_native_accessor_subset(self):
        self.assertIn('abstract member writeOnly: string with set', self.generator.interfaces())

    def test_event_listener_option_contracts_preserve_defaults_and_omit_signal(self):
        source = self.generator.interfaces()
        self.assertIn('listener: EventListener * options: AddEventListenerOptions -> unit', source)
        self.assertIn('listener: EventListenerObject * options: AddEventListenerOptions -> unit', source)
        self.assertIn('listener: EventListener * options: EventListenerOptions -> unit', source)
        self.assertIn('listener: EventListenerObject * ?capture: bool -> unit', source)
        self.assertIn('inherit EventListenerOptions()', source)
        self.assertIn('member val passive: (bool) option = None', source)
        self.assertIn('member val once: bool = false', source)
        self.assertNotIn('member val signal:', source)
        self.assertNotIn('member val webkitTrustedOnly:', source)
        self.assertIn('AddEventListenerOptions.signal', self.generator.report())
        self.assertIn('AddEventListenerOptions', json.loads(self.generator.api_model())['contractDictionaries'])

    def test_transport_model_describes_variadic_union_and_dictionary_fields(self):
        model = json.loads(self.generator.api_model())
        append = next(function for function in model['functions'] if function['function'] == 'rv_dom_node_append')
        argument = append['arguments'][0]
        self.assertTrue(argument['variadic'])
        self.assertEqual(argument['mapping']['kind'], 'sequence')
        self.assertEqual(argument['mapping']['subtypes'][0]['kind'], 'union')
        self.assertEqual([arm['kind'] for arm in argument['mapping']['subtypes'][0]['subtypes']], ['node', 'string'])
        self.assertEqual(model['schemaVersion'], 1)

    def test_contract_markers_and_mixins_do_not_expand_native_exports(self):
        source = self.generator.interfaces()
        self.assertIn('HTMLAudioElement =', source)
        self.assertIn('inherit HTMLMediaElement', source)
        self.assertIn('SVGSVGElement =', source)
        self.assertIn('inherit SVGElement', source)
        self.assertIn('ARIAMixin =', source)
        self.assertIn('inherit ARIAMixin', source)
        self.assertIn('inherit ParentNode', source)
        self.assertNotIn('abstract member play:', source)
        self.assertNotIn('HTMLArticleElement', source)
        self.assertFalse(any(function.interface == 'HTMLMediaElement' for function in self.generator.functions))
        model = json.loads(self.generator.api_model())
        self.assertEqual(next(tag for tag in model['tagInterfaces'] if tag['tag'] == 'article')['interface'], 'HTMLElement')
        self.assertIn('HTMLMediaElement.play', self.generator.report())

    def test_import_node_maps_both_boolean_and_dictionary_options(self):
        functions = {function.name for function in self.generator.functions}
        self.assertIn('document_import_node', functions)
        source = self.generator.interfaces()
        self.assertIn('importNode: node: Node * options: bool -> Node', source)
        self.assertIn('importNode: node: Node * options: ImportNodeOptions -> Node', source)

    def test_inline_style_result_has_a_public_contract(self):
        config = json.loads((ROOT / 'gen/dom.json').read_text())
        self.assertIn('CSSStyleProperties', config['contract']['interfaces'])
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleDeclaration { attribute DOMString cssText; };
interface CSSStyleProperties : CSSStyleDeclaration {};
interface mixin ElementCSSInlineStyle { readonly attribute CSSStyleProperties style; };
HTMLElement includes ElementCSSInlineStyle;
''')
        config = dict(self.world.config)
        config['interfaces'] = config['interfaces'] + ['HTMLElement', 'CSSStyleDeclaration']
        config['contract'] = dict(config['contract'])
        config['contract']['interfaces'] = config['contract']['interfaces'] + ['CSSStyleProperties']
        config['contract']['mixins'] = config['contract']['mixins'] | {'ElementCSSInlineStyle': 'ElementCSSInlineStyle'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        source = generator.interfaces()
        self.assertIn('abstract member style: CSSStyleProperties with get', source)
        self.assertIn('CSSStyleProperties =\n    inherit CSSStyleDeclaration', source)
        model = json.loads(generator.api_model())
        getter = next(f for f in model['functions'] if f['function'] == 'rv_dom_html_element_get_style')
        self.assertEqual(getter['contractOwner'], 'ElementCSSInlineStyle')
        self.assertIn('CSSStyleProperties', [i['name'] for i in model['contractInterfaces']])

    def test_configured_table_surface_exports_editor_operations_and_live_collections(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface HTMLCollection { readonly attribute unsigned long length; getter Element? item(unsigned long index); };
interface HTMLTableCaptionElement : HTMLElement {};
interface HTMLTableColElement : HTMLElement { attribute unsigned long span; };
interface HTMLTableCellElement : HTMLElement { attribute unsigned long colSpan; readonly attribute long cellIndex; };
interface HTMLTableRowElement : HTMLElement {
    readonly attribute HTMLCollection cells;
    HTMLElement insertCell(optional long index = -1);
    undefined deleteCell(long index);
};
interface HTMLTableSectionElement : HTMLElement {
    readonly attribute HTMLCollection rows;
    HTMLElement insertRow(optional long index = -1);
    undefined deleteRow(long index);
};
interface HTMLTableElement : HTMLElement {
    readonly attribute HTMLCollection rows;
    readonly attribute HTMLCollection tBodies;
    HTMLTableSectionElement createTBody();
    HTMLElement insertRow(optional long index = -1);
    undefined deleteRow(long index);
};
''')
        tables = {
            'HTMLTableElement', 'HTMLTableSectionElement', 'HTMLTableRowElement',
            'HTMLTableCellElement', 'HTMLTableColElement', 'HTMLTableCaptionElement',
        }
        configured = json.loads((ROOT / 'gen/dom.json').read_text())['interfaces']
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'HTMLElement', 'HTMLCollection'] + [name for name in configured if name in tables]
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        functions = {function['function']: function for function in model['functions']}
        self.assertIn('rv_dom_html_table_element_insert_row', functions)
        self.assertIn('rv_dom_html_table_element_create_t_body', functions)
        self.assertIn('rv_dom_html_table_section_element_delete_row', functions)
        self.assertIn('rv_dom_html_table_row_element_insert_cell', functions)
        self.assertIn('rv_dom_html_table_cell_element_set_col_span', functions)
        self.assertIn('rv_dom_html_table_col_element_set_span', functions)
        rows = functions['rv_dom_html_table_element_get_rows']
        self.assertEqual(rows['returns']['interface'], 'HTMLCollection')
        insert = functions['rv_dom_html_table_element_insert_row']
        self.assertEqual(insert['arguments'][0]['default'], '-1')
        self.assertIn('abstract member insertCell:', generator.interfaces())


    def test_interface_build_and_setting_gates_apply_to_own_and_mixin_members(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[Conditional=INTERFACE, EnabledBySetting=GatedEnabled]
interface GatedElement : Element { [Conditional=OWN] attribute DOMString own; };
interface mixin GatedMixin { attribute DOMString mixed; };
GatedElement includes GatedMixin;
''')
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'GatedElement']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = [f for f in generator.functions if f.interface == 'GatedElement']
        self.assertEqual(len(functions), 4)
        for function in functions:
            self.assertIn('ENABLE(INTERFACE)', function.conditional or '')
        self.assertIn('ENABLE(OWN)', functions[0].conditional)
        self.assertTrue('settings.gatedEnabled' in generator.glue())

    def test_configured_svg_mathml_shared_style_and_focus_members(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface MathMLElement : Element {};
interface CSSStyleDeclaration { attribute DOMString cssText; };
interface mixin ElementCSSInlineStyle { readonly attribute CSSStyleDeclaration style; };
interface mixin HTMLOrSVGOrMathMLElement {
    readonly attribute DOMStringMap dataset;
    attribute DOMString nonce;
    attribute boolean autofocus;
    attribute long tabIndex;
    undefined focus();
    undefined blur();
};
SVGElement includes ElementCSSInlineStyle;
SVGElement includes HTMLOrSVGOrMathMLElement;
MathMLElement includes ElementCSSInlineStyle;
MathMLElement includes HTMLOrSVGOrMathMLElement;
''')
        configured = json.loads((ROOT / 'gen/dom.json').read_text())['interfaces']
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'DOMStringMap', 'CSSStyleDeclaration'] + [
            name for name in configured if name in ['SVGElement', 'MathMLElement']
        ]
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {function['function'] for function in json.loads(generator.api_model())['functions']}
        for prefix in ['svg_element', 'math_ml_element']:
            for member in ['get_style', 'get_dataset', 'get_nonce', 'set_nonce', 'get_autofocus', 'set_autofocus',
                           'get_tab_index', 'set_tab_index', 'focus', 'blur']:
                self.assertIn('rv_dom_' + prefix + '_' + member, functions)

    def test_node_cast_by_tag_checks_namespace_and_tag_before_static_cast(self):
        self.world.config['nodeCastTags'] = {'HTMLModElement': ['del', 'ins']}
        generator = domgen.Generator(self.world)
        expression = generator.cast_expression('HTMLModElement', 'Node', '*nodeOf(target)')
        self.assertIn('dynamicDowncast<HTMLElement>(*nodeOf(target))', expression)
        self.assertIn('element->hasTagName(HTMLNames::delTag)', expression)
        self.assertIn('element->hasTagName(HTMLNames::insTag)', expression)
        self.assertIn('static_cast<HTMLModElement*>(element)', expression)
        self.assertIn(': nullptr', expression)
        self.assertIn('HTMLNames.h', generator.headers)

    def test_configured_html_reflection_scope_includes_selected_semantic_types(self):
        names = ["HTMLBaseElement","HTMLBRElement","HTMLDataElement","HTMLDataListElement","HTMLDirectoryElement","HTMLDListElement","HTMLFontElement","HTMLHeadingElement","HTMLHRElement","HTMLHtmlElement","HTMLMapElement","HTMLMarqueeElement","HTMLMenuElement","HTMLMetaElement","HTMLModElement","HTMLParamElement","HTMLPictureElement","HTMLPreElement","HTMLQuoteElement","HTMLSelectedContentElement","HTMLSourceElement","HTMLTimeElement","HTMLTitleElement"]
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '\n' + '\n'.join(
            'interface ' + name + ' : HTMLElement { attribute DOMString reflection; };'
            for name in names
        ))
        configured = json.loads((ROOT / 'gen/dom.json').read_text())['interfaces']
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'HTMLElement'] + [name for name in configured if name in names]
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        reflected = {function['interface'] for function in model['functions'] if function['member'] == 'reflection'}
        self.assertEqual(reflected, set(names))
        for name in names:
            kinds = {function['kind'] for function in model['functions']
                     if function['interface'] == name and function['member'] == 'reflection'}
            self.assertEqual(kinds, {'getter', 'setter'}, name)


    def test_configured_svg_style_exposes_link_style_sheet(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface StyleSheet {};
interface mixin LinkStyle { readonly attribute StyleSheet? sheet; };
interface SVGStyleElement : SVGElement {
    attribute boolean disabled;
    [Reflect] attribute DOMString type;
    [Reflect] attribute DOMString media;
    [Reflect] attribute DOMString title;
};
SVGStyleElement includes LinkStyle;
''')
        configured = json.loads((ROOT / 'gen/dom.json').read_text())['interfaces']
        config = dict(self.world.config)
        config['interfaces'] = ['Node', 'Element', 'SVGElement', 'StyleSheet'] + [
            name for name in configured if name == 'SVGStyleElement'
        ]
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {function['function']: function for function in json.loads(generator.api_model())['functions']}
        sheet = functions['rv_dom_svg_style_element_get_sheet']
        self.assertEqual(sheet['returns']['interface'], 'StyleSheet')
        self.assertTrue(sheet['returns']['nullable'])
        self.assertIn('SVGElementTypeHelpers.h', generator.glue())
        for member in ['disabled', 'type', 'media', 'title']:
            self.assertIn('rv_dom_svg_style_element_get_' + member, functions)
            self.assertIn('rv_dom_svg_style_element_set_' + member, functions)


if __name__ == '__main__':
    unittest.main()
