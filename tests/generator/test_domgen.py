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
interface EventTarget {
    undefined addEventListener(DOMString type, EventListener? listener, optional boolean capture = false);
    undefined removeEventListener(DOMString type, EventListener? listener, optional boolean capture = false);
    boolean dispatchEvent(Event event);
};
callback EventListener = undefined(Event event);
interface Event { readonly attribute DOMString type; };
interface Node : EventTarget {
    [CustomGetter] readonly attribute unsigned short nodeType;
    boolean checkOptions(optional ProbeOptions options = {});
    readonly attribute Mode mode;
    attribute (boolean or DOMString) state;
    undefined append((Node or DOMString)... nodes);
    sequence<DOMString> labels();
    sequence<Node> descendants();
    undefined take(sequence<Node> nodes);
};
dictionary ElementCreationOptions { DOMString is; };
interface Element : Node { attribute DOMString id; };
interface Document : Node {
    readonly attribute DOMImplementation implementation;
    Element createElementNS(DOMString? namespaceURI, DOMString name, optional (DOMString or ElementCreationOptions) options = {});
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
        config = dict(interfaces=['Node', 'Element', 'Document', 'HTMLDocument', 'DOMImplementation', 'Event', 'DOMStringMap'],
                      skipDirectories=[], exclude=[], atomArguments=[], customGetters=['Node.nodeType'])
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

    def test_transport_model_describes_variadic_union_and_dictionary_fields(self):
        model = json.loads(self.generator.api_model())
        append = next(function for function in model['functions'] if function['function'] == 'rv_dom_node_append')
        argument = append['arguments'][0]
        self.assertTrue(argument['variadic'])
        self.assertEqual(argument['mapping']['kind'], 'sequence')
        self.assertEqual(argument['mapping']['subtypes'][0]['kind'], 'union')
        self.assertEqual([arm['kind'] for arm in argument['mapping']['subtypes'][0]['subtypes']], ['node', 'string'])
        self.assertEqual(model['schemaVersion'], 1)


if __name__ == '__main__':
    unittest.main()
