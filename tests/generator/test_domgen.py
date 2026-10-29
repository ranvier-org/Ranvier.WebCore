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


if __name__ == '__main__':
    unittest.main()
