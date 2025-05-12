# Note: these templates take it for granted that ctypes is imported already.

T_UNCHECKED = """\
# AOTW, ctypes does not support non-primitive result types in callbacks,
# so we remap custom pointer types to unchecked c_void_p.
def UNCHECKED(t):
    if hasattr(t, "_type_") and not isinstance(t._type_, str):
        return ctypes.c_void_p
    else:
        return t\
"""
