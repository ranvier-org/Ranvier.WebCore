import argparse
import ctypes
import os
import pathlib
import sys
import threading


def verify(native_directory):
    directory = pathlib.Path(native_directory).resolve()
    filename = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / filename))
    pointer, integer, string, unsigned = ctypes.c_void_p, ctypes.c_int32, ctypes.c_char_p, ctypes.c_uint32
    pointers, numbers = ctypes.POINTER(pointer), ctypes.POINTER(integer)
    retained = []
    count = 0

    def bind(name, result, args):
        function = getattr(library, name)
        function.restype, function.argtypes = result, args
        return function

    def expect(condition, message):
        nonlocal count
        if not condition:
            raise AssertionError(message)
        count += 1

    def call(name, args, *values):
        status = bind(name, integer, args)(*values)
        expect(status == 0, name + ': status ' + str(status))

    def text(name, args, *values):
        buffer, length = ctypes.create_string_buffer(8192), integer()
        call(name, args + [pointer, integer, numbers], *values, buffer, len(buffer), ctypes.byref(length))
        return buffer.value.decode('utf-8')

    def handle(name, args, *values, release):
        result = pointer()
        call(name, args + [pointers], *values, ctypes.byref(result))
        expect(bool(result.value), name + ': null result')
        retained.append((release, result.value))
        return result.value

    bind('rv_dom_html_style_element_get_sheet', integer, [pointer, pointers])
    has = bind('rv_abi_has', integer, [string])
    for root in ['CSSRule', 'StyleSheet', 'CSSStyleDeclaration']:
        expect(has(('dom-type-query:' + root).encode()) == 1, root + ' runtime type capability')
    type_query = bind('rv_dom_css_rule_get_interface_name', integer, [pointer, pointer, integer, numbers])
    invalid_length = integer()
    expect(type_query(None, None, 0, ctypes.byref(invalid_length)) == -1, 'runtime type query null target')
    host = bind('rv_host_create', pointer, [integer, integer])(320, 240)
    expect(bool(host), 'host creation')
    try:
        body = bind('rv_document_body', pointer, [pointer])(host)
        expect(bool(body), 'document body')
        retained.append(('rv_node_release', body))
        document = handle('rv_dom_node_get_owner_document', [pointer], body, release='rv_node_release')
        style = bind('rv_document_create_element', pointer, [pointer, string])(host, b'style')
        expect(bool(style), 'style node')
        retained.append(('rv_node_release', style))
        call('rv_dom_node_set_text_content', [pointer, string], style, b'.probe { color: red; }')
        call('rv_node_append_child', [pointer, pointer], body, style)
        sheets = handle('rv_dom_document_get_style_sheets', [pointer], document, release='rv_dom_style_sheet_list_release')
        sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], style, release='rv_dom_style_sheet_release')
        expect(text('rv_dom_style_sheet_get_interface_name', [pointer], sheet) == 'CSSStyleSheet', 'concrete stylesheet type')
        expect(text('rv_dom_style_sheet_get_type', [pointer], sheet) == 'text/css', 'stylesheet MIME type')
        rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], sheet, release='rv_dom_css_rule_list_release')

        def length_is(name, target, expected):
            length = unsigned()
            call(name, [pointer, ctypes.POINTER(unsigned)], target, ctypes.byref(length))
            expect(length.value == expected, name + ': length ' + str(expected))

        length_is('rv_dom_style_sheet_list_get_length', sheets, 1)
        length_is('rv_dom_css_rule_list_get_length', rules, 1)
        rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, 0, release='rv_dom_css_rule_release')
        expect(text('rv_dom_css_style_rule_get_selector_text', [pointer], rule) == '.probe', 'selector text')
        declaration = handle('rv_dom_css_style_rule_get_style', [pointer], rule, release='rv_dom_css_style_declaration_release')
        expect(text('rv_dom_css_style_declaration_get_interface_name', [pointer], declaration) == 'CSSStyleProperties', 'concrete style declaration type')
        expect(text('rv_dom_css_rule_get_interface_name', [pointer], rule) == 'CSSStyleRule', 'concrete style rule type')
        expect(type_query(rule, None, 0, None) == -1, 'runtime type query null length')
        other_thread_status = []

        def query_other_thread():
            length = integer()
            other_thread_status.append(type_query(rule, None, 0, ctypes.byref(length)))

        thread = threading.Thread(target=query_other_thread)
        thread.start()
        thread.join()
        expect(other_thread_status == [-2], 'runtime type query owning thread')
        expect(text('rv_dom_css_style_declaration_get_property_value', [pointer, string], declaration, b'color') == 'red', 'rule declaration')
        call('rv_dom_css_style_rule_set_selector_text', [pointer, string], rule, b'.changed')
        expect('.changed' in text('rv_dom_css_rule_get_css_text', [pointer], rule), 'selector reflected in cssText')
        inserted = unsigned()
        call('rv_dom_css_style_sheet_insert_rule', [pointer, string, unsigned, ctypes.POINTER(unsigned)], sheet,
             b'@media screen { .inside { opacity: 0.5; } }', 1, ctypes.byref(inserted))
        expect(inserted.value == 1, 'insertRule returns index')
        length_is('rv_dom_css_rule_list_get_length', rules, 2)
        media_rule = handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, 1, release='rv_dom_css_rule_release')
        expect(text('rv_dom_css_condition_rule_get_condition_text', [pointer], media_rule) == 'screen', 'media condition')
        media = handle('rv_dom_css_media_rule_get_media', [pointer], media_rule, release='rv_dom_media_list_release')
        call('rv_dom_media_list_append_medium', [pointer, string], media, b'print')
        expect(text('rv_dom_media_list_get_media_text', [pointer], media) == 'screen, print', 'mutable MediaList')
        nested = handle('rv_dom_css_grouping_rule_get_css_rules', [pointer], media_rule, release='rv_dom_css_rule_list_release')
        length_is('rv_dom_css_rule_list_get_length', nested, 1)
        call('rv_dom_css_style_sheet_delete_rule', [pointer, unsigned], sheet, 1)
        length_is('rv_dom_css_rule_list_get_length', rules, 1)
        invalid = bind('rv_dom_css_style_sheet_insert_rule', integer, [pointer, string, unsigned, ctypes.POINTER(unsigned)])
        expect(invalid(sheet, b'.bad {}', 99, ctypes.byref(inserted)) != 0, 'invalid rule index reports error')
        length_is('rv_dom_css_rule_list_get_length', rules, 1)

        def append_rule(css):
            length = unsigned()
            call('rv_dom_css_rule_list_get_length', [pointer, ctypes.POINTER(unsigned)], rules, ctypes.byref(length))
            call('rv_dom_css_style_sheet_insert_rule', [pointer, string, unsigned, ctypes.POINTER(unsigned)],
                 sheet, css.encode(), length.value, ctypes.byref(inserted))
            return handle('rv_dom_css_rule_list_item', [pointer, unsigned], rules, inserted.value, release='rv_dom_css_rule_release')

        for css, getter, expected in [
            ('@supports (display: grid) { .supported { color: green; } }', 'css_condition_rule_get_condition_text', '(display: grid)'),
            ('@container card (width > 10px) { .contained { color: green; } }', 'css_container_rule_get_container_name', 'card'),
            ('@layer theme { .layered { color: green; } }', 'css_layer_block_rule_get_name', 'theme'),
            ('@scope (.root) to (.boundary) { .scoped { color: green; } }', 'css_scope_rule_get_start', '.root'),
            ('@font-feature-values Fixture { @styleset { fancy: 1; } }', 'css_font_feature_values_rule_get_font_family', 'Fixture'),
            ('@font-palette-values --theme { font-family: Fixture; base-palette: 1; override-colors: 0 red; }', 'css_font_palette_values_rule_get_name', '--theme'),
            ('@counter-style fixture { system: cyclic; symbols: "*"; suffix: " "; }', 'css_counter_style_rule_get_name', 'fixture'),
            ('@view-transition { navigation: auto; types: fixture; }', 'css_view_transition_rule_get_navigation', 'auto'),
        ]:
            current = append_rule(css)
            expect(text('rv_dom_' + getter, [pointer], current) == expected, getter + ' parsed metadata')
            concrete = {'@supports': 'CSSSupportsRule', '@container': 'CSSContainerRule', '@layer': 'CSSLayerBlockRule',
                        '@scope': 'CSSScopeRule', '@font-feature-values': 'CSSFontFeatureValuesRule',
                        '@font-palette-values': 'CSSFontPaletteValuesRule', '@counter-style': 'CSSCounterStyleRule',
                        '@view-transition': 'CSSViewTransitionRule'}[css.split()[0]]
            expect(text('rv_dom_css_rule_get_interface_name', [pointer], current) == concrete, concrete + ' runtime type')

        keyframes = append_rule('@keyframes pulse { from { opacity: 0; } to { opacity: 1; } }')
        expect(text('rv_dom_css_keyframes_rule_get_name', [pointer], keyframes) == 'pulse', 'keyframes name')
        call('rv_dom_css_keyframes_rule_set_name', [pointer, string], keyframes, b'changed-pulse')
        expect(text('rv_dom_css_keyframes_rule_get_name', [pointer], keyframes) == 'changed-pulse', 'keyframes rename')
        call('rv_dom_css_keyframes_rule_append_rule', [pointer, string], keyframes, b'50% { opacity: 0.5; }')
        middle = handle('rv_dom_css_keyframes_rule_find_rule', [pointer, string], keyframes, b'50%', release='rv_dom_css_rule_release')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', [pointer], middle) == '50%', 'keyframe lookup')
        call('rv_dom_css_keyframe_rule_set_key_text', [pointer, string], middle, b'60%')
        expect(text('rv_dom_css_keyframe_rule_get_key_text', [pointer], middle) == '60%', 'keyframe offset edit')
        call('rv_dom_css_keyframes_rule_delete_rule', [pointer, string], keyframes, b'60%')
        length_is('rv_dom_css_keyframes_rule_get_length', keyframes, 2)

        font = append_rule('@font-face { font-family: Fixture; src: local("Fixture"); font-display: swap; }')
        descriptors = handle('rv_dom_css_font_face_rule_get_style', [pointer], font, release='rv_dom_css_style_declaration_release')
        expect(text('rv_dom_css_style_declaration_get_interface_name', [pointer], descriptors) == 'CSSFontFaceDescriptors', 'concrete font descriptors type')
        expect(text('rv_dom_css_font_face_descriptors_get_font_family', [pointer], descriptors) == 'Fixture', 'font family descriptor')
        call('rv_dom_css_font_face_descriptors_set_font_family_css', [pointer, string], descriptors, b'ChangedFixture')
        expect(text('rv_dom_css_font_face_descriptors_get_font_family', [pointer], descriptors) == 'ChangedFixture', 'dashed descriptor alias')
        call('rv_dom_css_font_face_descriptors_set_ascent_override_css', [pointer, string], descriptors, b'90%')
        expect(text('rv_dom_css_font_face_descriptors_get_ascent_override', [pointer], descriptors) == '90%', 'font metric descriptor')

        position = append_rule('@position-try --fallback { top: 10px; margin-left: 4px; }')
        expect(text('rv_dom_css_position_try_rule_get_name', [pointer], position) == '--fallback', 'position fallback name')
        fallback = handle('rv_dom_css_position_try_rule_get_style', [pointer], position, release='rv_dom_css_style_declaration_release')
        expect(text('rv_dom_css_style_declaration_get_interface_name', [pointer], fallback) == 'CSSPositionTryDescriptors', 'concrete position descriptors type')
        expect(text('rv_dom_css_position_try_descriptors_get_top', [pointer], fallback) == '10px', 'position descriptor')
        call('rv_dom_css_position_try_descriptors_set_margin_left_css', [pointer, string], fallback, b'8px')
        expect(text('rv_dom_css_position_try_descriptors_get_margin_left', [pointer], fallback) == '8px', 'dashed position alias')

        starting = append_rule('@starting-style { .probe { opacity: 0; } }')
        expect(text('rv_dom_css_rule_get_interface_name', [pointer], starting) == 'CSSStartingStyleRule', 'zero-own-member rule type')
        starting_rules = handle('rv_dom_css_grouping_rule_get_css_rules', [pointer], starting, release='rv_dom_css_rule_list_release')
        length_is('rv_dom_css_rule_list_get_length', starting_rules, 1)
        scoped = append_rule('.nest { color: red; & .child { color: blue; } opacity: 0.5; }')
        scoped_rules = handle('rv_dom_css_style_rule_get_css_rules', [pointer], scoped, release='rv_dom_css_rule_list_release')
        length_is('rv_dom_css_rule_list_get_length', scoped_rules, 2)
        nested_declarations = handle('rv_dom_css_rule_list_item', [pointer, unsigned], scoped_rules, 1, release='rv_dom_css_rule_release')
        nested_style = handle('rv_dom_css_nested_declarations_get_style', [pointer], nested_declarations, release='rv_dom_css_style_declaration_release')
        expect(text('rv_dom_css_style_declaration_get_property_value', [pointer, string], nested_style, b'opacity') == '0.5', 'nested declaration')

        class StringSequence(ctypes.Structure):
            _fields_ = [('present', integer), ('count', integer), ('items', ctypes.POINTER(string))]

        layer_statement = append_rule('@layer first, second;')
        names = StringSequence()
        call('rv_dom_css_layer_statement_rule_get_name_list', [pointer, ctypes.POINTER(StringSequence)],
             layer_statement, ctypes.byref(names))
        try:
            expect(names.present == 1 and [names.items[index].decode() for index in range(names.count)] == ['first', 'second'],
                   'layer statement names')
        finally:
            bind('rv_dom_sequence_dom_string_release', None, [ctypes.POINTER(StringSequence)])(ctypes.byref(names))

        before_rules = bind('rv_document_create_element', pointer, [pointer, string])(host, b'style')
        expect(bool(before_rules), 'import and namespace sheet')
        retained.append(('rv_node_release', before_rules))
        call('rv_dom_node_set_text_content', [pointer, string], before_rules,
             b'@import url("data:text/css,.imported%7Bcolor:red%7D") layer(imported); @namespace svg "http://www.w3.org/2000/svg";')
        call('rv_node_append_child', [pointer, pointer], body, before_rules)
        import_sheet = handle('rv_dom_html_style_element_get_sheet', [pointer], before_rules, release='rv_dom_style_sheet_release')
        import_rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], import_sheet, release='rv_dom_css_rule_list_release')
        length_is('rv_dom_css_rule_list_get_length', import_rules, 2)
        imported = handle('rv_dom_css_rule_list_item', [pointer, unsigned], import_rules, 0, release='rv_dom_css_rule_release')
        expect(text('rv_dom_css_import_rule_get_layer_name', [pointer], imported) == 'imported', 'import layer metadata')
        expect(text('rv_dom_css_import_rule_get_href', [pointer], imported).startswith('data:text/css,'), 'import href metadata')
        namespace = handle('rv_dom_css_rule_list_item', [pointer, unsigned], import_rules, 1, release='rv_dom_css_rule_release')
        expect(text('rv_dom_css_namespace_rule_get_prefix', [pointer], namespace) == 'svg', 'namespace prefix')
        expect(text('rv_dom_css_namespace_rule_get_namespace_uri', [pointer], namespace) == 'http://www.w3.org/2000/svg', 'namespace URI')
        call('rv_node_remove_child', [pointer, pointer], body, before_rules)

        call('rv_node_remove_child', [pointer, pointer], body, style)
        length_is('rv_dom_style_sheet_list_get_length', sheets, 0)

        svg = handle('rv_dom_document_create_element_ns', [pointer, string, string, pointer],
                     document, b'http://www.w3.org/2000/svg', b'svg', None, release='rv_node_release')
        svg_style = handle('rv_dom_document_create_element_ns', [pointer, string, string, pointer],
                           document, b'http://www.w3.org/2000/svg', b'style', None, release='rv_node_release')
        call('rv_dom_node_set_text_content', [pointer, string], svg_style, b'.svg-probe { opacity: 0.4; }')
        call('rv_dom_svg_style_element_set_type', [pointer, string], svg_style, b'text/css')
        call('rv_dom_svg_style_element_set_title', [pointer, string], svg_style, b'SVG fixture')
        call('rv_dom_svg_style_element_set_media', [pointer, string], svg_style, b'screen')
        expect(text('rv_dom_svg_style_element_get_type', [pointer], svg_style) == 'text/css', 'SVG style type')
        expect(text('rv_dom_svg_style_element_get_title', [pointer], svg_style) == 'SVG fixture', 'SVG style title')
        expect(text('rv_dom_svg_style_element_get_media', [pointer], svg_style) == 'screen', 'SVG style media')
        call('rv_node_append_child', [pointer, pointer], svg, svg_style)
        call('rv_node_append_child', [pointer, pointer], body, svg)
        svg_sheet = handle('rv_dom_svg_style_element_get_sheet', [pointer], svg_style, release='rv_dom_style_sheet_release')
        expect(text('rv_dom_style_sheet_get_interface_name', [pointer], svg_sheet) == 'CSSStyleSheet', 'SVG concrete sheet')
        svg_rules = handle('rv_dom_css_style_sheet_get_css_rules', [pointer], svg_sheet, release='rv_dom_css_rule_list_release')
        length_is('rv_dom_css_rule_list_get_length', svg_rules, 1)
        owner_node = handle('rv_dom_style_sheet_get_owner_node', [pointer], svg_sheet, release='rv_node_release')
        expect(owner_node == svg_style, 'SVG stylesheet owner node')
        disabled = integer()
        call('rv_dom_svg_style_element_set_disabled', [pointer, integer], svg_style, 1)
        call('rv_dom_svg_style_element_get_disabled', [pointer, numbers], svg_style, ctypes.byref(disabled))
        expect(disabled.value == 1, 'SVG style disabled')
        call('rv_dom_style_sheet_get_disabled', [pointer, numbers], svg_sheet, ctypes.byref(disabled))
        expect(disabled.value == 1, 'SVG style disabled sheet synchronization')
        call('rv_dom_svg_style_element_set_disabled', [pointer, integer], svg_style, 0)
        expect(bind('rv_dom_svg_style_element_get_disabled', integer, [pointer, numbers])(style, ctypes.byref(disabled)) == -11,
               'SVG style wrong namespace rejected')
        call('rv_node_remove_child', [pointer, pointer], body, svg)
        length_is('rv_dom_style_sheet_list_get_length', sheets, 0)
    finally:
        for release, value in reversed(retained):
            bind(release, None, [pointer])(value)
        bind('rv_host_destroy', None, [pointer])(host)
        if search:
            search.close()
    print(f'PASS CSSOM surface: {count} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
