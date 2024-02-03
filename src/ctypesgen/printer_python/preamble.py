import ctypes
from ctypes import *  # noqa: F401, F403

def _get_ptrdiff_t():
    int_types = [ctypes.c_int32, ctypes.c_int16]
    # Some builds of ctypes do not provide c_int64. Assumably, this means the platform doesn't have 64-bit pointers.
    if hasattr(ctypes, "c_int64"):
        int_types.insert(0, ctypes.c_int64)
    return next((t for t in int_types if sizeof(t) == sizeof(c_size_t)), None)

c_ptrdiff_t = _get_ptrdiff_t()
