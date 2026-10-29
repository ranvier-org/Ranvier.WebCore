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

    def test_css_rule_and_descriptor_settings_use_owner_or_constructor_document(self):
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
        self.assertIn('settingsSheet->ownerDocument()', glue)
        self.assertIn('settingsSheet->constructorDocument()', glue)
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
