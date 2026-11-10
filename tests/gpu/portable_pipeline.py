"""Shared bounded transport assertions; platform callers provide a completed-frame pixel check."""
import ctypes as C
import threading
import time


def exercise(runtime, host, consumer, inspect, activate=lambda: None):
    P, I, U = C.c_void_p, C.c_int32, C.c_uint64
    def bind(name, result, *parameters):
        fn = getattr(runtime, name)
        fn.restype, fn.argtypes = result, parameters
        return fn
    configure = bind('rv_host_configure_gpu_pipeline', I, P, P)
    submit = bind('rv_host_submit_gpu_frame', I, P, U)
    acquire = bind('rv_host_try_acquire_completed_gpu_frame', I, P, C.POINTER(U), C.POINTER(P))
    release = bind('rv_gpu_frame_release', I, P)
    resize = bind('rv_host_resize', I, P, I, I)
    load = bind('rv_host_load_html', I, P, C.c_char_p, I)
    destroy = bind('rv_host_destroy', None, P)
    assert configure(host, consumer) == 0
    def take():
        deadline = time.monotonic() + 10
        while True:
            identity, frame = U(99), P(1)
            status = acquire(host, C.byref(identity), C.byref(frame))
            if status == 0:
                return identity.value, frame
            assert status == 1 and identity.value == 0 and not frame.value, status
            assert time.monotonic() < deadline, 'producer completion timeout'
            time.sleep(.002)
    frames = []
    for identity in range(1, 4):
        assert submit(host, identity) == 0
        received, frame = take()
        assert received == identity
        inspect(frame, 80, 60)
        frames.append(frame)
    assert submit(host, 4) == 1, 'three held slots exhaust the pool'
    assert resize(host, 96, 72) == 0
    assert submit(host, 4) == 1, 'resize cannot allocate a fourth slot'
    foreign = []
    thread = threading.Thread(target=lambda: foreign.append(release(frames[0])))
    thread.start()
    thread.join()
    assert foreign == [-2]
    assert release(frames.pop(0)) == 0
    deadline = time.monotonic() + 10
    while (status := submit(host, 4)) == 1:
        assert time.monotonic() < deadline
        time.sleep(.002)
    assert status == 0
    identity, resized = take()
    assert identity == 4
    inspect(resized, 96, 72)
    assert release(resized) == 0
    assert submit(host, 4) == -9, 'identities remain monotonic'
    for frame in frames:
        assert release(frame) == 0
    deadline = time.monotonic() + 10
    while (status := submit(host, 5)) == 1:
        assert time.monotonic() < deadline
        time.sleep(.002)
    assert status == 0
    html = b'<body style="background:green"></body>'
    assert load(host, html, len(html)) == 0
    identity, frame = U(), P()
    # Completed old-document work must be discarded, even if it completes after replacement.
    for _ in range(10):
        assert acquire(host, C.byref(identity), C.byref(frame)) == 1
        time.sleep(.002)
    assert submit(host, 6) == 0
    _, held = take()
    destroy(host)
    activate()
    assert release(held) == 0, 'lease outlives host and releases on owner'
    print('PORTABLE_GPU_PIPELINE=PASS', flush=True)
