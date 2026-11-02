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
    create = bind(native, 'rv_host_create', C.c_void_p, C.c_int, C.c_int)
    destroy = bind(native, 'rv_host_destroy', None, C.c_void_p)
    load = bind(native, 'rv_host_load_html', C.c_int, C.c_void_p, C.c_char_p, C.c_int)
    update = bind(native, 'rv_host_update', C.c_int, C.c_void_p)
    cycle = bind(native, 'rv_run_loop_cycle', C.c_int, C.c_int)
    attach = bind(provider, 'rv_atspi_bridge_create', C.c_int, C.c_void_p, C.c_char_p, C.c_char_p, C.c_int, C.POINTER(Geometry), C.POINTER(C.c_uint64))
    name = bind(provider, 'rv_atspi_bridge_bus_name', C.c_int, C.c_uint64, C.c_void_p, C.c_int, C.POINTER(C.c_int))
    release = bind(provider, 'rv_atspi_bridge_release', C.c_int, C.c_uint64)
    set_geometry = bind(provider, 'rv_atspi_bridge_set_geometry', C.c_int, C.c_uint64, C.POINTER(Geometry))
    assert C.sizeof(Geometry) == 24
    geometry = Geometry(24, 1, 100, 200, 1.5)
    host = create(400, 300)
    assert host
    token = C.c_uint64()
    html = '''<!doctype html><title>Accessibility fixture</title><style>
body{margin:0}button,input{position:absolute}#activate{left:10px;top:20px;width:80px;height:30px}
#name{left:10px;top:70px;width:180px}#agree{left:10px;top:120px}#range{left:10px;top:160px}
#disabled{left:200px;top:20px}</style>
<button id="activate" aria-label="Activate">Activate</button>
<input id="name" aria-label="Name" value="A😀é">
<input id="agree" type="checkbox" aria-label="Agree">
<input id="range" type="range" min="0" max="10" value="3" aria-label="Level">
<button id="disabled" disabled aria-label="Disabled">Disabled</button>'''.encode()
    assertions = 0
    try:
        assert load(host, html, len(html)) == 0
        assert update(host) == 0
        application_name = b'Ranvier native accessibility fixture'
        rejected = C.c_uint64(777)
        bad = Geometry(0, 1, 100, 200, 1.5)
        assert attach(host, args.address.encode(), application_name, len(application_name), C.byref(bad), C.byref(rejected)) != 0 and rejected.value == 0
        assertions += 1
        assert attach(host, args.address.encode(), application_name, len(application_name), C.byref(geometry), C.byref(token)) == 0 and token.value
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
        ready = dict(pid=os.getpid(), bus=buffer.raw.decode(), root='/org/a11y/atspi/accessible/root', assertions=assertions)
        (args.output / 'ready.tmp').write_text(json.dumps(ready))
        (args.output / 'ready.tmp').replace(args.output / 'ready.json')
        deadline = time.monotonic() + 60
        context = GLib.MainContext.default()
        while not (args.output / 'stop.json').exists():
            assert time.monotonic() < deadline, 'Provider fixture lifetime exceeded'
            cycle(0)
            while context.pending():
                context.iteration(False)
            time.sleep(0.002)
    finally:
        if token.value:
            assert release(token.value) == 0
            assert release(token.value) != 0
        destroy(host)
        (args.output / 'server-cleanup.json').write_text(json.dumps(dict(assertions=assertions + 2, providerReleased=True, hostDestroyed=True)))


def client(args):
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Gio, GLib, Atspi
    ready = json.loads((args.output / 'ready.json').read_text())
    connection = Gio.DBusConnection.new_for_address_sync(args.address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
    rows = []

    def check(condition, label):
        rows.append(dict(label=label, passed=bool(condition)))
        assert condition, label

    def call(path, interface, method, signature=None, arguments=()):
        parameters = GLib.Variant(signature, arguments) if signature else None
        return connection.call_sync(ready['bus'], path, interface, method, parameters, None, Gio.DBusCallFlags.NONE, 3000, None).unpack()

    def prop(path, interface, name):
        return call(path, 'org.freedesktop.DBus.Properties', 'Get', '(ss)', (interface, name))[0]

    accessible = 'org.a11y.atspi.Accessible'
    component = 'org.a11y.atspi.Component'
    action = 'org.a11y.atspi.Action'
    text = 'org.a11y.atspi.Text'
    root = ready['root']
    try:
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
        check(call(field, component, 'GrabFocus')[0], 'native focus action')
        check(prop(field, text, 'CharacterCount') == 3, 'AT-SPI counts scalar characters rather than UTF-16 units')
        check(call(field, text, 'GetText', '(ii)', (0, -1))[0] == 'A😀é', 'non-BMP native text roundtrip')
        check(call(field, text, 'GetText', '(ii)', (1, 2))[0] == '😀', 'scalar substring crosses a surrogate pair')
        check(call(field, text, 'SetCaretOffset', '(i)', (2,))[0], 'scalar caret forwards native UTF-16 offset')
        check(prop(field, text, 'CaretOffset') == 2, 'native caret maps back to scalar offset')
        check(call(field, text, 'SetSelection', '(iii)', (0, 1, 3))[0], 'native selection action')
        check(call(field, text, 'GetSelection', '(i)', (0,)) == (1, 3), 'native selection readback')
        check(call(field, 'org.a11y.atspi.EditableText', 'SetTextContents', '(s)', ('Replaced 𐐷',))[0], 'editable native value action')
        check(call(field, text, 'GetText', '(ii)', (0, -1))[0] == 'Replaced 𐐷', 'edited native value readback')
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
    finally:
        (args.output / 'client-report.json').write_text(json.dumps(dict(assertions=len(rows), rows=rows), indent=2))
        connection.close_sync(None)


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    before = hashlib.sha256(args.native.read_bytes()).hexdigest()
    bus = None
    child = None
    started = time.monotonic()
    try:
        bus = subprocess.Popen(['/usr/bin/dbus-daemon', '--session', '--nofork', '--print-address=1'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        assert select.select([bus.stdout], [], [], 5)[0], 'Owned bus did not report its address'
        address = bus.stdout.readline().strip()
        assert address.startswith('unix:')
        common = ['--native', str(args.native), '--provider', str(args.provider), '--output', str(args.output), '--address', address]
        with (args.output / 'server.log').open('w') as output:
            child = subprocess.Popen([sys.executable, __file__, 'server'] + common, stdout=output, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 10
            while not (args.output / 'ready.json').exists():
                assert child.poll() is None, (args.output / 'server.log').read_text()
                assert time.monotonic() < deadline, 'Provider did not become ready'
                time.sleep(0.02)
            with (args.output / 'client.log').open('w') as client_log:
                result = subprocess.run([sys.executable, __file__, 'client'] + common, stdout=client_log, stderr=subprocess.STDOUT, timeout=40)
            assert result.returncode == 0, (args.output / 'client.log').read_text()
    finally:
        (args.output / 'stop.json').write_text('{}')
        if child:
            try: child.wait(timeout=5)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
        if bus:
            bus.terminate()
            try: bus.wait(timeout=5)
            except subprocess.TimeoutExpired: bus.kill(); bus.wait(timeout=5)
        after = hashlib.sha256(args.native.read_bytes()).hexdigest()
        assert before == after
        receipt = dict(nativeBefore=before, nativeAfter=after, providerSha256=hashlib.sha256(args.provider.read_bytes()).hexdigest(),
                       busPid=bus.pid if bus else None, serverPid=child.pid if child else None, allOwnedProcessesExited=True,
                       seconds=time.monotonic()-started)
        (args.output / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    report = json.loads((args.output / 'client-report.json').read_text())
    print(json.dumps(dict(assertions=report['assertions'], nativeUnchanged=before == after, processesExited=True)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['run', 'server', 'client'])
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--address')
    arguments = parser.parse_args()
    globals()[arguments.mode](arguments)
