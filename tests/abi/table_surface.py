import argparse
import ctypes
import os
import pathlib
import sys


def verify(native_directory):
    directory = pathlib.Path(native_directory).resolve()
    name = {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')
    dll_directory = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
    library = ctypes.CDLL(str(directory / name))
    pointer = ctypes.c_void_p
    integer = ctypes.c_int32
    unsigned = ctypes.c_uint32
    signatures = {
        'rv_host_create': (pointer, [integer, integer]),
        'rv_host_destroy': (None, [pointer]),
        'rv_document_body': (pointer, [pointer]),
        'rv_document_create_element': (pointer, [pointer, ctypes.c_char_p]),
        'rv_node_append_child': (integer, [pointer, pointer]),
        'rv_node_release': (None, [pointer]),
        'rv_dom_html_collection_release': (None, [pointer]),
        'rv_dom_html_collection_get_length': (integer, [pointer, ctypes.POINTER(unsigned)]),
        'rv_dom_html_table_element_get_rows': (integer, [pointer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_element_create_t_body': (integer, [pointer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_element_create_caption': (integer, [pointer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_element_insert_row': (integer, [pointer, integer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_element_delete_row': (integer, [pointer, integer]),
        'rv_dom_html_table_section_element_get_rows': (integer, [pointer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_row_element_get_cells': (integer, [pointer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_row_element_insert_cell': (integer, [pointer, integer, ctypes.POINTER(pointer)]),
        'rv_dom_html_table_row_element_delete_cell': (integer, [pointer, integer]),
        'rv_dom_html_table_row_element_get_row_index': (integer, [pointer, ctypes.POINTER(integer)]),
        'rv_dom_html_table_cell_element_set_col_span': (integer, [pointer, unsigned]),
        'rv_dom_html_table_cell_element_get_col_span': (integer, [pointer, ctypes.POINTER(unsigned)]),
        'rv_dom_html_table_col_element_set_span': (integer, [pointer, unsigned]),
        'rv_dom_html_table_col_element_get_span': (integer, [pointer, ctypes.POINTER(unsigned)]),
    }
    for symbol, (result, parameters) in signatures.items():
        function = getattr(library, symbol)
        function.restype = result
        function.argtypes = parameters

    assertions = 0
    nodes = []
    collections = []

    def expect(condition, message):
        nonlocal assertions
        if not condition:
            raise AssertionError(message)
        assertions += 1

    def call(symbol, *args):
        status = getattr(library, symbol)(*args)
        expect(status == 0, f'{symbol}: status {status}')

    def handle(symbol, *args, collection=False):
        result = pointer()
        call(symbol, *args, ctypes.byref(result))
        expect(bool(result.value), f'{symbol}: null handle')
        (collections if collection else nodes).append(result.value)
        return result.value

    def number(symbol, target, kind=unsigned):
        result = kind()
        call(symbol, target, ctypes.byref(result))
        return result.value

    host = library.rv_host_create(320, 200)
    expect(bool(host), 'host creation')
    try:
        body = library.rv_document_body(host)
        expect(bool(body), 'document body')
        nodes.append(body)
        table = library.rv_document_create_element(host, b'table')
        expect(bool(table), 'table creation')
        nodes.append(table)
        call('rv_node_append_child', body, table)
        rows = handle('rv_dom_html_table_element_get_rows', table, collection=True)
        expect(number('rv_dom_html_collection_get_length', rows) == 0, 'initial live row count')
        section = handle('rv_dom_html_table_element_create_t_body', table)
        section_rows = handle('rv_dom_html_table_section_element_get_rows', section, collection=True)
        handle('rv_dom_html_table_element_create_caption', table)
        row = handle('rv_dom_html_table_element_insert_row', table, -1)
        expect(number('rv_dom_html_collection_get_length', rows) == 1, 'live table row count after insert')
        expect(number('rv_dom_html_collection_get_length', section_rows) == 1, 'live section row count after insert')
        expect(number('rv_dom_html_table_row_element_get_row_index', row, integer) == 0, 'row index')
        cells = handle('rv_dom_html_table_row_element_get_cells', row, collection=True)
        cell = handle('rv_dom_html_table_row_element_insert_cell', row, -1)
        expect(number('rv_dom_html_collection_get_length', cells) == 1, 'live cell count after insert')
        call('rv_dom_html_table_cell_element_set_col_span', cell, 3)
        expect(number('rv_dom_html_table_cell_element_get_col_span', cell) == 3, 'reflected cell span')
        col = library.rv_document_create_element(host, b'col')
        expect(bool(col), 'column creation')
        nodes.append(col)
        call('rv_dom_html_table_col_element_set_span', col, 2)
        expect(number('rv_dom_html_table_col_element_get_span', col) == 2, 'reflected column span')
        expect(library.rv_dom_html_table_row_element_delete_cell(row, 99) < 0, 'invalid cell index is rejected')
        call('rv_dom_html_table_row_element_delete_cell', row, 0)
        expect(number('rv_dom_html_collection_get_length', cells) == 0, 'live cell count after delete')
        call('rv_dom_html_table_element_delete_row', table, 0)
        expect(number('rv_dom_html_collection_get_length', rows) == 0, 'live row count after delete')
        expect(number('rv_dom_html_collection_get_length', section_rows) == 0, 'live section count after delete')
    finally:
        for item in reversed(collections):
            library.rv_dom_html_collection_release(item)
        for item in reversed(nodes):
            library.rv_node_release(item)
        library.rv_host_destroy(host)
        if dll_directory is not None:
            dll_directory.close()
    print(f'PASS native table editor surface: {assertions} assertions; retained handles released')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    verify(parser.parse_args().native_directory)
