import json
import pathlib
import re
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
    def svg_matrix_generator(self, argument='optional DOMMatrix2DInit matrix = {}', configured=None):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
dictionary DOMMatrix2DInit { unrestricted double a; unrestricted double m11; };
interface SVGTransform { undefined setMatrix(''' + argument + '''); };
partial interface SVGSVGElement { SVGTransform createSVGTransformFromMatrix(''' + argument + '''); };
interface SVGTransformList { SVGTransform createSVGTransformFromMatrix(''' + argument + '''); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(dict.fromkeys(list(config['interfaces']) + ['SVGSVGElement', 'SVGTransform', 'SVGTransformList']))
        config['svgMatrixDictionaryBindings'] = configured if configured is not None else ['SVGSVGElement.createSVGTransformFromMatrix', 'SVGTransform.setMatrix', 'SVGTransformList.createSVGTransformFromMatrix']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        return generator

    def test_svg_matrix_dictionary_bindings_reuse_engine_alias_validation(self):
        generator = self.svg_matrix_generator()
        generator.run()
        glue = generator.glue()
        self.assertEqual(glue.count('DOMMatrixReadOnly::validateAndFixup(a0)'), 3)
        for short, alias in zip('abcdef', ['m11', 'm12', 'm21', 'm22', 'm41', 'm42']):
            self.assertEqual(glue.count(f'a0.{short} = a0.{alias};'), 3)
        self.assertIn('return Ranvier::recordException(matrixValidation0.releaseException());', glue)

    def test_svg_matrix_dictionary_bindings_reject_unknown_member(self):
        with self.assertRaisesRegex(SystemExit, 'unsupported SVG matrix dictionary binding'):
            self.svg_matrix_generator(configured=['SVGTransform.other']).run()

    def test_svg_matrix_dictionary_browser_adapters_create_genuine_svg_matrices(self):
        generator = self.svg_matrix_generator()
        generator.run()
        shared = generator.interfaces()
        self.assertEqual(shared.count('globalThis.DOMMatrix.fromMatrix(d??{})'), 3)
        self.assertEqual(shared.count("globalThis.document.createElementNS('http://www.w3.org/2000/svg','svg').createSVGMatrix()"), 3)
        self.assertIn('return v.setMatrix(m);})($0,$1)', shared)
        self.assertEqual(shared.count('return v.createSVGTransformFromMatrix(m);})($0,$1)'), 2)

    def test_svg_matrix_dictionary_bindings_reject_wrong_argument_shape(self):
        for argument in ['DOMString matrix', 'DOMMatrix2DInit other', 'DOMMatrix2DInit matrix, long extra', 'DOMMatrix2DInit? matrix']:
            with self.subTest(argument=argument), self.assertRaisesRegex(SystemExit, 'one nonnullable DOMMatrix2DInit matrix argument'):
                self.svg_matrix_generator(argument=argument).run()

    def test_existing_atom_string_inputs_use_lookup_without_interning(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
partial interface Document {
    Element? lookupExisting([RequiresExistingAtomString] DOMString name);
    Element? lookupOrdinary(DOMString name);
};
''')
        generator = domgen.Generator(domgen.World(self.source, dict(self.world.config)))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        self.assertTrue('impl->lookupExisting(StringView { a0.string() }.toExistingAtomString())' in glue)
        self.assertTrue('impl->lookupOrdinary(a0.string())' in glue)

    def test_svg_animated_getters_use_webkit_animated_accessors_after_implemented_as(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface SVGAnimatedNumber { attribute float baseVal; };
partial interface SVGElement {
    readonly attribute SVGAnimatedNumber count;
    [ImplementedAs=alternate] readonly attribute SVGAnimatedNumber renamed;
    readonly attribute float ordinary;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(dict.fromkeys(list(config['interfaces']) + ['SVGElement', 'SVGAnimatedNumber']))
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        for expression in ['impl->countAnimated()', 'impl->alternateAnimated()', 'impl->ordinary()', 'impl->baseVal()']:
            self.assertTrue(expression in glue, expression)

    def test_svg_animated_string_setter_completes_its_cpp_variant_parameter(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '\ninterface SVGAnimatedString { attribute DOMString baseVal; };\n')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['SVGAnimatedString']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        self.assertTrue('#include "TrustedScriptURL.h"' in generator.glue())

    def test_scoped_interface_header_override_uses_the_real_cpp_alias_declaration(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '\ninterface SVGAnimatedNumber { attribute float baseVal; };\n')
        header = self.source / 'Source/WebCore/dom/AliasDeclarations.h'
        header.write_text('// Test alias declaration header.\n')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['SVGAnimatedNumber']
        config['interfaceHeaders'] = {'SVGAnimatedNumber': 'dom/AliasDeclarations.h'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        self.assertTrue('#include "dom/AliasDeclarations.h"' in glue)
        self.assertTrue('#include "SVGAnimatedNumber.h"' not in glue)

    def test_interface_header_override_rejects_unselected_missing_and_external_headers(self):
        for name, header, error in [
            ('NotSelected', 'dom/Fixture.h', 'selected interface'),
            ('Node', 'dom/Missing.h', 'exist inside WebCore'),
            ('Node', '../Outside.h', 'WebCore-relative header'),
            ('Node', '/Absolute.h', 'WebCore-relative header'),
            ('Node', 'C:/Absolute.h', 'WebCore-relative header'),
        ]:
            with self.subTest(name=name, header=header):
                config = dict(self.world.config)
                config['interfaceHeaders'] = {name: header}
                with self.assertRaisesRegex(SystemExit, error):
                    domgen.Generator(domgen.World(self.source, config))

    def test_selected_browser_transform_matrix_flags_copy_only_the_measured_false_flag_case(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface DOMMatrixReadOnly {};
interface DOMMatrix : DOMMatrixReadOnly {};
interface CSSTransformComponent { attribute boolean is2D; DOMMatrix toMatrix(); };
interface CSSTransformValue : CSSStyleValue { readonly attribute boolean is2D; DOMMatrix toMatrix(); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'DOMMatrixReadOnly', 'DOMMatrix', 'CSSTransformComponent', 'CSSTransformValue']
        config['browserMatrixFlagAdapters'] = ['CSSTransformComponent.toMatrix', 'CSSTransformValue.toMatrix']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        shared = generator.interfaces()
        self.assertEqual(shared.count('v.is2D===false&&m.is2D===true'), 2)
        self.assertIn('new m.constructor([m.m11,m.m12,m.m13,m.m14,m.m21,m.m22,m.m23,m.m24,m.m31,m.m32,m.m33,m.m34,m.m41,m.m42,m.m43,m.m44])', shared)
        self.assertIn(':m;})($0)', shared)

    def test_browser_matrix_flag_adapter_rejects_other_matrix_operations(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface DOMMatrix {};
interface CSSTransformComponent { DOMMatrix anotherMatrix(); };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['DOMMatrix', 'CSSTransformComponent']
        config['browserMatrixFlagAdapters'] = ['CSSTransformComponent.anotherMatrix']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        with self.assertRaisesRegex(SystemExit, 'plain zero-argument DOMMatrix operation'):
            generator.interfaces()

    def test_selected_transform_browser_adapters_brand_numeric_subtypes_and_guard_index_and_reference_coercion(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue {};
typedef (double or CSSNumericValue) CSSNumberish;
typedef (DOMString or CSSOMKeywordValue) CSSOMKeywordish;
typedef (CSSNumericValue or CSSOMKeywordish) CSSPerspectiveValue;
interface CSSTransformComponent {};
interface CSSScale : CSSTransformComponent { attribute CSSNumberish x; };
interface CSSPerspective : CSSTransformComponent { attribute CSSPerspectiveValue length; };
interface CSSTransformValue : CSSStyleValue {
    getter CSSTransformComponent (unsigned long index);
    setter undefined (unsigned long index, CSSTransformComponent val);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSOMKeywordValue', 'CSSTransformComponent', 'CSSScale', 'CSSPerspective', 'CSSTransformValue']
        config['flattenUnionTypedefs'] = ['CSSPerspectiveValue']
        config['validatedReferenceUnions'] = ['DoubleOrCSSNumericValue', 'CSSNumericValueOrDOMStringOrCSSOMKeywordValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        shared = generator.interfaces()
        self.assertIn('globalThis.CSSNumericValue.prototype.type.call(v)', shared)
        self.assertIn("globalThis.CSSKeywordValue.prototype,'value').get.call(v)", shared)
        self.assertIn('if not (isCSSNumericValue (box value)) then', shared)
        self.assertIn('if not (isCSSOMKeywordValue (box value)) then', shared)
        self.assertIn('if(i===4294967295)throw new RangeError', shared)
        self.assertNotIn("Object.prototype.toString.call($0) === '[object CSSNumericValue]'", shared)

    def test_selected_transform_setters_validate_dimensions_before_calling_engine_mutators(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
typedef (double or CSSNumericValue) CSSNumberish;
interface CSSTranslate { attribute CSSNumericValue x; };
interface CSSScale { attribute CSSNumberish x; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSTranslate', 'CSSScale']
        config['setterValueChecks'] = {'CSSTranslate.x': 'css-length-or-percentage', 'CSSScale.x': 'css-numberish-number'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        translation = next(function for function in generator.functions if function.name == 'css_translate_set_x')
        scale = next(function for function in generator.functions if function.name == 'css_scale_set_x')
        translation_body, scale_body = '\n'.join(translation.body), '\n'.join(scale.body)
        self.assertIn('a0->type().matchesTypeOrPercentage<CSSNumericBaseType::Length>()', translation_body)
        self.assertLess(translation_body.index('matchesTypeOrPercentage'), translation_body.index('impl->setX'))
        self.assertIn('numeric->type().matchesNumber()', scale_body)
        self.assertLess(scale_body.index('matchesNumber'), scale_body.index('impl->setX'))
        self.assertIn('ExceptionCode::TypeError', scale_body)
        bad = dict(config)
        bad['setterValueChecks'] = {'CSSScale.x': 'css-length-or-percentage'}
        with self.assertRaisesRegex(SystemExit, 'setter check.*requires CSSNumericValue'):
            domgen.Generator(domgen.World(self.source, bad)).run()

    def test_selected_const_numeric_getter_retains_a_checked_declared_reference_without_global_const_casts(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
interface CSSTranslate { attribute CSSNumericValue x; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSTranslate']
        config['constGetterBindings'] = {'CSSTranslate.x': {'interface': 'CSSNumericValue', 'root': 'CSSStyleValue'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        self.assertIn('storeConstGetter<CSSStyleValue, CSSNumericValue>(value, result)', glue)
        self.assertIn('static_assert(std::is_lvalue_reference_v<V> && std::is_const_v<std::remove_reference_t<V>>);', glue)
        self.assertIn('static_assert(std::is_same_v<std::remove_cvref_t<V>, Declared>);', glue)
        self.assertIn('static_assert(std::is_polymorphic_v<Root>);', glue)
        self.assertIn('static_cast<Root*>(const_cast<Declared*>(&value))', glue)
        self.assertIn('Root* pointer = rawPointer<Root>(std::forward<V>(value));', glue)
        bad = dict(config)
        bad['constGetterBindings'] = {'CSSTranslate.x': {'interface': 'CSSStyleValue', 'root': 'CSSStyleValue'}}
        with self.assertRaisesRegex(SystemExit, 'const getter.*declared interface/root'):
            domgen.Generator(domgen.World(self.source, bad)).run()

    def test_selected_restricted_numeric_union_inputs_reject_nonfinite_values_without_restricting_geometry(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSNumericValue {};
typedef (double or CSSNumericValue) CSSNumberish;
typedef (unrestricted double or CSSNumericValue) GeometryNumberish;
partial interface Node {
    undefined restricted(CSSNumberish value);
    undefined unrestricted(GeometryNumberish value);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSNumericValue']
        config['finiteUnionInputs'] = ['DoubleOrCSSNumericValue', 'UnrestrictedDoubleOrCSSNumericValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {row['function']: row for row in json.loads(generator.api_model())['functions']}
        restricted = functions['rv_dom_node_restricted']['arguments'][0]['mapping']['subtypes'][0]
        unrestricted = functions['rv_dom_node_unrestricted']['arguments'][0]['mapping']['subtypes'][0]
        self.assertTrue(restricted.get('finiteInput', False))
        self.assertNotIn('finiteInput', unrestricted)
        glue = generator.glue()
        self.assertEqual(glue.count('!std::isfinite(source->arm0)'), 1)
        self.assertIn('status = Ranvier::recordException(Exception { ExceptionCode::TypeError, "A finite numeric value is required."_s });', glue)

    def test_selected_perspective_typedef_flattens_nested_union_for_cpp_and_shared_contracts(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue {};
typedef (DOMString or CSSOMKeywordValue) CSSOMKeywordish;
typedef (CSSNumericValue or CSSOMKeywordish) CSSPerspectiveValue;
interface CSSTransformComponent {};
interface CSSPerspective : CSSTransformComponent {
    constructor(CSSPerspectiveValue length);
    attribute CSSPerspectiveValue length;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSOMKeywordValue', 'CSSTransformComponent', 'CSSPerspective']
        config['constructors'] = {'CSSPerspective': {'receiver': 'Document', 'factory': 'CSSPerspective::create', 'passReceiver': False}}
        config['flattenUnionTypedefs'] = ['CSSPerspectiveValue']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        factory = next(row for row in json.loads(generator.api_model())['functions'] if row['function'] == 'rv_dom_css_perspective_create')
        mapping = factory['arguments'][0]['mapping']
        self.assertEqual([child['kind'] for child in mapping['subtypes']], ['object', 'string', 'object'])
        self.assertIn('Variant<Ref<CSSNumericValue>, String, Ref<CSSOMKeywordValue>>', generator.glue())
        shared = generator.interfaces()
        self.assertIn('| CSSNumericValue of CSSNumericValue', shared)
        self.assertIn('| DOMString of string', shared)
        self.assertIn('| CSSOMKeywordValue of CSSOMKeywordValue', shared)
        self.assertNotIn('| DOMStringOrCSSOMKeywordValue of', shared)
        unselected = dict(config)
        unselected.pop('flattenUnionTypedefs')
        untouched = domgen.World(self.source, unselected).map(domgen.idl.Type('CSSPerspectiveValue'))
        self.assertEqual([child.kind for child in untouched.subtypes], ['object', 'union'])

    def test_overloaded_component_constructors_use_arity_exports_and_preserve_a_locked_plain_name(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSNumericValue : CSSStyleValue {};
interface CSSTransformComponent {};
interface CSSRotate : CSSTransformComponent {
    constructor(CSSNumericValue angle);
    constructor(double x, double y, double z, CSSNumericValue angle);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSNumericValue', 'CSSTransformComponent', 'CSSRotate']
        config['constructors'] = {'CSSRotate': {'receiver': 'Document', 'factory': 'CSSRotate::create', 'passReceiver': False}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        factories = {function.name: function for function in generator.functions if function.kind == 'constructor'}
        self.assertEqual(set(factories), {'css_rotate_create_1', 'css_rotate_create_4'})
        self.assertIn('CSSRotate::create(HandleArg<CSSNumericValue> { a0.get() })', generator.glue())
        locked = {'params': factories['css_rotate_create_1'].params, 'comment': factories['css_rotate_create_1'].comment}
        subsequent = domgen.Generator(domgen.World(self.source, config))
        subsequent.lock = {'css_rotate_create': locked}
        subsequent.lock_structs = {}
        subsequent.run()
        subsequent_factories = {function.name: function for function in subsequent.functions if function.kind == 'constructor'}
        self.assertEqual(set(subsequent_factories), {'css_rotate_create', 'css_rotate_create_4'})
        self.assertEqual(subsequent_factories['css_rotate_create'].params, locked['params'])
        self.assertEqual(subsequent.stubs, [])
        regenerated = domgen.Generator(domgen.World(self.source, config))
        regenerated.lock = {name: {'params': function.params, 'comment': function.comment}
                            for name, function in factories.items()}
        regenerated.lock_structs = {}
        regenerated.run()
        self.assertEqual({function.name for function in regenerated.functions if function.kind == 'constructor'}, set(factories))
        self.assertEqual(regenerated.stubs, [])

    def test_same_arity_component_constructors_fail_closed_when_exports_cannot_disambiguate(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSNumericValue {};
interface CSSRotate {
    constructor(CSSNumericValue angle);
    constructor(double angle);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSNumericValue', 'CSSRotate']
        config['constructors'] = {'CSSRotate': {'receiver': 'Document', 'factory': 'CSSRotate::create', 'passReceiver': False}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        with self.assertRaisesRegex(SystemExit, 'generated names collide.*css_rotate_create_1'):
            generator.run()

    def test_optional_matrix_constructor_union_keeps_absence_distinct_from_present_empty_values(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface DOMMatrixReadOnly {
    [CallWith=CurrentScriptExecutionContext] constructor(optional (DOMString or sequence<unrestricted double>) init);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['DOMMatrixReadOnly']
        config['constructors'] = {'DOMMatrixReadOnly': {'receiver': 'Document', 'factory': 'DOMMatrixReadOnly::create'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        model = json.loads(generator.api_model())
        factory = next(row for row in model['functions'] if row['function'] == 'rv_dom_dom_matrix_read_only_create')
        self.assertTrue(factory['arguments'][0]['optional'])
        self.assertFalse(factory['arguments'][0]['mapping']['nullable'])
        glue = generator.glue()
        self.assertIn('std::optional<Variant<String, Vector<double>>> a0;', glue)
        self.assertIn('if (init) {', glue)
        self.assertIn('a0 = decodeRvDomUnionDOMStringOrSequenceOfUnrestrictedDouble(init, status0);', glue)
        self.assertIn('DOMMatrixReadOnly::create(*impl, std::move(a0))', glue)
        self.assertNotIn('DOMMatrixReadOnly::create(*impl, std::move(*a0))', glue)
        self.assertIn('RV_DOM_UNION_DOM_STRING_OR_SEQUENCE_OF_UNRESTRICTED_DOUBLE_SEQUENCE_UNRESTRICTED_DOUBLE = 2', generator.header())

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
        config['trackedHandleRoots'] = {root: concrete for root, concrete in configured['trackedHandleRoots'].items()
                                        if root in selected}
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
        self.assertIn('RvDomUtf8StringInput label;', generator.header())
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
        config['browserWellFormedUnions'] = ['CSSStyleValueOrUSVString']
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

    def form_data_generator(self, extra=''):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
dictionary EventInit { boolean bubbles = false; [ImplementedAs=trustedForBindingsOnly] boolean trusted = false; };
interface File {};
typedef (File or USVString) FormDataEntryValue;
interface DOMFormData {
    undefined append(USVString name, USVString value);
    FormDataEntryValue? get(USVString name);
    sequence<FormDataEntryValue> getAll(USVString name);
    iterable<USVString, FormDataEntryValue>;
};
dictionary FormDataEventInit : EventInit { required DOMFormData formData; };
interface FormDataEvent : Event {
    constructor([AtomString] DOMString type, FormDataEventInit eventInitDict);
    readonly attribute DOMFormData formData;
};
''' + extra)
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['DOMFormData', 'FormDataEvent']
        config['exclude'] = list(config['exclude']) + ['EventInit.trusted']
        config['opaqueUnionArms'] = ['File']
        config['browserWellFormedUnions'] = ['FileOrUSVString']
        config['browserWellFormedSetters'] = ['DOMFormData']
        config['objectContexts'] = {'DOMFormData': 'Document'}
        config['iterableBindings'] = {'DOMFormData': {'feature': 'dom-form-data-entries'}}
        config['dictionaryObjectMembers'] = ['FormDataEventInit.formData']
        config['dictionaryCppTypes'] = {'FormDataEventInit': 'FormDataEvent::Init'}
        config['eventInterfaceCasts'] = ['FormDataEvent']
        config['constructors'] = {'FormDataEvent': {'receiver': 'Document', 'factory': 'FormDataEvent::create',
                                                    'passReceiver': False}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        return generator

    def test_opaque_union_arm_returns_a_tag_with_a_null_payload_and_no_decoder(self):
        generator = self.form_data_generator()
        names = {function.name for function in generator.functions}
        self.assertTrue({'dom_form_data_get', 'dom_form_data_get_all', 'dom_form_data_entries'} <= names)
        header = generator.header()
        self.assertIn('void* arm0; /* File: NULL; the tag identifies the arm */', header)
        self.assertIn('RvDomUtf8StringSpan arm1;', header)
        glue = generator.glue()
        self.assertNotIn('decodeRvDomUnionFileOrUSVString', glue)
        self.assertIn('result->arm0 = nullptr;', glue)

    def test_opaque_union_arm_is_refused_as_an_input_or_a_bare_result(self):
        generator = self.form_data_generator('''
partial interface DOMFormData { undefined take(FormDataEntryValue value); File file(); };
''')
        names = {function.name for function in generator.functions}
        self.assertNotIn('dom_form_data_take', names)
        self.assertNotIn('dom_form_data_file', names)
        reasons = dict(generator.excluded)
        self.assertEqual('an opaque interface is a union result arm only', reasons['DOMFormData.take'])
        self.assertEqual('an opaque interface is a union result arm only', reasons['DOMFormData.file'])

    def test_required_dictionary_object_member_builds_the_init_with_its_reference(self):
        generator = self.form_data_generator()
        self.assertIn('RvDOMFormData* form_data; /* DOMFormData, required */', generator.header())
        self.assertNotIn('trusted', generator.header().split('RvDomFormDataEventInit {')[1].split('}')[0])
        glue = generator.glue()
        self.assertIn('FormDataEvent::Init a1 { { }, a1form_data.releaseNonNull() };', glue)
        self.assertIn('event.interfaceType() == EventInterfaceType::FormDataEvent', glue)

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
        config['browserWellFormedUnions'] = ['USVStringOrCSSOMVariableReferenceValue']
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
        config['browserWellFormedSetters'] = ['CSSOMKeywordValue']
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
        config['browserWellFormedUnions'] = ['USVStringOrCSSOMVariableReferenceValue']
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

    def test_every_setter_takes_a_length_delimited_string(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface CSSStyleValue {};
interface CSSOMKeywordValue : CSSStyleValue { attribute USVString value; };
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleValue', 'CSSOMKeywordValue']
        config['browserWellFormedSetters'] = ['CSSOMKeywordValue']
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
        self.assertEqual(functions['rv_dom_element_set_id']['parameters'][1:],
                         [{'ctype': 'const uint8_t*', 'name': 'value'}, {'ctype': 'int32_t', 'name': 'value_length'}])
        self.assertEqual(functions['rv_dom_element_set_id']['stringInputs'], 'utf8-lengths')

    def test_union_string_arms_carry_byte_lengths(self):
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
        config['browserWellFormedUnions'] = ['USVStringOrCSSOMVariableReferenceValue']
        config['constructors'] = {'CSSUnparsedValue': {
            'receiver': 'Document', 'factory': 'CSSUnparsedValue::create', 'passReceiver': False,
        }}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        header = generator.header()
        self.assertTrue('RvDomUtf8StringSpan arm0;' in header)
        self.assertNotIn('const char* arm', header)
        model = json.loads(generator.api_model())
        functions = {item['function']: item for item in model['functions']}
        item = functions['rv_dom_css_unparsed_value_item']
        self.assertTrue(item['returns']['nullable'])
        self.assertEqual(item['returns']['subtypes'][0]['stringTransport'], 'utf8-lengths')
        other = functions['rv_dom_node_get_state']['returns']['subtypes'][1]
        self.assertEqual(other['stringTransport'], 'utf8-lengths')
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
            'passReceiver': False,
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
            'feature': 'dom-css-style-values',
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
        config['namespaceBindings'] = {'DOMCSSNamespace': {
            'receiver': 'Document', 'members': ['supports', 'registerProperty'],
            'feature': 'dom-css-supports', 'memberFeatures': {'registerProperty': 'dom-css-register-property'},
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
        self.assertIn('RvDomUtf8StringInput label;', header)
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
            'feature': 'dom-computed-style',
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

    def test_element_array_reflections_bind_the_engine_element_arrays(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
partial interface Element {
    [CustomGetter, Reflect="aria-labelledby"] attribute FrozenArray<Element>? ariaLabelledByElements;
    [CustomGetter, Reflect="aria-owns"] attribute FrozenArray<Element>? ariaOwnsElements;
};
''')
        config = dict(self.world.config)
        config['elementArrayReflections'] = ['Element.ariaLabelledByElements']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertEqual(functions['rv_dom_element_get_aria_labelled_by_elements']['parameters'][-1],
                         {'ctype': 'RvDomSequenceElementNullable*', 'name': 'result'})
        self.assertEqual(functions['rv_dom_element_set_aria_labelled_by_elements']['parameters'][-1],
                         {'ctype': 'const RvDomSequenceElementNullable*', 'name': 'value'})
        self.assertNotIn('rv_dom_element_get_aria_owns_elements', functions)
        glue = generator.glue()
        self.assertIn('impl->getElementsArrayAttributeForBindings(HTMLNames::aria_labelledbyAttr)', glue)
        self.assertIn('impl->setElementsArrayAttribute(HTMLNames::aria_labelledbyAttr, std::move(*a0))', glue)

    def test_event_target_objects_use_event_target_handles_and_report_detached(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[EnabledBySetting=ViewportApi] interface Viewport : EventTarget {
    readonly attribute double width;
    attribute EventHandler onresize;
};
[InterfaceName=Window, Exposed=Window] interface DOMWindow : EventTarget {};
[EnabledBySetting=ViewportApi] partial interface DOMWindow {
    [SameObject] readonly attribute Viewport viewport;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['Viewport']
        config['creationGatedInterfaces'] = {'Viewport': 'DOMWindow.viewport'}
        config['eventTargetObjects'] = {'Viewport': {'attached': 'impl->frame()'}}
        config['windowBindings'] = {'DOMWindow': [{'receiver': 'Document', 'members': ['viewport'], 'feature': 'viewport-object'}]}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertEqual(functions['rv_dom_viewport_get_width']['parameters'], [{'ctype': 'RvEventTarget*', 'name': 'target'}, {'ctype': 'double*', 'name': 'result'}])
        self.assertEqual(functions['rv_dom_window_get_viewport']['parameters'][-1], {'ctype': 'RvEventTarget**', 'name': 'result'})
        self.assertNotIn('Viewport', generator.handles)
        glue = generator.glue()
        self.assertIn('dynamicDowncast<Viewport>(*reinterpret_cast<EventTarget*>(target))', glue)
        self.assertIn('if (!(impl->frame()))' + chr(10) + '        return RV_ERR_DETACHED;', glue)
        self.assertIn('storeHandle<EventTarget>(value, result)', glue)
        self.assertNotIn('settings.viewportApi', glue.split('ranvier_dom_viewport_get_width', 1)[1].split(chr(10) + '}', 1)[0])

    def test_window_bindings_list_reads_readonly_attributes_and_overloads_per_feature(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
typedef USVString CSSOMString;
interface CSSStyleDeclaration { DOMString getPropertyValue(DOMString property); };
[InterfaceName=Window, Exposed=Window] interface DOMWindow : EventTarget {};
partial interface DOMWindow {
    [NewObject] CSSStyleDeclaration getComputedStyle(Element element, optional CSSOMString? pseudoElement = null);
    [Replaceable] readonly attribute double scrollX;
    [Replaceable, ImplementedAs=scrollX] readonly attribute double pageXOffset;
    undefined scrollTo(unrestricted double x, unrestricted double y);
    undefined scrollBy(unrestricted double x, unrestricted double y);
    [ImplementedAs=scrollTo] undefined scroll(unrestricted double x, unrestricted double y);
    attribute DOMString name;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['CSSStyleDeclaration']
        computed = {'receiver': 'Document', 'members': ['getComputedStyle'], 'feature': 'dom-computed-style'}
        scrolling = {'receiver': 'Document', 'members': ['scrollX', 'pageXOffset', 'scrollTo', 'scroll'], 'feature': 'dom-window-scrolling'}
        config['windowBindings'] = {'DOMWindow': [computed, scrolling]}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertEqual(functions['rv_dom_window_get_computed_style']['feature'], 'dom-computed-style')
        for name in ['rv_dom_window_get_scroll_x', 'rv_dom_window_get_page_x_offset', 'rv_dom_window_scroll_to', 'rv_dom_window_scroll']:
            self.assertEqual(functions[name]['feature'], 'dom-window-scrolling', name)
            self.assertEqual(functions[name]['contractOwner'], 'Window', name)
        self.assertNotIn('rv_dom_window_scroll_by', functions)
        self.assertEqual(functions['rv_dom_window_get_scroll_x']['parameters'], [{'ctype': 'RvNode*', 'name': 'target'}, {'ctype': 'double*', 'name': 'result'}])
        glue = generator.glue()
        self.assertEqual(glue.count('impl->window()->scrollX(); }'), 2)
        self.assertIn('impl->window()->scrollTo(x, y)', glue)
        self.assertIn('"dom-window-scrolling"', glue)
        config['windowBindings'] = {'DOMWindow': {'receiver': 'Document', 'members': ['name'], 'feature': 'f'}}
        with self.assertRaisesRegex(SystemExit, 'not an operation or a readonly attribute'):
            domgen.Generator(domgen.World(self.source, config)).run()

    def window_object_generator(self, extra, **overrides):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=Window, Exposed=Window] interface DOMWindow : EventTarget {};
interface mixin WindowOrWorkerGlobalScope {};
DOMWindow includes WindowOrWorkerGlobalScope;
partial interface mixin WindowOrWorkerGlobalScope { [SameObject] readonly attribute Crypto crypto; };
''' + extra)
        config = dict(self.world.config)
        config['windowObjectBindings'] = {'Crypto': {
            'receiver': 'Document', 'accessor': 'crypto', 'members': ['getRandomValues', 'randomUUID'],
            'feature': 'dom-crypto-random'}}
        config['typedArrayViewTypes'] = ['ArrayBufferView']
        config.update(overrides)
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        return generator

    CRYPTO = '''
[Exposed=(Window,Worker)] interface Crypto {
    ArrayBufferView getRandomValues([ReturnValue] ArrayBufferView array);
    [SecureContext] DOMString randomUUID();
};
'''

    def test_window_object_binding_calls_the_member_through_the_window_accessor(self):
        generator = self.window_object_generator(self.CRYPTO)
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        uuid = functions['rv_dom_crypto_random_uuid']
        self.assertEqual('context_operation', uuid['kind'])
        self.assertEqual('Document', uuid['receiver'])
        self.assertEqual('Crypto', uuid['contractOwner'])
        self.assertEqual('dom-crypto-random', uuid['feature'])
        self.assertEqual('facade', uuid['binding'])
        self.assertEqual([{'ctype': 'RvNode*', 'name': 'target'}, {'ctype': 'char*', 'name': 'buffer'},
                          {'ctype': 'int32_t', 'name': 'capacity'}, {'ctype': 'int32_t*', 'name': 'length'}], uuid['parameters'])
        glue = generator.glue()
        self.assertIn('impl->window()->crypto().randomUUID()', glue)
        self.assertIn('if (!impl->window())', glue)
        self.assertIn('"dom-crypto-random"', glue)
        self.assertNotIn('type Crypto =', generator.interfaces())

    def test_return_value_typed_array_view_is_an_in_out_span_with_its_element_kind(self):
        generator = self.window_object_generator(self.CRYPTO)
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        random = functions['rv_dom_crypto_get_random_values']
        self.assertEqual([{'ctype': 'RvNode*', 'name': 'target'}, {'ctype': 'int32_t', 'name': 'array_kind'},
                          {'ctype': 'uint8_t*', 'name': 'array'}, {'ctype': 'int32_t', 'name': 'array_length'}],
                         random['parameters'])
        self.assertEqual('typedarray', random['arguments'][0]['mapping']['kind'])
        header = generator.header()
        for name, value in [('INT8', 0), ('UINT8', 1), ('UINT8_CLAMPED', 2), ('INT16', 3), ('UINT16', 4), ('INT32', 5),
                            ('UINT32', 6), ('FLOAT16', 7), ('FLOAT32', 8), ('FLOAT64', 9), ('BIG_INT64', 10),
                            ('BIG_UINT64', 11), ('DATA_VIEW', 12)]:
            self.assertIn(f'RV_DOM_ARRAY_BUFFER_VIEW_{name} = {value},', header)
        glue = generator.glue()
        self.assertIn('makeTypedArrayView(array_kind, array, array_length, status0)', glue)
        self.assertIn('impl->window()->crypto().getRandomValues(*a0)', glue)
        self.assertIn('copyTypedArrayView(*a0, array)', glue)
        self.assertIn('"JavaScriptCore/TypedArrays.h"', glue)
        self.assertIn('(array_length >= 0 && (array_length == 0 || array))', glue)
        self.assertIn('byte[] array', generator.fsharp())

    SCREEN = '''
[Exposed=Window] interface Screen {
    readonly attribute long width;
    readonly attribute unsigned long colorDepth;
    [ImplementedAs=colorDepth] readonly attribute unsigned long pixelDepth;
    [SameObject, EnabledBySetting=ScreenOrientationAPIEnabled] readonly attribute ScreenOrientation orientation;
};
enum OrientationType { "portrait-primary", "portrait-secondary", "landscape-primary", "landscape-secondary" };
[Exposed=Window, EnabledBySetting=ScreenOrientationAPIEnabled] interface ScreenOrientation : EventTarget {
    readonly attribute OrientationType type;
    readonly attribute unsigned short angle;
};
partial interface mixin WindowOrWorkerGlobalScope { [SameObject] readonly attribute Screen screen; };
'''

    def screen_generator(self, **overrides):
        return self.window_object_generator(self.CRYPTO + self.SCREEN, **{'windowObjectBindings': {
            'Screen': {'receiver': 'Document', 'accessor': 'screen', 'members': ['width', 'colorDepth', 'pixelDepth'],
                       'feature': 'dom-screen'},
            'ScreenOrientation': {'receiver': 'Document', 'accessor': 'screen.orientation', 'members': ['type', 'angle'],
                                  'feature': 'dom-screen-orientation'}}, **overrides})

    def test_window_object_bindings_read_readonly_attributes_through_the_accessor(self):
        generator = self.screen_generator()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        width = functions['rv_dom_screen_get_width']
        self.assertEqual('context_operation', width['kind'])
        self.assertEqual('Screen', width['contractOwner'])
        self.assertEqual('dom-screen', width['feature'])
        self.assertEqual([{'ctype': 'RvNode*', 'name': 'target'}, {'ctype': 'int32_t*', 'name': 'result'}], width['parameters'])
        glue = generator.glue()
        self.assertIn('impl->window()->screen().width()', glue)
        self.assertEqual(2, glue.count('impl->window()->screen().colorDepth()'))
        self.assertIn('rv_dom_screen_get_pixel_depth', functions)

    def test_a_dotted_accessor_reaches_a_nested_object_and_keeps_its_setting_gate(self):
        generator = self.screen_generator()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        kind = functions['rv_dom_screen_orientation_get_type']
        self.assertEqual('ScreenOrientation', kind['contractOwner'])
        self.assertEqual([{'ctype': 'RvNode*', 'name': 'target'}, {'ctype': 'int32_t*', 'name': 'result'}], kind['parameters'])
        glue = generator.glue()
        self.assertIn('impl->window()->screen().orientation().type()', glue)
        self.assertIn('impl->window()->screen().orientation().angle()', glue)
        self.assertIn('ScreenOrientationAPIEnabled', glue)
        self.assertIn('RV_DOM_ORIENTATION_TYPE_LANDSCAPE_PRIMARY', generator.header())

    def test_a_dotted_accessor_requires_each_step_to_be_a_readonly_attribute_of_the_next_interface(self):
        with self.assertRaisesRegex(SystemExit, 'Window object bindings require a readonly Window attribute'):
            self.screen_generator(windowObjectBindings={'ScreenOrientation': {
                'receiver': 'Document', 'accessor': 'screen.missing', 'members': ['type'], 'feature': 'f'}})

    def test_typed_array_view_requires_a_top_level_return_value_argument(self):
        generator = self.window_object_generator('''
[Exposed=Window] interface Crypto {
    undefined fill(ArrayBufferView array);
    undefined fillAll(sequence<ArrayBufferView> arrays);
    readonly attribute DOMString unused;
};
''', windowObjectBindings={})
        names = [item.name for item in generator.functions]
        self.assertNotIn('crypto_fill', names)
        with self.assertRaisesRegex(SystemExit, r'Crypto.fill: typed array view argument without \[ReturnValue\]'):
            self.window_object_generator('''
[Exposed=Window] interface Crypto { undefined fill(ArrayBufferView array); };
''', windowObjectBindings={'Crypto': {'receiver': 'Document', 'accessor': 'crypto', 'members': ['fill'],
                                        'feature': 'f'}})
        with self.assertRaisesRegex(SystemExit, 'Window object bindings require a readonly Window attribute'):
            self.window_object_generator(self.CRYPTO, windowObjectBindings={'Crypto': {
                'receiver': 'Document', 'accessor': 'missing', 'members': ['randomUUID'], 'feature': 'f'}})

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

    def collection_generator(self, setlike=True, maplike=True, extra_config=None):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
interface AbstractRange {};
enum HighlightType { "highlight", "spelling-error" };
interface Highlight {
    constructor(AbstractRange... initialRanges);
    setlike<AbstractRange>;
    attribute long priority;
    attribute HighlightType type;
};
interface HighlightRegistry { maplike<[AtomString] DOMString, Highlight>; };
interface FrozenSet { readonly setlike<AbstractRange>; };
interface UnboundSet { setlike<AbstractRange>; readonly attribute long other; };
[InterfaceName=CSS] namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] readonly attribute HighlightRegistry highlights;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['AbstractRange', 'Highlight', 'HighlightRegistry', 'FrozenSet', 'UnboundSet']
        config['constructors'] = {'Highlight': {'receiver': 'Document', 'factory': 'RanvierCollectionLike::createHighlight', 'passReceiver': False}}
        if setlike:
            config['setlikeBindings'] = {'Highlight': {'adapter': 'RanvierCollectionLike'}, 'FrozenSet': {'adapter': 'RanvierCollectionLike'}}
        if maplike:
            config['maplikeBindings'] = {'HighlightRegistry': {'adapter': 'RanvierCollectionLike'}}
        config['namespaceBindings'] = {'DOMCSSNamespace': {'receiver': 'Document', 'members': ['highlights'],
                                                           'feature': 'dom-custom-highlights'}}
        config.update(extra_config or {})
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        return generator

    def test_configured_setlike_and_maplike_bind_ordered_engine_state_through_the_adapter(self):
        generator = self.collection_generator()
        functions = {item.name: item for item in generator.functions}
        for name in ['highlight_size', 'highlight_has', 'highlight_values', 'highlight_add', 'highlight_delete', 'highlight_clear',
                     'highlight_registry_size', 'highlight_registry_has', 'highlight_registry_get', 'highlight_registry_entries',
                     'highlight_registry_set', 'highlight_registry_delete', 'highlight_registry_clear', 'frozen_set_values']:
            self.assertIn(name, functions)
            self.assertEqual('operation', functions[name].kind)
        self.assertNotIn('frozen_set_add', functions)
        self.assertFalse(any(name.startswith('unbound_set_') and name != 'unbound_set_get_other' for name in functions))
        self.assertIn('snapshot copy', functions['highlight_values'].comment)
        self.assertIn('snapshot copy', functions['highlight_registry_entries'].comment)
        self.assertEqual([('RvHighlightRegistry*', 'target'), ('const uint8_t*', 'key'), ('int32_t', 'key_length'),
                          ('RvHighlight**', 'result')], functions['highlight_registry_get'].params)
        self.assertEqual(('RvHighlight*', 'value'), functions['highlight_registry_set'].params[3])
        self.assertTrue(functions['highlight_registry_get'].returns.nullable)
        self.assertEqual('pair', functions['highlight_registry_entries'].returns.subtypes[0].kind)
        glue = generator.glue()
        self.assertIn('#include "RanvierCollectionLike.h"', glue)
        self.assertIn('WebCore::RanvierCollectionLike::remove(*impl, HandleArg<AbstractRange> { a0.get() })', glue)
        self.assertIn('WebCore::RanvierCollectionLike::get(*impl, a0.atom())', glue)
        self.assertIn('RanvierCollectionLike::createHighlight(DomSequenceArgument<Ref<AbstractRange>>', glue)
        self.assertIn('DOMCSSNamespace::highlights(document.get())', glue)
        self.assertIn('decltype(impl->type())', glue)
        self.assertNotIn('{call_with', glue)
        self.assertIn('css_get_highlights', functions)
        self.assertEqual('namespace_operation', functions['css_get_highlights'].kind)

    def test_collection_declarations_without_a_binding_leave_the_output_unchanged(self):
        bound = self.collection_generator(setlike=False, maplike=False)
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(re.sub(r'(readonly )?(setlike|maplike)<[^;]*>;', '', fixture.read_text()))
        config = dict(bound.world.config)
        unbound = domgen.Generator(domgen.World(self.source, config))
        unbound.lock = {}
        unbound.lock_structs = {}
        unbound.run()
        for render in ('header', 'glue', 'api_model', 'interfaces', 'report'):
            self.assertEqual(getattr(unbound, render)(), getattr(bound, render)(), render)

    def test_collection_binding_fails_closed_without_a_declaration_or_adapter(self):
        cases = [({'setlikeBindings': {'HighlightRegistry': {'adapter': 'RanvierCollectionLike'}}}, 'requires one setlike declaration'),
                 ({'setlikeBindings': {'Highlight': {'adapter': 'RanvierMissingAdapter'}}}, 'requires an adapter class'),
                 ({'setlikeBindings': {'Highlight': {}}}, 'requires an adapter class'),
                 ({'maplikeBindings': {'Absent': {'adapter': 'RanvierCollectionLike'}}}, 'requires a scoped interface')]
        for extra, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(SystemExit, reason):
                    self.collection_generator(setlike=False, maplike=False, extra_config=extra)

    def test_namespace_configuration_fails_closed_for_missing_or_unsupported_operations(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=CSS] namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(optional DOMString? conditionText);
};
''')
        binding = {'receiver': 'Document', 'members': ['supports'],
                   'feature': 'dom-css-supports'}
        cases = [
            ('AbsentNamespace', binding, 'configured IDL namespace was not found'),
            ('DOMCSSNamespace', dict(binding, receiver='Event'), 'receiver must be a scoped node'),
            ('DOMCSSNamespace', dict(binding, members=['missing']), 'missing configured namespace operations'),
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

    def test_a_nullable_optional_namespace_string_is_length_minus_one_for_null(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=CSS] namespace DOMCSSNamespace {
    [CallWith=CurrentDocument] boolean supports(optional DOMString? conditionText);
};
''')
        config = dict(self.world.config)
        config['namespaceBindings'] = {'DOMCSSNamespace': {'receiver': 'Document', 'members': ['supports'],
                                                           'feature': 'dom-css-supports'}}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        supports = next(item for item in generator.functions if item.name == 'css_supports')
        self.assertEqual(supports.params[1:3], [('const uint8_t*', 'condition_text'), ('int32_t', 'condition_text_length')])
        self.assertIn('(condition_text_length >= -1 && (condition_text_length <= 0 || condition_text))', generator.glue())

    def test_legacy_null_to_empty_string_arguments_are_marked_in_the_contract(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
partial interface Node { attribute [LegacyNullToEmptyString] DOMString emptyForNull; attribute DOMString plainText; };
''')
        generator = domgen.Generator(domgen.World(self.source, dict(self.world.config)))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        functions = {item['function']: item for item in json.loads(generator.api_model())['functions']}
        self.assertTrue(functions['rv_dom_node_set_empty_for_null']['arguments'][0]['legacyNullToEmptyString'])
        self.assertNotIn('legacyNullToEmptyString', functions['rv_dom_node_set_plain_text']['arguments'][0])

    def test_retired_string_transport_keys_fail_the_run(self):
        for key, value in [('complexStringSpans', []), ('interfaceStringInputs', {}), ('dictionaryStringInputs', {})]:
            with self.subTest(key=key):
                config = dict(self.world.config)
                config[key] = value
                with self.assertRaisesRegex(SystemExit, f'gen/dom.json.{key}'):
                    domgen.World(self.source, config)
        config = dict(self.world.config)
        config['constructors'] = {'Node': {'receiver': 'Document', 'stringInputs': 'utf8-lengths'}}
        with self.assertRaisesRegex(SystemExit, r'gen/dom.json.constructors.Node.stringInputs'):
            domgen.World(self.source, config)

    def test_no_generated_input_is_a_nul_terminated_string(self):
        generator = domgen.Generator(self.world)
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        for function in generator.functions:
            self.assertNotIn('const char*', [ctype for ctype, _ in function.params], function.name)
        self.assertNotIn('const char*', generator.header())

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

    def value_object_generator(self, extra, interfaces, **overrides):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + extra)
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + interfaces
        config.update(overrides)
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        return generator

    def test_buffer_source_arm_is_a_copied_byte_span_decoding_to_the_flattened_array_buffer(self):
        generator = self.value_object_generator('''
typedef (BufferSource or Bytes or USVString) BytesPart;
interface Bytes {
    constructor(optional sequence<BytesPart> parts);
    readonly attribute unsigned long long size;
};
''', ['Bytes'], constructors={'Bytes': {'receiver': 'Document', 'factory': 'Bytes::create'}},
            byteSpanTypes=['BufferSource'], browserWellFormedUnions=['BufferSourceOrBytesOrUSVString'])
        function = next(item for item in generator.functions if item.name == 'bytes_create')
        union = function.arguments[0][1].subtypes[0]
        self.assertEqual(['bytes', 'object', 'string'], [child.kind for child in union.subtypes])
        header = generator.header()
        self.assertIn('typedef struct RvDomByteSpan {', header)
        self.assertIn('    RvDomByteSpan arm0;', header)
        glue = generator.glue()
        self.assertIn('Variant<Ref<JSC::ArrayBufferView>, Ref<JSC::ArrayBuffer>, Ref<Bytes>, String>', glue)
        self.assertIn('WTF::InPlaceIndex<1>, arm0.releaseNonNull()', glue)
        self.assertIn('WTF::InPlaceIndex<2>', glue)
        self.assertIn('WTF::InPlaceIndex<3>', glue)
        self.assertIn('JSC::ArrayBuffer::tryCreate(', glue)
        self.assertIn('"JavaScriptCore/ArrayBuffer.h"', glue)
        self.assertNotIn('encodeRvDomUnionBufferSourceOrBytesOrUSVString', glue)

    def test_byte_span_results_are_unsupported(self):
        generator = self.value_object_generator('''
interface Bytes { readonly attribute BufferSource data; };
''', ['Bytes'], byteSpanTypes=['BufferSource'])
        self.assertNotIn('bytes_get_data', [item.name for item in generator.functions])

    def test_locked_plain_overload_matches_length_delimited_string_parameters(self):
        generator = self.value_object_generator('''
interface Pairs {
    undefined append(USVString name, USVString value);
    undefined append(USVString name, Pairs other, optional USVString label);
};
''', ['Pairs'], browserWellFormedSetters=['Pairs'])
        generator.lock = {'pairs_append': {'params': [['RvPairs*', 'target'], ['const uint8_t*', 'name'],
                                                      ['int32_t', 'name_length'], ['const uint8_t*', 'value'],
                                                      ['int32_t', 'value_length']], 'comment': 'Pairs.append'}}
        self.assertEqual(0, generator.plain_overload('Pairs', 'append', [
            (type('M', (), {'arguments': [type('A', (), {'name': 'name'}), type('A', (), {'name': 'value'})]}), None, None),
            (type('M', (), {'arguments': [type('A', (), {'name': 'name'}), type('A', (), {'name': 'other'}),
                                          type('A', (), {'name': 'label'})]}), None, None)]))

    def test_value_object_constructor_and_static_take_an_absent_optional_string_as_length_minus_one(self):
        generator = self.value_object_generator('''
interface ValueURL {
    constructor(USVString url, optional USVString base);
    static ValueURL? parse(USVString url, optional USVString base);
    readonly attribute USVString href;
};
''', ['ValueURL'],
            constructors={'ValueURL': {'receiver': 'Document', 'factory': 'ValueURL::create', 'passReceiver': False}},
            staticBindings={'ValueURL': {'receiver': 'Document', 'members': ['parse'], 'feature': 'dom-value-url-static'}})
        for name in ('value_url_create', 'value_url_parse'):
            function = next(item for item in generator.functions if item.name == name)
            self.assertEqual([('RvNode*', 'target'), ('const uint8_t*', 'url'), ('int32_t', 'url_length'),
                              ('const uint8_t*', 'base'), ('int32_t', 'base_length'), ('RvValueURL**', 'result')],
                             function.params)
            self.assertIn('base_length -1 means absent', function.comment)
            body = '\n'.join(function.body)
            self.assertIn('(base_length >= -1 && (base_length <= 0 || base))', body)
            self.assertIn('(url_length >= 0 && (url_length <= 0 || url))', body)
            self.assertIn('if (base_length >= 0 && a1.string().isNull()) return RV_ERR_NULL_ARGUMENT;', body)
        self.assertIn('ValueURL', generator.handles)

    def test_record_arguments_use_the_entry_sequence_transport_of_their_cpp_vector(self):
        generator = self.value_object_generator('''
interface Params {
    constructor(optional (sequence<sequence<USVString>> or record<USVString, USVString> or USVString) init = "");
};
''', ['Params'], constructors={'Params': {'receiver': 'Document', 'factory': 'Params::create', 'passReceiver': False}})
        function = next(item for item in generator.functions if item.name == 'params_create')
        union = function.arguments[0][1]
        self.assertEqual(['sequence', 'sequence', 'string'], [child.kind for child in union.subtypes])
        record = union.subtypes[1]
        self.assertEqual('pair', record.subtypes[0].kind)
        self.assertEqual('RvDomSequencePairUSVStringAndUSVString', record.ctype)
        self.assertTrue(all(child.string_spans for child in record.subtypes[0].subtypes))
        glue = generator.glue()
        self.assertIn('Variant<Vector<Vector<String>>, Vector<KeyValuePair<String, String>>, String>', glue)
        self.assertIn('decodeRvDomSequencePairUSVStringAndUSVString', glue)

    def dictionary_result_idl(self):
        return '''
dictionary PartInit { USVString name; };
dictionary PartResult { USVString input; record<USVString, (undefined or USVString)> groups; };
dictionary MatchResult { sequence<(USVString or PartInit)> inputs; PartResult part; };
interface Matcher {
    MatchResult? exec(optional (USVString or PartInit) input = {});
    MatchResult match();
};
'''

    def test_configured_dictionary_results_are_owned_structs_with_one_paired_release(self):
        presence = 'utf8-lengths-presence'
        generator = self.value_object_generator(
            self.dictionary_result_idl(), ['Matcher'],
            resultDictionaries=['MatchResult', 'PartResult', 'PartInit'])
        nullable = next(item for item in generator.functions if item.name == 'matcher_exec')
        required = next(item for item in generator.functions if item.name == 'matcher_match')
        self.assertEqual(('RvDomMatchResult**', 'result'), nullable.params[-1])
        self.assertEqual(('RvDomMatchResult**', 'result'), required.params[-1])
        self.assertIn('storeOptionalDictionary(value, result', '\n'.join(nullable.body))
        self.assertIn('*result is NULL for null', nullable.comment)
        self.assertIn('(*result = encodeDictRvDomMatchResult(value), RV_OK)', '\n'.join(required.body))
        self.assertIn('rv_dom_match_result_release', required.comment)
        self.assertEqual({'MatchResult': 'RvDomMatchResult', 'PartResult': 'RvDomPartResult', 'PartInit': 'RvDomPartInit'},
                         generator.result_dicts)
        glue = generator.glue()
        for line in ['RvDomMatchResult* encodeDictRvDomMatchResult(const MatchResult& value);',
                     'result->size = sizeof(RvDomMatchResult);',
                     'result->part = encodeDictRvDomPartResult(*field);',
                     'releaseDictRvDomPartResult(const_cast<RvDomPartResult*>(value->part));',
                     'encodeRvDomSequenceUSVStringOrPartInit(*field, container);',
                     'clearRvDomSequenceUSVStringOrPartInit(const_cast<RvDomSequenceUSVStringOrPartInit*>(value->inputs));',
                     'result->input = copyOwnedDomStringInput(asString(*field));',
                     'std::free(const_cast<uint8_t*>(value->input.data));',
                     'releaseDictRvDomPartInit(const_cast<RvDomPartInit*>(value->arm1));',
                     'result->arm1 = encodeDictRvDomPartInit(std::get<I>(value));',
                     'if (source->arm1->name.present != 0 && source->arm1->name.present != 1)',
                     'void ranvier_dom_match_result_release(RvDomMatchResult* value)',
                     '    if (isMainThread()) releaseDictRvDomMatchResult(value);']:
            self.assertIn(line, glue)
        self.assertLess(glue.index('void releaseDictRvDomPartResult(RvDomPartResult* value);'),
                        glue.index('void clearRvDomSequenceUSVStringOrPartInit('))
        header = generator.header()
        self.assertIn('RV_EXPORT void rv_dom_match_result_release(RvDomMatchResult* value);', header)
        self.assertIn('RV_EXPORT void rv_dom_part_init_release(RvDomPartInit* value);', header)
        self.assertIn('void rv_dom_match_result_release(RvDomMatchResult* value) { ranvier_dom_match_result_release(value); }',
                      generator.host())
        self.assertIn('extern void rv_dom_match_result_release(nativeint value)', generator.fsharp())
        contract = generator.interfaces()
        self.assertNotIn('MatchResult()', contract)
        self.assertNotIn('PartResult()', contract)
        self.assertIn('PartInit()', contract)
        model = json.loads(generator.api_model())
        self.assertEqual({'struct': 'RvDomMatchResult', 'releaseFunction': 'rv_dom_match_result_release'},
                         model['resultDictionaries']['MatchResult'])

    def test_an_omitted_optional_union_omits_the_later_optional_arguments_in_the_contract(self):
        generator = self.value_object_generator('''
dictionary PartInit { USVString name; };
interface Matcher { boolean test(optional (USVString or PartInit) input = {}, optional USVString baseURL); };
''', ['Matcher'], resultDictionaries=['PartInit'])
        contract = generator.interfaces()
        self.assertIn('abstract member test: unit -> bool', contract)
        self.assertIn('abstract member test: input: string * ?baseURL: string -> bool', contract)
        self.assertNotIn('abstract member test: ?baseURL: string -> bool', contract)
        self.assertIn('this.__ranvier_test (?input = None, ?baseURL = None)', contract)

    def test_sequence_string_spans_name_their_sequences_utf8(self):
        idl = '''
interface Params {
    constructor(optional (sequence<sequence<USVString>> or USVString) init = "");
    sequence<USVString> getAll(USVString name);
};
interface Other { sequence<USVString> names(); };
'''
        generator = self.value_object_generator(idl, ['Params', 'Other'], sequenceStringSpans=['Params'],
            constructors={'Params': {'receiver': 'Document', 'factory': 'Params::create', 'passReceiver': False}})
        get_all = next(item for item in generator.functions if item.name == 'params_get_all')
        names = next(item for item in generator.functions if item.name == 'other_names')
        self.assertEqual('RvDomSequenceUSVStringUtf8', get_all.returns.ctype)
        self.assertTrue(get_all.returns.subtypes[0].string_spans)
        self.assertEqual('RvDomSequenceUSVString', names.returns.ctype)
        self.assertTrue(names.returns.subtypes[0].string_spans)
        create = next(item for item in generator.functions if item.name == 'params_create')
        self.assertEqual('RvDomSequenceSequenceOfUSVStringUtf8', create.arguments[0][1].subtypes[0].ctype)
        header = generator.header()
        self.assertIn('RvDomUtf8StringSpan* items;', header.split('struct RvDomSequenceUSVStringUtf8 {')[1].split('};')[0])

    def test_unconfigured_dictionary_results_stay_left_out(self):
        generator = self.value_object_generator(self.dictionary_result_idl(), ['Matcher'])
        excluded = dict(generator.excluded)
        self.assertIn('Matcher.exec', excluded)
        self.assertIn('Matcher.match', excluded)
        self.assertEqual({}, generator.result_dicts)
        self.assertNotIn('encodeDict', generator.glue())

    def test_result_dictionaries_reject_handle_members(self):
        fixture_idl = '''
interface Item {};
dictionary Holder { Item item; };
interface Source { Holder read(); };
'''
        generator = self.value_object_generator(fixture_idl, ['Item', 'Source'], resultDictionaries=['Holder'])
        self.assertIn('Source.read', dict(generator.excluded))

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

    def test_event_detail_constructor_query_and_getter_expression(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[InterfaceName=ShownEvent] interface InternalShownEvent : Event {
    [CallWith=CurrentGlobalObject] constructor([AtomString] DOMString type, optional ShownEventInit eventInitDict = {});
    readonly attribute DOMString label;
    readonly attribute double when;
};
dictionary EventInit {
    boolean bubbles = false;
    boolean cancelable = false;
    boolean composed = false;
};
dictionary ShownEventInit : EventInit {
    DOMString label = "";
};
interface HiddenEvent : Event {
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['InternalShownEvent']
        config['contract'] = {**config['contract'], 'aliases': {'InternalShownEvent': 'ShownEvent'}}
        config['constructors'] = {'InternalShownEvent': {'receiver': 'Document', 'factory': 'InternalShownEvent::create',
                                                         'passReceiver': False, 'globalObject': True}}
        config['dictionaryCppTypes'] = {'ShownEventInit': 'InternalShownEvent::Init'}
        config['getterExpressions'] = {'InternalShownEvent.when': 'impl->whenSeconds().value()'}
        config['runtimeTypeRoots'] = ['Event']
        config['runtimeTypePublicNames'] = ['Event']
        config['runtimeTypeExtras'] = {'Event': ['HiddenEvent']}
        config['eventInterfaceCasts'] = ['HiddenEvent']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        create = glue[glue.index('int32_t ranvier_dom_internal_shown_event_create('):]
        create = create[:create.index('\n}\n')]
        self.assertIn('auto* global = impl->globalObject(); if (!global) return Exception { ExceptionCode::InvalidStateError', create)
        self.assertIn('InternalShownEvent::create(*global, a0.atom(), std::move(a1))', create)
        self.assertIn('impl->whenSeconds().value()', glue)
        query = glue[glue.index('int32_t ranvier_dom_event_get_interface_name('):]
        query = query[:query.index('\n}\n')]
        # The exposed name, an unscoped extra and the root, most derived first.
        self.assertLess(query.index('"ShownEvent"_s'), query.index('return copyString("Event"_s'))
        self.assertIn('EventInterfaceType::HiddenEvent', query)
        self.assertNotIn('"InternalShownEvent"_s', query)
        self.assertIn('rv_dom_event_get_interface_name(RvEvent* target', generator.header())

    def test_gated_event_interface_members_read_without_a_target(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[EnabledBySetting=GatedEnabled] interface GatedEvent : Event {
    readonly attribute DOMString command;
    [EnabledBySetting=OtherEnabled] readonly attribute DOMString extra;
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['GatedEvent']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        glue = generator.glue()
        command = glue[glue.index('ranvier_dom_gated_event_get_command('):glue.index('ranvier_dom_gated_event_get_extra(')]
        self.assertNotIn('settings.gatedEnabled', command)
        extra = glue[glue.index('ranvier_dom_gated_event_get_extra('):]
        self.assertIn('settings.otherEnabled', extra.split('\n}\n')[0])

    def test_creation_gated_interface_members_skip_the_check_their_factory_makes(self):
        fixture = self.source / 'Source/WebCore/dom/Fixture.idl'
        fixture.write_text(IDL + '''
[EnabledBySetting=PickEnabled] interface Pick {
    readonly attribute unsigned long offset;
    [EnabledBySetting=OtherEnabled] readonly attribute unsigned long extra;
};
partial interface Element {
    [EnabledBySetting=PickEnabled] Pick? pick(double x, double y);
    boolean near(double x);
};
''')
        config = dict(self.world.config)
        config['interfaces'] = list(config['interfaces']) + ['Pick']
        config['creationGatedInterfaces'] = {'Pick': 'Element.pick'}
        config['finiteNumberInputs'] = ['Element.pick']
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        generator.run()
        body = {item.name: chr(10).join(item.body) for item in generator.functions}
        self.assertNotIn('settings.pickEnabled', body['pick_get_offset'])
        self.assertNotIn('pick_get_extra', body)
        self.assertIn('settings.pickEnabled', body['element_pick'])
        self.assertIn('!std::isfinite(x)', body['element_pick'])
        self.assertIn('!std::isfinite(y)', body['element_pick'])
        self.assertNotIn('isfinite', body['element_near'])
        config['creationGatedInterfaces'] = {'Pick': 'Element.near'}
        generator = domgen.Generator(domgen.World(self.source, config))
        generator.lock = {}
        generator.lock_structs = {}
        with self.assertRaises(SystemExit):
            generator.run()

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


    def test_integer_enums_carry_no_require_qualified_access(self):
        # F# enums are always qualified; the attribute on one is warning FS0842.
        lines = (ROOT / 'gen' / 'Ranvier.Dom.fs').read_text(encoding='utf-8').splitlines()
        for index, line in enumerate(lines[:-1]):
            if 'RequireQualifiedAccess' in line and line.rstrip().endswith('='):
                case = lines[index + 1].strip()
                self.assertFalse(case.startswith('|') and '=' in case, line)
        self.assertIn('and NodeFilterResult =', lines)

    def test_fable_reads_wide_integers_as_bigint_and_passes_them_as_numbers(self):
        # Fable represents int64 and uint64 as BigInt; a browser reads and takes them as numbers.
        source = (ROOT / 'gen' / 'Ranvier.Dom.fs').read_text(encoding='utf-8').replace('\r\n', '\n')
        for member in ['size: uint64 with get', 'lastModified: int64 with get']:
            name = member.split(':')[0]
            self.assertIn(f'#if FABLE_COMPILER\n    [<Fable.Core.Emit("BigInt($0.{name})")>]\n#endif\n    abstract member {member}', source)
        self.assertIn('o.slice(a0===void 0?void 0:Number(a0),a1===void 0?void 0:Number(a1),a2))($0,$1,$2,$3)', source)

    def test_fable_adapters_are_not_shadowed_by_inherited_intrinsic_members(self):
        # F# prefers an intrinsic member to an extension, so a Fable adapter extension on an interface is unreachable
        # while an ancestor declares an intrinsic member of the same name.
        fable, keep, stack = [], True, []
        for line in (ROOT / 'gen' / 'Ranvier.Dom.fs').read_text(encoding='utf-8').splitlines():
            directive = line.strip()
            if directive == '#if FABLE_COMPILER':
                stack.append(keep)
            elif directive.startswith('#if '):
                stack.append(keep)
                keep = keep and directive != '#if !FABLE_COMPILER'
            elif directive == '#else':
                keep = stack[-1] and not keep
            elif directive == '#endif':
                keep = stack.pop()
            elif keep:
                fable.append(line)
        bases, intrinsic, extensions, current = {}, {}, {}, None
        for line in fable:
            declared = re.match(r'(?:type|and) (?:\[<[^>]*>\] )*(\w+) =$', line)
            extended = re.match(r'    type (\w+) with$', line)
            if declared:
                current = ('interface', declared.group(1))
                bases.setdefault(current[1], [])
            elif extended:
                current = ('extension', extended.group(1))
            elif current and current[0] == 'interface' and (match := re.match(r'    inherit (\w+)$', line)):
                bases[current[1]].append(match.group(1))
            elif current and current[0] == 'interface' and (match := re.match(r'    abstract member (\w+)', line)):
                intrinsic.setdefault(current[1], set()).add(match.group(1))
            elif current and current[0] == 'extension' and (match := re.match(r'        member this\.(\w+)', line)):
                extensions.setdefault(current[1], set()).add(match.group(1))

        def ancestors(name):
            for base in bases.get(name, []):
                yield base
                yield from ancestors(base)

        shadowed = sorted((owner, member, ancestor) for owner, members in extensions.items() for member in members
                          for ancestor in ancestors(owner) if member in intrinsic.get(ancestor, set()))
        self.assertEqual([], shadowed)
        self.assertIn('namedItem', extensions['HTMLFormControlsCollection'])

if __name__ == '__main__':
    unittest.main()
