# TODO
# - add c_ptrdiff_t only on as-needed basis
# - Avoid ctypes glob import (pollutes namespace)

import ctypes
from ctypes import *  # noqa: F401, F403

def _get_ptrdiff_t():

    int_types = (ctypes.c_int16, ctypes.c_int32)
    if hasattr(ctypes, "c_int64"):
        # Some builds of ctypes apparently do not have ctypes.c_int64
        # defined; it's a pretty good bet that these builds do not
        # have 64-bit pointers.
        int_types += (ctypes.c_int64,)

    c_ptrdiff_t = None
    for t in int_types:
        if ctypes.sizeof(t) == ctypes.sizeof(ctypes.c_size_t):
            c_ptrdiff_t = t

    return c_ptrdiff_t

c_ptrdiff_t = _get_ptrdiff_t()


def PRIMITIVE(type):
    if hasattr(type, "_type_") and isinstance(type._type_, str) and type._type_ != "P":
        return type
    else:
        return ctypes.c_void_p
