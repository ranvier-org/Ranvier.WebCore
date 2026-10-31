"""Generated rv_dom_* string inputs carry UTF-8 bytes and an explicit byte count (ABI 51). A probe marks such an
argument Utf8 in a function's argument types; bind passes it as a pointer and an int32_t length: str and bytes as
their UTF-8 bytes, None as length -1 (null or absent)."""

import ctypes


class Utf8:
    """The argument-type marker of a generated string input."""


def encode(value):
    """The (pointer, length) pair of a string input; the buffer lives as long as the returned pointer object."""
    if value is None:
        return None, -1
    data = value.encode('utf-8') if isinstance(value, str) else bytes(value)
    return ctypes.create_string_buffer(data, len(data) + 1), len(data)


# The buffers of the struct fields made by span and string_input, kept for the life of the process.
_retained = []


class Span(ctypes.Structure):
    """RvDomUtf8StringSpan: a string inside a union or sequence; length -1 is a null element."""
    _fields_ = [('data', ctypes.c_void_p), ('length', ctypes.c_int32)]

    def text(self):
        return ctypes.string_at(self.data, self.length).decode('utf-8') if self.length > 0 else ('' if self.length == 0 else None)


class StringInput(ctypes.Structure):
    """RvDomUtf8StringInput: a dictionary string field; present 0 takes the field's IDL default."""
    _fields_ = [('present', ctypes.c_int32), ('data', ctypes.c_void_p), ('length', ctypes.c_int32)]


def _pointer(value):
    buffer, length = encode(value)
    if buffer is not None:
        _retained.append(buffer)
    return (None if buffer is None else ctypes.cast(buffer, ctypes.c_void_p).value), length


def span(value):
    """The Span of a str or bytes value, or of None as a null element."""
    return Span(*_pointer(value))


def string_input(value):
    """The StringInput of a str or bytes value, or of None as the field's default."""
    return StringInput(0, None, 0) if value is None else StringInput(1, *_pointer(value))


def bind(library, name, result, arguments):
    """The library's function with these argument types, each Utf8 marker taking one string value."""
    function = getattr(library, name)
    expanded = []
    for argument in arguments:
        expanded += [ctypes.c_void_p, ctypes.c_int32] if argument is Utf8 else [argument]
    function.restype, function.argtypes = result, expanded
    if Utf8 not in arguments:
        return function
    marks = [argument is Utf8 for argument in arguments]

    def call(*values):
        converted, buffers = [], []
        for marked, value in zip(marks, values):
            if marked:
                buffer, length = encode(value)
                buffers.append(buffer)
                converted += [None if buffer is None else ctypes.cast(buffer, ctypes.c_void_p), length]
            else:
                converted.append(value)
        return function(*converted)

    return call
