# TODO
# - add c_ptrdiff_t and _variadic_function only on an as-needed basis
# - check if we can remove the _variadic_function wrapper entirely and use plain ctypes instead
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


class _variadic_function(object):
    def __init__(self, func, restype, argtypes, errcheck):
        self.func = func
        self.func.restype = restype
        self.argtypes = argtypes
        if errcheck:
            self.func.errcheck = errcheck

    def _as_parameter_(self):
        # So we can pass this variadic function as a function pointer
        return self.func

    def __call__(self, *args):
        fixed_args = []
        i = 0
        for argtype in self.argtypes:
            # Typecheck what we can
            fixed_args.append(argtype.from_param(args[i]))
            i += 1
        return self.func(*fixed_args + list(args[i:]))
