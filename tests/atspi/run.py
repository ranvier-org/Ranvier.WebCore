"""Exercise the optional provider through an independent client on an owned D-Bus bus."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time


def publish_response(directory, command):
    temporary = directory / 'response.tmp'
    temporary.write_text(json.dumps(command))
    temporary.replace(directory / 'response.json')


class Geometry(C.Structure):
    _fields_ = [('size', C.c_uint32), ('known', C.c_int32), ('x', C.c_int32), ('y', C.c_int32), ('scale', C.c_double)]


def bind(library, name, result, *parameters):
    function = getattr(library, name)
    function.restype = result
    function.argtypes = parameters
    return function


def server(args):
    import gi
    from gi.repository import GLib
    native = C.CDLL(str(args.native))
    provider = C.CDLL(str(args.provider))
    abi = bind(native, 'rv_abi_version', C.c_int)
    loaded_native = sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines() if line.split()[-1].endswith('/libRanvierWebCoreHost.so')})
    assert loaded_native == [str(args.native.resolve())], loaded_native
    create = bind(native, 'rv_host_create', C.c_void_p, C.c_int, C.c_int)
    destroy = bind(native, 'rv_host_destroy', None, C.c_void_p)
    load = bind(native, 'rv_host_load_html', C.c_int, C.c_void_p, C.c_char_p, C.c_int)
    update = bind(native, 'rv_host_update', C.c_int, C.c_void_p)
    scale = bind(native, 'rv_host_set_device_scale', C.c_int, C.c_void_p, C.c_float)
    cycle = bind(native, 'rv_run_loop_cycle', C.c_int, C.c_int)
    attach = bind(provider, 'rv_atspi_bridge_create', C.c_int, C.c_void_p, C.c_char_p, C.c_char_p, C.c_int, C.POINTER(Geometry), C.POINTER(C.c_uint64))
    name = bind(provider, 'rv_atspi_bridge_bus_name', C.c_int, C.c_uint64, C.c_void_p, C.c_int, C.POINTER(C.c_int))
    release = bind(provider, 'rv_atspi_bridge_release', C.c_int, C.c_uint64)
    set_geometry = bind(provider, 'rv_atspi_bridge_set_geometry', C.c_int, C.c_uint64, C.POINTER(Geometry))
    event_callback = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)
    element_by_id = bind(native, 'rv_document_get_element_by_id', C.c_void_p, C.c_void_p, C.c_char_p, C.c_int)
    add_listener = bind(native, 'rv_node_add_event_listener', C.c_void_p, C.c_void_p, C.c_char_p, C.c_int, C.c_int, event_callback, C.c_void_p)
    remove_listener = bind(native, 'rv_listener_remove', C.c_int, C.c_void_p)
    release_node = bind(native, 'rv_node_release', None, C.c_void_p)
    remove_node = bind(native, 'rv_node_remove', C.c_int, C.c_void_p)
    create_element = bind(native, 'rv_document_create_element', C.c_void_p, C.c_void_p, C.c_char_p)
    set_attribute = bind(native, 'rv_element_set_attribute', C.c_int, C.c_void_p, C.c_char_p, C.c_char_p, C.c_int)
    append_child = bind(native, 'rv_node_append_child', C.c_int, C.c_void_p, C.c_void_p)
    assert C.sizeof(Geometry) == 24
    geometry = Geometry(24, 1, 100, 200, 1.5)
    host = create(400, 300)
    assert host
    token = C.c_uint64()
    html = '''<!doctype html><title>Accessibility fixture</title><style>
body{margin:0}button,input{position:absolute}#activate{left:10px;top:20px;width:80px;height:30px}
#name{left:10px;top:70px;width:180px}#agree{left:10px;top:120px}#range{left:10px;top:160px}
#disabled{left:200px;top:20px}</style>
<body id="fixture"><button id="activate" aria-label="Activate" aria-describedby="help" aria-controls="name" aria-flowto="disabled">Activate</button><span id="help" aria-label="Help">Instruction</span>
<input id="name" aria-label="Name" aria-describedby="help" value="A😀é">
<input id="agree" type="checkbox" aria-label="Agree">
<input id="range" type="range" min="0" max="10" value="3" aria-label="Level">
<button id="disabled" disabled aria-label="Disabled">Disabled</button>
<div role="group" aria-label="Group" style="position:absolute;left:230px;top:160px"><button id="last" aria-label="Last">Last</button></div>
<p aria-label="Styled text" style="position:absolute;left:10px;top:200px;font-family:serif;font-size:16px;color:rgb(1,2,3)">A<span style="font-weight:700;color:rgb(4,5,6)">😀B</span>C</p>'''.encode()
    assertions = 0
    listener = None
    callback = None
    reentrant_releases = []
    try:
        assert scale(host, 1.5) == 0
        assert load(host, html, len(html)) == 0
        assert update(host) == 0
        application_name = b'Ranvier native accessibility fixture'
        rejected = C.c_uint64(777)
        bad = Geometry(0, 1, 100, 200, 1.5)
        assert attach(host, args.address.encode(), application_name, len(application_name), C.byref(bad), C.byref(rejected)) != 0 and rejected.value == 0
        assertions += 1
        address = None if args.discovery else args.address.encode()
        assert attach(host, address, application_name, len(application_name), C.byref(geometry), C.byref(token)) == 0 and token.value
        assertions += 1
        assert attach(host, args.address.encode(), application_name, len(application_name), C.byref(geometry), C.byref(rejected)) != 0 and rejected.value == 0
        assertions += 1
        wrong_thread = []
        worker = threading.Thread(target=lambda: wrong_thread.append(set_geometry(token.value, C.byref(geometry))))
        worker.start()
        worker.join(3)
        assert not worker.is_alive() and wrong_thread[0] != 0
        assertions += 1
        length = C.c_int()
        assert name(token.value, None, 0, C.byref(length)) != 0 and length.value > 0
        buffer = C.create_string_buffer(length.value)
        assert name(token.value, buffer, length.value, C.byref(length)) == 0
        assertions += 2
        ready = dict(pid=os.getpid(), bus=buffer.raw.decode(), root='/org/a11y/atspi/accessible/root', assertions=assertions, nativeAbi=abi(), loadedNative=loaded_native)
        (args.output / 'ready.tmp').write_text(json.dumps(ready))
        (args.output / 'ready.tmp').replace(args.output / 'ready.json')
        deadline = time.monotonic() + 60
        paused = False
        while not (args.output / 'stop.json').exists():
            assert time.monotonic() < deadline, 'Provider fixture lifetime exceeded'
            request = args.output / 'request.json'
            if request.exists():
                command = json.loads(request.read_text())
                request.unlink()
                if command['action'] == 'reload':
                    replacement = b'<title>Replacement document</title><button id="replacement" aria-label="Replacement">New</button>'
                    assert load(host, replacement, len(replacement)) == 0
                    assert update(host) == 0
                elif command['action'] == 'arm-release':
                    @event_callback
                    def callback(context, event):
                        captured = token.value
                        token.value = 0
                        reentrant_releases.append(release(captured))
                        return 0
                    element = element_by_id(host, b'replacement', 11)
                    assert element
                    listener = add_listener(element, b'click', 5, 0, callback, None)
                    release_node(element)
                    assert listener
                elif command['action'] == 'release':
                    if paused:
                        time.sleep(0.05)
                    assert release(token.value) == 0
                    token.value = 0
                    paused = False
                elif command['action'] == 'pause':
                    paused = True
                elif command['action'] in ['remove-field', 'remove-last']:
                    identifier = b'name' if command['action'] == 'remove-field' else b'last'
                    element = element_by_id(host, identifier, len(identifier))
                    assert element
                    assert remove_node(element) == 0
                    release_node(element)
                    assert update(host) == 0
                elif command['action'] == 'add-control':
                    parent = element_by_id(host, b'fixture', 7)
                    element = create_element(host, b'button')
                    assert parent and element
                    assert set_attribute(element, b'aria-label', b'Dynamic', 7) == 0
                    assert append_child(parent, element) == 0
                    release_node(element)
                    release_node(parent)
                    assert update(host) == 0
                else:
                    raise AssertionError(command)
                publish_response(args.output, command)
            if not paused:
                cycle(0)
            time.sleep(0.002)
    finally:
        if listener:
            assert remove_listener(listener) == 0
        if token.value:
            assert release(token.value) == 0
            assert release(token.value) != 0
        destroy(host)
        (args.output / 'server-cleanup.json').write_text(json.dumps(dict(assertions=assertions + 2, providerReleased=True, hostDestroyed=True, reentrantReleaseResults=reentrant_releases)))


def client(args):
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Gio, GLib, Atspi
    ready = json.loads((args.output / 'ready.json').read_text())
    connection = Gio.DBusConnection.new_for_address_sync(args.address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    rows = []
    events = []
    subscription = connection.signal_subscribe(ready['bus'], 'org.a11y.atspi.Event.Object', None, None, None,
        Gio.DBusSignalFlags.NONE, lambda connection, sender, path, interface, signal, parameters, data: events.append(dict(path=path, signal=signal, parameters=parameters.unpack())), None)
    cache_events = []
    cache_subscription = connection.signal_subscribe(ready['bus'], 'org.a11y.atspi.Cache', None, None, None,
        Gio.DBusSignalFlags.NONE, lambda connection, sender, path, interface, signal, parameters, data: cache_events.append(dict(signal=signal, parameters=parameters.unpack())), None)

    def check(condition, label):
        rows.append(dict(label=label, passed=bool(condition)))
        assert condition, label

    def call(path, interface, method, signature=None, arguments=()):
        parameters = GLib.Variant(signature, arguments) if signature else None
        return connection.call_sync(ready['bus'], path, interface, method, parameters, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def prop(path, interface, name):
        return call(path, 'org.freedesktop.DBus.Properties', 'Get', '(ss)', (interface, name))[0]

    def request(action):
        response = args.output / 'response.json'
        response.unlink(missing_ok=True)
        (args.output / 'request.tmp').write_text(json.dumps(dict(action=action)))
        (args.output / 'request.tmp').replace(args.output / 'request.json')
        deadline = time.monotonic() + 3
        while not response.exists():
            assert time.monotonic() < deadline, action
            time.sleep(0.005)
        assert json.loads(response.read_text())['action'] == action

    accessible = 'org.a11y.atspi.Accessible'
    component = 'org.a11y.atspi.Component'
    action = 'org.a11y.atspi.Action'
    text = 'org.a11y.atspi.Text'
    root = ready['root']
    try:
        if args.registry:
            check(Atspi.init() == 0, 'independent libatspi client initializes on owned bus')
            desktop = Atspi.get_desktop(0)
            check(desktop is not None, 'real AT-SPI registry exposes desktop')
            applications = [desktop.get_child_at_index(i).get_name() for i in range(desktop.get_child_count())]
            check('Ranvier native accessibility fixture' in applications, 'real AT-SPI registry discovers native application')
        check(prop(root, accessible, 'Name') == 'Ranvier native accessibility fixture', 'application name through D-Bus')
        check(call(root, accessible, 'GetRole')[0] == int(Atspi.Role.APPLICATION), 'application role')
        found = {}

        def visit(path):
            name = prop(path, accessible, 'Name')
            if name:
                found[name] = path
            for bus, child in call(path, accessible, 'GetChildren')[0]:
                check(bus == ready['bus'], 'child uses provider bus')
                visit(child)

        visit(root)
        check(all(name in found for name in ['Activate', 'Name', 'Agree', 'Level', 'Disabled']), 'native named controls are exposed')
        button, field, checkbox, slider = [found[name] for name in ['Activate', 'Name', 'Agree', 'Level']]
        check(call(button, accessible, 'GetRole')[0] == int(Atspi.Role.PUSH_BUTTON), 'native button role')
        check(call(checkbox, accessible, 'GetRole')[0] == int(Atspi.Role.CHECK_BOX), 'native checkbox role')
        check(call(button, component, 'GetExtents', '(u)', (int(Atspi.CoordType.SCREEN),))[0] == (115, 230, 120, 45), 'physical screen geometry at 1.5')
        check(call(button, component, 'GetExtents', '(u)', (int(Atspi.CoordType.WINDOW),))[0] == (15, 30, 120, 45), 'physical window geometry at 1.5')
        hit = call(button, component, 'GetAccessibleAtPoint', '(iiu)', (120, 235, int(Atspi.CoordType.SCREEN)))[0]
        check(hit[0] == ready['bus'] and prop(hit[1], accessible, 'Name') == 'Activate', 'physical screen hit-test reaches native button')
        relations = call(button, accessible, 'GetRelationSet')[0]
        check(any(kind == int(Atspi.RelationType.DESCRIBED_BY) and (ready['bus'], found['Help']) in targets for kind, targets in relations), 'native described-by relationship preserves target identity')
        check(call(field, component, 'GrabFocus')[0], 'native focus action')
        check(prop(field, text, 'CharacterCount') == 3, 'AT-SPI counts scalar characters rather than UTF-16 units')
        check(call(field, text, 'GetText', '(ii)', (0, -1))[0] == 'A😀é', 'non-BMP native text roundtrip')
        check(call(field, text, 'GetText', '(ii)', (1, 2))[0] == '😀', 'scalar substring crosses a surrogate pair')
        char_window = call(field, text, 'GetCharacterExtents', '(iu)', (1, int(Atspi.CoordType.WINDOW)))
        char_screen = call(field, text, 'GetCharacterExtents', '(iu)', (1, int(Atspi.CoordType.SCREEN)))
        check(char_window[2] > 0 and char_window[3] > 0, 'non-BMP character exposes native text geometry')
        check(char_screen == (char_window[0] + 100, char_window[1] + 200, char_window[2], char_window[3]), 'text geometry uses physical screen translation')
        check(call(field, text, 'GetRangeExtents', '(iiu)', (1, 2, int(Atspi.CoordType.WINDOW))) == char_window, 'scalar character and surrogate-pair range geometry agree')
        if args.extended_text:
            def extended(label, path, interface, method, signature, arguments, predicate):
                try:
                    actual = call(path, interface, method, signature, arguments)
                    rows.append(dict(label=label, passed=bool(predicate(actual)), actual=actual))
                except GLib.Error as error:
                    rows.append(dict(label=label, passed=False, error=str(error)))

            relation_cases = [
                ('Help', Atspi.RelationType.DESCRIPTION_FOR, ['Activate', 'Name']),
                ('Name', Atspi.RelationType.CONTROLLED_BY, ['Activate']),
                ('Disabled', Atspi.RelationType.FLOWS_FROM, ['Activate'])]
            for source, kind, names in relation_cases:
                expected_targets = {(ready['bus'], found[name]) for name in names}
                extended('inverse relation ' + source, found[source], accessible, 'GetRelationSet', None, (),
                         lambda result, kind=kind, expected=expected_targets: any(
                             relation == int(kind) and set(targets) == expected for relation, targets in result[0]))
            extended('physical point maps through native UTF16 to scalar offset', field, text, 'GetOffsetAtPoint', '(iiu)',
                     (char_window[0] + max(1, char_window[2] // 4), char_window[1] + char_window[3] // 2, int(Atspi.CoordType.WINDOW)),
                     lambda result: result == (1,))
            styled = found['Styled text']
            extended('styled accessible text preserves scalar content', styled, text, 'GetText', '(ii)', (0, -1),
                     lambda result: result == ('A😀BC',))
            extended('default text attributes reflect the native computed style', styled, text, 'GetDefaultAttributes', None, (),
                     lambda result: result[0].get('weight') == '400' and result[0].get('fg-color') == '1,2,3' and result[0].get('size') == '12pt')
            extended('attribute run retains nonBMP scalar boundaries and overrides', styled, text, 'GetAttributeRun', '(ib)', (1, False),
                     lambda result: result[1:] == (1, 3) and result[0].get('weight') == '700' and result[0].get('fg-color') == '4,5,6')
            extended('attribute run includes requested defaults', styled, text, 'GetAttributeRun', '(ib)', (2, True),
                     lambda result: result[1:] == (1, 3) and result[0].get('size') == '12pt' and result[0].get('weight') == '700')
            extended('default run omits inherited defaults', styled, text, 'GetAttributes', '(i)', (0,),
                     lambda result: result == ({}, 0, 1))
            extended('trailing default run remains separate from styled span', styled, text, 'GetAttributes', '(i)', (3,),
                     lambda result: result == ({}, 3, 4))
            extended('named text attribute lookup', styled, text, 'GetAttributeValue', '(is)', (1, 'weight'),
                     lambda result: result == ('700',))
            extended('bounded range uses scalar offsets around a complete nonBMP glyph', field, text, 'GetBoundedRanges', '(iiiiuuu)',
                     (*char_window, int(Atspi.CoordType.WINDOW), int(Atspi.TextClipType.BOTH), int(Atspi.TextClipType.BOTH)),
                     lambda result: [(item[0], item[1], item[2]) for item in result[0]] == [(1, 2, '😀')])
            extended('empty physical text intersection returns no range', field, text, 'GetBoundedRanges', '(iiiiuuu)',
                     (100000, 100000, 20, 20, int(Atspi.CoordType.WINDOW), int(Atspi.TextClipType.NONE), int(Atspi.TextClipType.NONE)),
                     lambda result: result == ([],))
        check(call(field, text, 'SetCaretOffset', '(i)', (2,))[0], 'scalar caret forwards native UTF-16 offset')
        check(prop(field, text, 'CaretOffset') == 2, 'native caret maps back to scalar offset')
        check(call(field, text, 'SetSelection', '(iii)', (0, 1, 3))[0], 'native selection action')
        check(call(field, text, 'GetSelection', '(i)', (0,)) == (1, 3), 'native selection readback')
        check(call(field, 'org.a11y.atspi.EditableText', 'SetTextContents', '(s)', ('Replaced 𐐷',))[0], 'editable native value action')
        check(call(field, text, 'GetText', '(ii)', (0, -1))[0] == 'Replaced 𐐷', 'edited native value readback')
        deadline = time.monotonic() + 2
        context = GLib.MainContext.default()
        while sum(event['path'] == field and event['signal'] == 'TextChanged' for event in events) < 2 and time.monotonic() < deadline:
            while context.pending(): context.iteration(False)
            time.sleep(0.005)
        check(any(event['path'] == field and event['signal'] == 'TextChanged' for event in events), 'native text edits deliver AT-SPI text events')
        changes = [list(event['parameters'][:4]) for event in events if event['path'] == field and event['signal'] == 'TextChanged']
        check(changes == [['delete', 0, 3, 'A😀é'], ['insert', 0, 10, 'Replaced 𐐷']], 'text events preserve exact scalar offsets and deleted/inserted payloads')
        available = call(checkbox, action, 'GetActions')[0]
        click = next(index for index, item in enumerate(available) if item[0] == 'click')
        before = call(checkbox, accessible, 'GetState')[0]
        check(call(checkbox, action, 'DoAction', '(i)', (click,))[0], 'native checkbox press')
        after = call(checkbox, accessible, 'GetState')[0]
        checked = int(Atspi.StateType.CHECKED)
        check(not (before[checked // 32] & (1 << (checked % 32))) and bool(after[checked // 32] & (1 << (checked % 32))), 'native checked state changes')
        check(not call(found['Disabled'], action, 'DoAction', '(i)', (0,))[0], 'disabled native action is rejected')
        value = 'org.a11y.atspi.Value'
        check(prop(slider, value, 'CurrentValue') == 3.0, 'native range value')
        call(slider, 'org.freedesktop.DBus.Properties', 'Set', '(ssv)', (value, 'CurrentValue', GLib.Variant('d', 6.0)))
        check(prop(slider, value, 'CurrentValue') == 6.0, 'native range value action')
        check(prop(slider, value, 'MinimumValue') == 0.0 and prop(slider, value, 'MaximumValue') == 10.0, 'native range limits')
        rejected = False
        try:
            call(field, text, 'GetText', '(ii)', (100, 101))
        except GLib.Error:
            rejected = True
        check(rejected, 'invalid text range returns a D-Bus error')
        request('add-control')
        deadline = time.monotonic() + 2
        added = lambda: any(event['signal'] == 'ChildrenChanged' and event['parameters'][0] == 'add' for event in events)
        while not added() and time.monotonic() < deadline:
            while context.pending(): context.iteration(False)
            time.sleep(0.005)
        visit(root)
        check('Dynamic' in found and added(), 'adding a native control exposes its child-addition event and accessible object')
        check(any(event['signal'] == 'AddAccessible' and event['parameters'][0][0] == (ready['bus'], found['Dynamic']) for event in cache_events), 'new native control updates the AT-SPI cache')
        check(call(field, component, 'GrabFocus')[0], 'editable can be focused before removal')
        request('remove-field')
        deadline = time.monotonic() + 2
        removed = lambda: any(event['signal'] == 'ChildrenChanged' and event['parameters'][0] == 'remove'
            and event['parameters'][3] == (ready['bus'], field) for event in events)
        while not removed() and time.monotonic() < deadline:
            while context.pending(): context.iteration(False)
            time.sleep(0.005)
        check(removed(), 'removing a native control delivers its exact accessible child-removal identity')
        check(any(event['signal'] == 'RemoveAccessible' and event['parameters'][0] == (ready['bus'], field) for event in cache_events), 'detached native control is retired from the AT-SPI cache')
        check(call(found['Dynamic'], component, 'GrabFocus')[0], 'another control accepts focus after focused node removal')
        request('remove-last')
        deadline = time.monotonic() + 2
        last_removed = lambda: any(event['signal'] == 'ChildrenChanged' and event['path'] == found['Group']
            and event['parameters'][0] == 'remove' and event['parameters'][3] == (ready['bus'], found['Last']) for event in events)
        while not last_removed() and time.monotonic() < deadline:
            while context.pending(): context.iteration(False)
            time.sleep(0.005)
        check(last_removed(), 'removing the final child reports its original parent and identity')
        check(call(found['Group'], accessible, 'GetChildren')[0] == [], 'empty native child lists do not retain the old cache snapshot')
        old_field = field
        request('reload')
        rejected = False
        try:
            prop(old_field, accessible, 'Name')
        except GLib.Error:
            rejected = True
        check(rejected, 'old document objects are unavailable after replacement')
        found.clear()
        visit(root)
        check('Replacement' in found and 'Name' not in found, 'replacement document is exposed without old controls')
        check(call(found['Replacement'], component, 'GrabFocus')[0], 'replacement document accepts focus after node retirement')
        if args.queued_set:
            request('pause')
            completion = []

            def completed(connection, result):
                try:
                    connection.call_finish(result)
                    completion.append('success')
                except GLib.Error as error:
                    completion.append(Gio.DBusError.get_remote_error(error))

            connection.call(ready['bus'], root, 'org.freedesktop.DBus.Properties', 'Set',
                GLib.Variant('(ssv)', ('org.a11y.atspi.Application', 'Id', GLib.Variant('i', 42))),
                None, Gio.DBusCallFlags.NONE, 3000, None, completed)
            connection.flush_sync(None)
            request('release')
            deadline = time.monotonic() + 4
            while not completion and time.monotonic() < deadline:
                while context.pending(): context.iteration(False)
                time.sleep(0.005)
            check(completion == ['org.freedesktop.DBus.Error.UnknownMethod'], 'queued property setter rejects an unregistered application without invoking stale state')
        else:
            request('arm-release')
            check(call(found['Replacement'], action, 'DoAction', '(i)', (0,))[0], 'native action completes while its application releases the provider reentrantly')
        rejected = False
        try:
            prop(root, accessible, 'Name')
        except GLib.Error:
            rejected = True
        check(rejected, 'released bridge objects cannot be queried')
        if args.registry:
            deadline = time.monotonic() + 3
            while desktop.get_child_count() and time.monotonic() < deadline:
                while context.pending(): context.iteration(False)
                time.sleep(0.01)
            check(desktop.get_child_count() == 0, 'released application is removed from the real registry')
        if args.extended_text:
            assert all(row['passed'] for row in rows), [row['label'] for row in rows if not row['passed']]
    finally:
        (args.output / 'client-report.json').write_text(json.dumps(dict(assertions=len(rows), rows=rows, events=events, cacheEvents=cache_events), indent=2))
        connection.signal_unsubscribe(subscription)
        connection.signal_unsubscribe(cache_subscription)
        connection.close_sync(None)


def bus_service(args):
    from gi.repository import Gio, GLib
    connection = Gio.DBusConnection.new_for_address_sync(args.address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    schema = Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.a11y.Bus"><method name="GetAddress"><arg type="s" direction="out"/></method></interface></node>')
    registration = connection.register_object('/org/a11y/bus', schema.interfaces[0],
        lambda connection, sender, path, interface, method, parameters, invocation: invocation.return_value(GLib.Variant('(s)', (args.address,))), None, None)
    result = connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', ('org.a11y.Bus', 0)), None, Gio.DBusCallFlags.NONE, 1000, None)
    assert result.unpack()[0] == 1
    (args.output / 'bus-service-ready.json').write_text('{}')
    context = GLib.MainContext.default()
    try:
        while not (args.output / 'stop.json').exists():
            while context.pending(): context.iteration(False)
            time.sleep(0.002)
    finally:
        connection.unregister_object(registration)
        connection.close_sync(None)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    before = hashlib.sha256(args.native.read_bytes()).hexdigest()
    bus = None
    child = None
    registry = None
    registry_log = None
    discovery_service = None
    discovery_log = None
    started = time.monotonic()
    try:
        bus = subprocess.Popen(['/usr/bin/dbus-daemon', '--session', '--nofork', '--print-address=1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert select.select([bus.stdout], [], [], 5)[0], 'Owned bus did not report its address'
        address = bus.stdout.readline().strip()
        assert address.startswith('unix:')
        environment = os.environ | {'DBUS_SESSION_BUS_ADDRESS': address, 'AT_SPI_BUS_ADDRESS': address}
        if args.registry:
            import gi
            from gi.repository import Gio, GLib
            registry_log = (args.output / 'registry.log').open('w')
            registry = subprocess.Popen(['/usr/libexec/at-spi2-registryd'], env=environment, stdout=registry_log, stderr=subprocess.STDOUT)
            connection = Gio.DBusConnection.new_for_address_sync(address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
            deadline = time.monotonic() + 5
            while not connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', ('org.a11y.atspi.Registry',)), None, Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]:
                assert registry.poll() is None, 'Owned AT-SPI registry exited'
                assert time.monotonic() < deadline, 'Owned AT-SPI registry did not acquire its name'
                time.sleep(0.02)
            connection.close_sync(None)
        common = ['--native', str(args.native), '--provider', str(args.provider), '--output', str(args.output), '--address', address]
        if args.registry:
            common += ['--registry']
        if args.discovery:
            common += ['--discovery', args.discovery]
        if args.queued_set:
            common += ['--queued-set']
        if args.extended_text:
            common += ['--extended-text']
        if args.discovery == 'session':
            discovery_log = (args.output / 'bus-service.log').open('w')
            discovery_service = subprocess.Popen([sys.executable, __file__, 'bus_service'] + common, env=environment, stdout=discovery_log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 5
            while not (args.output / 'bus-service-ready.json').exists():
                assert discovery_service.poll() is None
                assert time.monotonic() < deadline
                time.sleep(0.01)
        server_environment = environment.copy()
        if args.discovery == 'session':
            server_environment.pop('AT_SPI_BUS_ADDRESS', None)
        if args.managed_command:
            command = json.loads(args.managed_command.read_text())
            server_environment.update(LD_LIBRARY_PATH=str(args.provider.parent) + ':' + str(args.native.parent),
                SDL_VIDEODRIVER='x11', RANVIER_ATSPI_OWNED_BUS_TEST='1')
            if args.provider_disabled:
                server_environment['LD_LIBRARY_PATH'] = str(args.native.parent)
                server_environment['RANVIER_ATSPI_OWNED_BUS_TEST'] = '0'
            with (args.output / 'managed.log').open('w') as output:
                child = subprocess.Popen(command, env=server_environment, stdout=output, stderr=subprocess.STDOUT)
                code = child.wait(timeout=90)
            (args.output / 'managed-exit.json').write_text(json.dumps(dict(pid=child.pid, command=command, exit=code)))
            assert code == 0, (code, str(args.output / 'managed.log'), (args.output / 'managed.log').read_text()[-2500:])
            (args.output / 'client-report.json').write_text(json.dumps(dict(assertions=1, managedCommand=command, managedExit=code)))
        else:
            child = run_protocol_client(args, common, server_environment, environment)
    finally:
        (args.output / 'stop.json').write_text('{}')
        if child:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        if discovery_service:
            try: discovery_service.wait(timeout=5)
            except subprocess.TimeoutExpired: discovery_service.kill(); discovery_service.wait(timeout=5)
        if discovery_log:
            discovery_log.close()
        if bus:
            if registry:
                registry.terminate()
                try: registry.wait(timeout=5)
                except subprocess.TimeoutExpired: registry.kill(); registry.wait(timeout=5)
            if registry_log:
                registry_log.close()
            bus.terminate()
            try: bus.wait(timeout=5)
            except subprocess.TimeoutExpired: bus.kill(); bus.wait(timeout=5)
        after = hashlib.sha256(args.native.read_bytes()).hexdigest()
        assert before == after
        receipt = dict(nativeBefore=before, nativeAfter=after, providerSha256=hashlib.sha256(args.provider.read_bytes()).hexdigest(),
                       busPid=bus.pid if bus else None, serverPid=child.pid if child else None, registryPid=registry.pid if registry else None, discoveryPid=discovery_service.pid if discovery_service else None, allOwnedProcessesExited=True,
                       seconds=time.monotonic()-started)
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    report = json.loads((args.output / 'client-report.json').read_text())
    print(json.dumps(dict(assertions=report['assertions'], nativeUnchanged=before == after, processesExited=True)))


def run_protocol_client(args, common, server_environment, environment):
    child = None
    try:
        with (args.output / 'server.log').open('w') as output:
            child = subprocess.Popen([sys.executable, __file__, 'server'] + common, env=server_environment, stdout=output, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 10
            while not (args.output / 'ready.json').exists():
                assert child.poll() is None, (args.output / 'server.log').read_text()
                assert time.monotonic() < deadline, 'Provider did not become ready'
                time.sleep(0.02)
            with (args.output / 'client.log').open('w') as client_log:
                result = subprocess.run([sys.executable, __file__, 'client'] + common, env=environment, stdout=client_log, stderr=subprocess.STDOUT, timeout=40)
            assert result.returncode == 0, (args.output / 'client.log').read_text()
    finally:
        (args.output / 'stop.json').write_text('{}')
        if child:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
    return child


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'server', 'client', 'bus_service'])
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--address')
    parser.add_argument('--registry', action='store_true')
    parser.add_argument('--discovery', choices=['environment', 'session'])
    parser.add_argument('--managed-command', type=Path)
    parser.add_argument('--provider-disabled', action='store_true')
    parser.add_argument('--queued-set', action='store_true')
    parser.add_argument('--extended-text', action='store_true')
    arguments = parser.parse_args()
    globals()[arguments.mode](arguments)
