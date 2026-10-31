import ctypes, sys, time
sys.path.insert(0, 'tests/abi')
from svg_paint_probe import SvgProbe

markup = ("<!doctype html><html><body><svg id='s' width='200' height='200'>"
          "<rect id='a-t' width='10' height='10'><animate id='a' attributeName='width' from='10' to='110' dur='10s' begin='indefinite' fill='freeze'/></rect>"
          "<rect id='b-t' width='10' height='10'><animate id='b' attributeName='width' from='10' to='110' dur='10s' begin='indefinite' end='indefinite' fill='freeze'/></rect>"
          "<rect id='c-t' width='10' height='10'><animate id='c' attributeName='width' from='10' to='110' dur='10s' begin='indefinite' fill='freeze'/></rect>"
          "</svg></body></html>")

with SvgProbe(sys.argv[1], 300, 300) as p:
    p.load(markup, standalone=False)
    root = p.node('s')
    animation = {name: p.node(name) for name in 'abc'}

    def width(name):
        animated = p.object('rv_dom_svg_rect_element_get_width', [p.pointer], [p.node(name + '-t')], 'svg_animated_length')
        return p.read('svg_length', p.property('svg_animated_length', animated, 'anim_val', 'svg_length'), 'value')

    def start(name):
        value = ctypes.c_float()
        status = p.bind('rv_dom_svg_animation_element_get_start_time', p.integer, [p.pointer, ctypes.POINTER(ctypes.c_float)])(animation[name], ctypes.byref(value))
        return round(value.value, 4) if status == 0 else 'status ' + str(status)

    def seek(seconds):
        p.call('rv_dom_svgsvg_element_set_current_time', [p.pointer, p.single], root, seconds)

    def each(operation, names, *arguments):
        for name in names:
            p.call('rv_dom_svg_animation_element_' + operation, [p.pointer] + [p.single] * len(arguments), animation[name], *arguments)

    p.call('rv_dom_svgsvg_element_pause_animations', [p.pointer], root)
    seek(0)
    each('begin_element', 'ab')
    seek(5)
    each('end_element', 'ab')
    seek(6)
    each('begin_element_at', 'ab', 1.0)
    seek(8)
    for name in 'ab':
        print('PAUSED-SEEK %s endAttr=%s width@8=%g start=%s' % (name, name == 'b', width(name), start(name)), flush=True)

    def pump(milliseconds):
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            p.bind('rv_run_loop_cycle', p.integer, [p.integer])(5)
            p.update()

    seek(20)
    p.call('rv_dom_svgsvg_element_unpause_animations', [p.pointer], root)
    each('begin_element', 'c')
    pump(300)
    each('end_element', 'c')
    pump(300)
    frozen = width('c')
    each('begin_element_at', 'c', 0.2)
    pump(700)
    after = width('c')
    print('RUNNING c frozen=%g after-new-begin=%g restarted=%s' % (frozen, after, after < frozen), flush=True)
