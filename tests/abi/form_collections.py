"""Replays tests/fixtures/form-collections-cases.json through the generated form collection, FormData, SubmitEvent and
FormDataEvent functions and compares every step with the Chromium oracle tests/fixtures/form-collections-oracle.json.
It also checks the null, thread and interface errors, the File entry tag, and requestSubmit and submit leaving the
host's document in place."""

import argparse
import ctypes
import json
import os
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utf8_inputs import Utf8, bind as bind_utf8

FIXTURES = Path(__file__).resolve().parents[1] / 'fixtures'
P, I, U = ctypes.c_void_p, ctypes.c_int32, ctypes.c_uint32
CALLBACK = ctypes.CFUNCTYPE(I, P, P)
OK, NULL_ARGUMENT, WRONG_THREAD, DOM_EXCEPTION, WRONG_INTERFACE = 0, -1, -2, -3, -11
ABI = 54
FILE_ARM, STRING_ARM = 1, 2


class Span(ctypes.Structure):
    _fields_ = [('data', P), ('length', I)]


class EntryValue(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', P), ('arm1', Span)]


class EntryValues(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(EntryValue))]


class Entry(ctypes.Structure):
    _fields_ = [('present', I), ('key', Span), ('value', EntryValue)]


class Entries(ctypes.Structure):
    _fields_ = [('present', I), ('count', I), ('items', ctypes.POINTER(Entry))]


class Named(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', P), ('arm1', P)]


class OptionOrGroup(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', P), ('arm1', P)]


class ElementOrIndex(ctypes.Structure):
    _fields_ = [('present', I), ('tag', I), ('arm0', P), ('arm1', I)]


class SubmitEventInit(ctypes.Structure):
    _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('submitter', P)]


class FormDataEventInit(ctypes.Structure):
    _fields_ = [('size', U), ('bubbles', I), ('cancelable', I), ('composed', I), ('form_data', P)]


def utf8(value):
    data = value.encode('utf-8')
    return ctypes.create_string_buffer(data, len(data) + 1), len(data)


def span_text(span):
    return ctypes.string_at(span.data, span.length).decode('utf-8') if span.length > 0 else ''


class Native:
    def __init__(self, directory):
        directory = Path(directory).resolve()
        self.search = os.add_dll_directory(str(directory)) if sys.platform == 'win32' else None
        self.library = ctypes.CDLL(str(directory / {'win32': 'RanvierWebCoreHost.dll', 'darwin': 'libRanvierWebCoreHost.dylib'}.get(sys.platform, 'libRanvierWebCoreHost.so')))
        self.assertions = 0

    def bind(self, name, result, arguments):
        return bind_utf8(self.library, name, result, arguments)

    def expect(self, condition, label):
        self.assertions += 1
        if not condition:
            raise AssertionError(label)

    def call(self, name, arguments, *values):
        return self.bind(name, I, arguments)(*values)

    def ok(self, name, arguments, *values):
        status = self.call(name, arguments, *values)
        self.expect(status == OK, f'{name}: status {status}')

    def text(self, name, arguments, *values):
        buffer, length = ctypes.create_string_buffer(4096), I()
        self.ok(name, arguments + [P, I, ctypes.POINTER(I)], *values, buffer, len(buffer), ctypes.byref(length))
        return None if length.value < 0 else buffer.raw[:length.value].decode('utf-8')

    def exception(self):
        return self.text('rv_last_exception', [I], 0)

    def handle(self, name, arguments, *values, nullable=True):
        result = P()
        self.ok(name, arguments + [ctypes.POINTER(P)], *values, ctypes.byref(result))
        if not nullable:
            self.expect(bool(result.value), name + ': nonnull')
        return result.value

    def integer(self, name, target, kind=I):
        result = kind()
        self.ok(name, [P, ctypes.POINTER(kind)], target, ctypes.byref(result))
        return result.value


class Case:
    def __init__(self, native, markup):
        self.n = native
        self.host = native.bind('rv_host_create', P, [I, I])(320, 200)
        native.expect(bool(self.host), 'host')
        native.expect(native.call('rv_host_load_html', [P, ctypes.c_char_p], self.host, markup.encode()) == OK, 'load')
        self.document = native.bind('rv_host_document', P, [P])(self.host)
        self.created, self.vars, self.events, self.listeners, self.callbacks, self.owned = {}, {}, [], [], [], []

    def close(self):
        n = self.n
        for listener in self.listeners:
            n.call('rv_listener_remove', [P], listener)
        for value in self.vars.values():
            n.bind('rv_dom_dom_form_data_release', None, [P])(value)
        for node in self.owned + list(self.created.values()) + [self.document]:
            n.bind('rv_node_release', None, [P])(node)
        n.bind('rv_host_destroy', None, [P])(self.host)

    def node(self, identifier):
        if identifier is None:
            return None
        if identifier in self.created:
            return self.created[identifier]
        node = self.n.bind('rv_document_get_element_by_id', P, [P, ctypes.c_char_p])(self.host, identifier.encode())
        self.n.expect(bool(node), 'node ' + identifier)
        self.owned.append(node)
        return node

    def label(self, node):
        if not node:
            return None
        identifier = self.n.text('rv_dom_element_get_id', [P], node)
        return identifier or self.n.text('rv_dom_node_get_node_name', [P], node)

    def labels(self, collection, prefix):
        n = self.n
        count = n.integer(f'rv_dom_{prefix}_get_length', collection, U)
        result = []
        for index in range(count):
            item = n.handle(f'rv_dom_{prefix}_item', [P, U], collection, index)
            result.append(self.label(item))
            n.bind('rv_node_release', None, [P])(item)
        return result

    def collection(self, getter, target):
        return self.n.handle(getter, [P], self.node(target), nullable=False)

    def release_collection(self, collection):
        self.n.bind('rv_dom_html_collection_release', None, [P])(collection)

    def with_elements(self, form, action):
        collection = self.collection('rv_dom_html_form_element_get_elements', form)
        try:
            return action(collection)
        finally:
            self.release_collection(collection)

    def with_options(self, select, action):
        collection = self.collection('rv_dom_html_select_element_get_options', select)
        try:
            return action(collection)
        finally:
            self.release_collection(collection)

    def entry_value(self, value):
        self.n.expect(value.tag in (FILE_ARM, STRING_ARM), 'entry tag')
        if value.tag == FILE_ARM:
            self.n.expect(value.arm0 is not None, 'File arm carries a handle')
            return {'file': True}
        return span_text(value.arm1)

    def entries(self, data):
        n = self.n
        result = Entries()
        n.ok('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, self.document, ctypes.byref(result))
        try:
            return [[span_text(result.items[i].key), self.entry_value(result.items[i].value)] for i in range(result.count)]
        finally:
            n.bind('rv_dom_sequence_pair_usv_string_and_union_file_or_usv_string_release', None, [ctypes.POINTER(Entries)])(ctypes.byref(result))

    def describe(self, event):
        n = self.n
        described = {'type': n.text('rv_dom_event_get_type', [P], event),
                     'trusted': n.integer('rv_dom_event_get_is_trusted', event) == 1,
                     'bubbles': n.integer('rv_dom_event_get_bubbles', event) == 1,
                     'cancelable': n.integer('rv_dom_event_get_cancelable', event) == 1}
        submitter = P()
        status = n.call('rv_dom_submit_event_get_submitter', [P, ctypes.POINTER(P)], event, ctypes.byref(submitter))
        if status == OK:
            described['submitter'] = self.label(submitter.value)
            if submitter.value:
                n.bind('rv_node_release', None, [P])(submitter.value)
        else:
            n.expect(status == WRONG_INTERFACE, 'submitter on another event')
        data = P()
        status = n.call('rv_dom_form_data_event_get_form_data', [P, ctypes.POINTER(P)], event, ctypes.byref(data))
        if status == OK:
            described['entries'] = self.entries(data.value)
            n.bind('rv_dom_dom_form_data_release', None, [P])(data.value)
        else:
            n.expect(status == WRONG_INTERFACE, 'formData on another event')
        return described

    def attempt(self, action):
        self.events = []
        status, value = action()
        if status == DOM_EXCEPTION:
            return {'status': self.n.exception(), 'events': self.events}
        self.n.expect(status == OK, f'status {status}')
        return {'status': 'ok', 'value': value, 'events': self.events}

    def listen(self, step):
        n = self.n

        def on_event(context, event):
            try:
                if step['action'] == 'preventDefault':
                    n.ok('rv_dom_event_prevent_default', [P], event)
                if step['action'] == 'edit':
                    data = n.handle('rv_dom_form_data_event_get_form_data', [P], event, nullable=False)
                    for edit in step['edits']:
                        name, name_length = utf8(edit['name'])
                        if edit['op'] == 'delete':
                            n.ok('rv_dom_dom_form_data_delete', [P, P, I], data, name, name_length)
                        else:
                            value, value_length = utf8(edit['value'])
                            n.ok(f"rv_dom_dom_form_data_{edit['op']}", [P, P, I, P, I], data, name, name_length, value, value_length)
                    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
                self.events.append(self.describe(event))
                return 0
            except Exception as error:
                self.events.append({'listenerError': str(error)})
                return 1

        callback = CALLBACK(on_event)
        self.callbacks.append(callback)
        listener = n.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])(self.node(step['form']), step['type'].encode(), 0, callback, None)
        n.expect(bool(listener), 'listener')
        self.listeners.append(listener)

    def form_data_get(self, data, name):
        n = self.n
        text, length = utf8(name)
        result = EntryValue()
        n.ok('rv_dom_dom_form_data_get', [P, P, I, ctypes.POINTER(EntryValue)], data, text, length, ctypes.byref(result))
        try:
            return self.entry_value(result) if result.present else None
        finally:
            n.bind('rv_dom_union_file_or_usv_string_nullable_release', None, [ctypes.POINTER(EntryValue)])(ctypes.byref(result))

    def form_data_get_all(self, data, name):
        n = self.n
        text, length = utf8(name)
        result = EntryValues()
        n.ok('rv_dom_dom_form_data_get_all', [P, P, I, ctypes.POINTER(EntryValues)], data, text, length, ctypes.byref(result))
        try:
            return [self.entry_value(result.items[i]) for i in range(result.count)]
        finally:
            n.bind('rv_dom_sequence_file_or_usv_string_release', None, [ctypes.POINTER(EntryValues)])(ctypes.byref(result))

    def named(self, form, name):
        n = self.n

        def lookup(collection):
            result = Named()
            n.ok('rv_dom_html_form_controls_collection_named_item', [P, Utf8, ctypes.POINTER(Named)], collection, name.encode(), ctypes.byref(result))
            try:
                if not result.present:
                    return None
                if result.tag == 2:
                    return {'element': self.label(result.arm1)}
                n.expect(result.tag == 1, 'RadioNodeList tag')
                count = n.integer('rv_dom_node_list_get_length', result.arm0, U)
                items = []
                for index in range(count):
                    item = n.handle('rv_dom_node_list_item', [P, U], result.arm0, index)
                    items.append(self.label(item))
                    n.bind('rv_node_release', None, [P])(item)
                return {'radioNodeList': items}
            finally:
                n.bind('rv_dom_union_radio_node_list_or_element_nullable_release', None, [ctypes.POINTER(Named)])(ctypes.byref(result))
        return self.with_elements(form, lookup)

    def run(self, step):
        n, op = self.n, step['op']
        if op == 'elementsList':
            return self.with_elements(step['form'], lambda c: self.labels(c, 'html_collection'))
        if op == 'elementsLength':
            return self.with_elements(step['form'], lambda c: n.integer('rv_dom_html_collection_get_length', c, U))
        if op == 'elementsItem':
            def item(collection):
                node = n.handle('rv_dom_html_form_controls_collection_item', [P, U], collection, step['index'])
                label = self.label(node)
                if node:
                    n.bind('rv_node_release', None, [P])(node)
                return label
            return self.with_elements(step['form'], item)
        if op == 'elementsNamed':
            return self.named(step['form'], step['name'])
        if op == 'remove':
            n.ok('rv_dom_element_remove', [P], self.node(step['id']))
            return None
        if op == 'append':
            appended = n.handle('rv_dom_node_append_child', [P, P], self.node(step['parent']), self.node(step['id']))
            n.bind('rv_node_release', None, [P])(appended)
            return None
        if op == 'setAttribute':
            n.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], self.node(step['id']), step['name'].encode(), step['value'].encode())
            return None
        if op == 'removeAttribute':
            n.ok('rv_dom_element_remove_attribute', [P, Utf8], self.node(step['id']), step['name'].encode())
            return None
        if op == 'create':
            element = n.handle('rv_dom_document_create_element', [P, Utf8, P], self.document, step['tag'].encode(), None, nullable=False)
            n.ok('rv_dom_element_set_attribute', [P, Utf8, Utf8], element, b'id', step['id'].encode())
            n.ok('rv_dom_node_set_text_content', [P, Utf8], element, step['text'].encode())
            self.created[step['id']] = element
            return None
        if op == 'optionsList':
            return self.with_options(step['select'], lambda c: self.labels(c, 'html_collection'))
        if op == 'optionsLength':
            return self.with_options(step['select'], lambda c: n.integer('rv_dom_html_options_collection_get_length', c, U))
        if op == 'optionsItem':
            def item(collection):
                node = n.handle('rv_dom_html_options_collection_item', [P, U], collection, step['index'])
                label = self.label(node)
                if node:
                    n.bind('rv_node_release', None, [P])(node)
                return label
            return self.with_options(step['select'], item)
        if op == 'optionsNamed':
            def named(collection):
                node = n.handle('rv_dom_html_options_collection_named_item', [P, Utf8], collection, step['name'].encode())
                label = self.label(node)
                if node:
                    n.bind('rv_node_release', None, [P])(node)
                return label
            return self.with_options(step['select'], named)
        if op == 'selectedIndex':
            return self.with_options(step['select'], lambda c: n.integer('rv_dom_html_options_collection_get_selected_index', c))
        if op == 'setSelectedIndex':
            return self.with_options(step['select'], lambda c: n.ok('rv_dom_html_options_collection_set_selected_index', [P, I], c, step['value']))
        if op == 'optionsAdd':
            element = OptionOrGroup(1, 2 if step['element'].startswith('ng') else 1, None, None)
            if element.tag == 1:
                element.arm0 = self.node(step['element'])
            else:
                element.arm1 = self.node(step['element'])
            before = None
            if step['before'] is not None:
                before = ElementOrIndex(1, 2, None, step['before']['index']) if 'index' in step['before'] else ElementOrIndex(1, 1, self.node(step['before']['element']), 0)
            return self.with_options(step['select'], lambda c: self.attempt(lambda: (n.call(
                'rv_dom_html_options_collection_add', [P, ctypes.POINTER(OptionOrGroup), ctypes.POINTER(ElementOrIndex)],
                c, ctypes.byref(element), ctypes.byref(before) if before else None), None)))
        if op == 'optionsRemove':
            return self.with_options(step['select'], lambda c: n.ok('rv_dom_html_options_collection_remove', [P, I], c, step['index']))
        if op == 'optionsSetLength':
            return self.with_options(step['select'], lambda c: n.ok('rv_dom_html_options_collection_set_length', [P, U], c, step['length']))
        if op == 'optionsSetItem':
            return self.with_options(step['select'], lambda c: self.attempt(lambda: (n.call(
                'rv_dom_html_options_collection_set_item', [P, U, P], c, step['index'], self.node(step['option'])), None)))
        if op == 'listen':
            self.listen(step)
            return None
        if op == 'requestSubmit':
            return self.attempt(lambda: (n.call('rv_dom_html_form_element_request_submit', [P, P], self.node(step['form']), self.node(step['submitter'])), None))
        if op == 'submit':
            return self.attempt(lambda: (n.call('rv_dom_html_form_element_submit', [P], self.node(step['form'])), None))
        if op == 'formDataNew':
            def create():
                result = P()
                status = n.call('rv_dom_dom_form_data_create', [P, P, P, ctypes.POINTER(P)], self.document,
                                self.node(step['form']), self.node(step['submitter']), ctypes.byref(result))
                if status == OK:
                    if step['var'] in self.vars:
                        n.bind('rv_dom_dom_form_data_release', None, [P])(self.vars[step['var']])
                    self.vars[step['var']] = result.value
                return status, None
            return self.attempt(create)
        if op == 'formDataEntries':
            return self.entries(self.vars[step['var']])
        if op in ('formDataAppend', 'formDataSet'):
            name, name_length = utf8(step['name'])
            value, value_length = utf8(step['value'])
            n.ok('rv_dom_dom_form_data_' + op[8:].lower(), [P, P, I, P, I], self.vars[step['var']], name, name_length, value, value_length)
            return None
        if op == 'formDataDelete':
            name, name_length = utf8(step['name'])
            n.ok('rv_dom_dom_form_data_delete', [P, P, I], self.vars[step['var']], name, name_length)
            return None
        if op == 'formDataGet':
            return self.form_data_get(self.vars[step['var']], step['name'])
        if op == 'formDataGetAll':
            return self.form_data_get_all(self.vars[step['var']], step['name'])
        if op == 'formDataHas':
            name, name_length = utf8(step['name'])
            result = I()
            n.ok('rv_dom_dom_form_data_has', [P, P, I, ctypes.POINTER(I)], self.vars[step['var']], name, name_length, ctypes.byref(result))
            return result.value == 1
        if op == 'constructSubmitEvent':
            def construct():
                kind, length = utf8(step['type'])
                init = SubmitEventInit(ctypes.sizeof(SubmitEventInit), int(step['bubbles']), int(step['cancelable']), 0, self.node(step['submitter']))
                event = P()
                status = n.call('rv_dom_submit_event_create', [P, P, I, ctypes.POINTER(SubmitEventInit), ctypes.POINTER(P)],
                                self.document, kind, length, ctypes.byref(init), ctypes.byref(event))
                if status != OK:
                    return status, None
                described = self.describe(event.value)
                n.bind('rv_event_release', None, [P])(event.value)
                return status, described
            return self.attempt(construct)
        if op in ('constructFormDataEvent', 'dispatchFormDataEvent'):
            kind, length = utf8(step['type'])
            dispatch = op == 'dispatchFormDataEvent'
            init = FormDataEventInit(ctypes.sizeof(FormDataEventInit), int(step.get('bubbles', False)), int(step.get('cancelable', False)), 0, self.vars[step['var']])
            event = P()
            n.ok('rv_dom_form_data_event_create', [P, P, I, ctypes.POINTER(FormDataEventInit), ctypes.POINTER(P)],
                 self.document, kind, length, ctypes.byref(init), ctypes.byref(event))
            try:
                if not dispatch:
                    data = n.handle('rv_dom_form_data_event_get_form_data', [P], event.value, nullable=False)
                    same = data == self.vars[step['var']]
                    n.bind('rv_dom_dom_form_data_release', None, [P])(data)
                    return {'sameFormData': same, 'event': self.describe(event.value)}

                def send():
                    target = n.bind('rv_node_as_event_target', P, [P])(self.node(step['form']))
                    prevented = I()
                    status = n.call('rv_event_target_dispatch', [P, P, ctypes.POINTER(I)], target, event.value, ctypes.byref(prevented))
                    n.bind('rv_event_target_release', None, [P])(target)
                    return status, {'dispatched': prevented.value == 0, 'event': self.describe(event.value)}
                return self.attempt(send)
            finally:
                n.bind('rv_event_release', None, [P])(event.value)
        raise AssertionError('unknown op ' + op)


def errors(native, markup):
    """Null, thread and interface errors of the new functions, and the document kept by submission."""
    n = native
    case = Case(n, markup)
    try:
        form, select, paragraph = case.node('f'), case.node('s'), case.node('p')
        n.expect(n.call('rv_dom_html_form_element_request_submit', [P, P], None, None) == NULL_ARGUMENT, 'requestSubmit NULL form')
        n.expect(n.call('rv_dom_html_form_element_request_submit', [P, P], paragraph, None) == WRONG_INTERFACE, 'requestSubmit on <p>')
        n.expect(n.call('rv_dom_html_form_element_submit', [P], paragraph) == WRONG_INTERFACE, 'submit on <p>')
        n.expect(n.call('rv_dom_dom_form_data_create', [P, P, P, ctypes.POINTER(P)], None, None, None, ctypes.byref(P())) == NULL_ARGUMENT, 'FormData NULL document')
        n.expect(n.call('rv_dom_dom_form_data_create', [P, P, P, ctypes.POINTER(P)], case.document, select, None, ctypes.byref(P())) == WRONG_INTERFACE, 'FormData of a <select>')
        n.expect(n.call('rv_dom_dom_form_data_create', [P, P, P, ctypes.POINTER(P)], form, None, None, ctypes.byref(P())) == WRONG_INTERFACE, 'FormData with a form as document')
        data = n.handle('rv_dom_dom_form_data_create', [P, P, P], case.document, None, None, nullable=False)
        case.vars['errors'] = data
        n.expect(n.call('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, None, ctypes.byref(Entries())) == NULL_ARGUMENT, 'entries without context')
        n.expect(n.call('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, form, ctypes.byref(Entries())) == WRONG_INTERFACE, 'entries with an element context')
        n.expect(n.call('rv_dom_dom_form_data_append', [P, P, I, P, I], data, None, 1, None, 0) == NULL_ARGUMENT, 'append NULL name bytes')
        init = FormDataEventInit(ctypes.sizeof(FormDataEventInit), 0, 0, 0, None)
        kind, length = utf8('formdata')
        n.expect(n.call('rv_dom_form_data_event_create', [P, P, I, ctypes.POINTER(FormDataEventInit), ctypes.POINTER(P)],
                        case.document, kind, length, ctypes.byref(init), ctypes.byref(P())) == NULL_ARGUMENT, 'FormDataEvent without formData')
        short = FormDataEventInit(16, 0, 0, 0, data)
        n.expect(n.call('rv_dom_form_data_event_create', [P, P, I, ctypes.POINTER(FormDataEventInit), ctypes.POINTER(P)],
                        case.document, kind, length, ctypes.byref(short), ctypes.byref(P())) == NULL_ARGUMENT, 'FormDataEvent init size short of formData')
        n.expect(n.call('rv_dom_form_data_event_create', [P, P, I, ctypes.POINTER(FormDataEventInit), ctypes.POINTER(P)],
                        case.document, kind, length, None, ctypes.byref(P())) == NULL_ARGUMENT, 'FormDataEvent NULL init')
        sinit = SubmitEventInit(ctypes.sizeof(SubmitEventInit), 0, 0, 0, None)
        event = P()
        n.ok('rv_dom_submit_event_create', [P, P, I, ctypes.POINTER(SubmitEventInit), ctypes.POINTER(P)], case.document, kind, length, None, ctypes.byref(event))
        n.expect(n.call('rv_dom_form_data_event_get_form_data', [P, ctypes.POINTER(P)], event.value, ctypes.byref(P())) == WRONG_INTERFACE, 'formData of a SubmitEvent')
        n.bind('rv_event_release', None, [P])(event.value)
        text_node = n.bind('rv_document_create_comment', P, [P, ctypes.c_char_p])(case.host, b'c')
        sinit.submitter = text_node
        n.expect(n.call('rv_dom_submit_event_create', [P, P, I, ctypes.POINTER(SubmitEventInit), ctypes.POINTER(P)],
                        case.document, kind, length, ctypes.byref(sinit), ctypes.byref(P())) == WRONG_INTERFACE, 'SubmitEvent submitter that is not an HTMLElement')
        n.bind('rv_node_release', None, [P])(text_node)
        options = case.collection('rv_dom_html_select_element_get_options', 's')
        elements = case.collection('rv_dom_html_form_element_get_elements', 'f')
        n.expect(n.call('rv_dom_html_options_collection_get_length', [P, ctypes.POINTER(U)], elements, ctypes.byref(U())) == WRONG_INTERFACE, 'options length on form elements')
        n.expect(n.call('rv_dom_html_form_controls_collection_item', [P, U, ctypes.POINTER(P)], options, 0, ctypes.byref(P())) == WRONG_INTERFACE, 'form controls item on options')
        n.expect(n.call('rv_dom_html_options_collection_add', [P, P, P], options, None, None) == NULL_ARGUMENT, 'options add NULL element')
        statuses = {}

        def worker():
            statuses['request'] = n.call('rv_dom_html_form_element_request_submit', [P, P], form, None)
            statuses['formdata'] = n.call('rv_dom_dom_form_data_create', [P, P, P, ctypes.POINTER(P)], case.document, form, None, ctypes.byref(P()))
            statuses['entries'] = n.call('rv_dom_dom_form_data_entries', [P, P, ctypes.POINTER(Entries)], data, case.document, ctypes.byref(Entries()))
            statuses['options'] = n.call('rv_dom_html_options_collection_remove', [P, I], options, 0)
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        n.expect(statuses == {'request': WRONG_THREAD, 'formdata': WRONG_THREAD, 'entries': WRONG_THREAD, 'options': WRONG_THREAD}, 'wrong thread ' + str(statuses))
        n.expect(case.run({'op': 'optionsLength', 'select': 's'}) == 3, 'wrong-thread remove left options unchanged')
        case.release_collection(options)
        case.release_collection(elements)
        submitted = []
        callback = CALLBACK(lambda context, event: submitted.append(1) or 0)
        listener = n.bind('rv_node_add_event_listener', P, [P, ctypes.c_char_p, I, CALLBACK, P])(form, b'submit', 0, callback, None)
        case.listeners.append(listener)
        for _ in range(2):
            n.ok('rv_dom_html_form_element_request_submit', [P, P], form, None)
            n.ok('rv_dom_html_form_element_submit', [P], form)
        n.expect(len(submitted) == 2, 'two requestSubmit calls each fire submit; submit() fires none')
        for _ in range(10):
            n.bind('rv_run_loop_cycle', I, [I])(50)
        current = n.bind('rv_host_document', P, [P])(case.host)
        same = I()
        n.ok('rv_dom_node_is_same_node', [P, P, ctypes.POINTER(I)], current, case.document, ctypes.byref(same))
        n.bind('rv_node_release', None, [P])(current)
        connected = n.integer('rv_dom_node_get_is_connected', form)
        n.expect(same.value == 1 and connected == 1, 'document kept after submission and the run loop')
    finally:
        case.close()


def verify(directory):
    spec = json.loads((FIXTURES / 'form-collections-cases.json').read_text(encoding='utf-8'))
    oracle = json.loads((FIXTURES / 'form-collections-oracle.json').read_text(encoding='utf-8'))
    expected = {case['name']: case for case in oracle['cases']}
    native = Native(directory)
    native.expect(native.bind('rv_abi_version', I, [])() == ABI, 'ABI version ' + str(ABI))
    has = native.bind('rv_abi_has', I, [ctypes.c_char_p])
    for capability in [b'dom:HTMLFormControlsCollection', b'dom:HTMLOptionsCollection', b'dom:DOMFormData', b'dom:SubmitEvent',
                       b'dom:FormDataEvent', b'dom-form-data-entries']:
        native.expect(has(capability) == 1, 'rv_abi_has ' + capability.decode())
    failures, results = [], []
    for spec_case in spec['cases']:
        case = Case(native, spec['markup'])
        try:
            steps = [{'op': step['op'], 'result': case.run(step)} for step in spec_case['steps']]
        finally:
            case.close()
        results.append({'name': spec_case['name'], 'steps': steps})
        for index, (actual, wanted) in enumerate(zip(steps, expected[spec_case['name']]['steps'])):
            native.assertions += 1
            if actual != wanted:
                failures.append({'case': spec_case['name'], 'step': index, 'op': actual['op'], 'native': actual['result'], 'chromium': wanted['result']})
    errors(native, spec['markup'])
    return native, results, failures, oracle['browser']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native-directory', required=True)
    parser.add_argument('--evidence')
    args = parser.parse_args()
    native, results, failures, browser = verify(args.native_directory)
    if args.evidence:
        Path(args.evidence).write_text(json.dumps({'oracle': browser, 'assertions': native.assertions, 'failures': failures,
                                                   'cases': results}, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    for failure in failures:
        print('MISMATCH', json.dumps(failure, ensure_ascii=False))
    if failures:
        raise SystemExit(f'{len(failures)} steps differ from {browser}')
    print(f'PASS form collections: {native.assertions} assertions against {browser}')


if __name__ == '__main__':
    main()
