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

# TODO Refactor. Consider something like this instead:
# https://github.com/ctypesgen/ctypesgen/issues/77#issuecomment-570145399

T_STRINGS = """\
import sys
import functools

if sys.version_info < (3, 8):
    def cached_property(func):
        return property( functools.lru_cache(maxsize=1)(func) )
else:
    cached_property = functools.cached_property


DEFAULT_ENCODING = {encoding!r}

class OutputString:
    
    def __init__(self, raw):
        self.raw = raw
    
    @cached_property
    def data(self):
        return self.raw.value
    
    @cached_property
    def decoded(self):
        if self.data is None:
            raise RuntimeError("Null pointer cannot be decoded")
        return self.data.decode(DEFAULT_ENCODING)
    
    def __bytes__(self):
        return self.data
    
    def __str__(self):
        return self.decoded
    
    def __getattr__(self, attr):
        return getattr(self.data, attr)
    
    def __hash__(self):
        return hash(self.data)
    
    def __eq__(self, other):
        if type(self) is type(other):
            return self is other or self.data == other.data
        elif isinstance(other, str):
            return self.decoded == other
        else:
            return self.data == other

class String (ctypes.c_char_p):
    
    @classmethod
    def _check_retval_(cls, result):
        return OutputString(result)
    
    @classmethod
    def from_param(cls, obj):
        if isinstance(obj, str):
            obj = (obj+"\\0").encode(DEFAULT_ENCODING)
        return super().from_param(obj)

# not internally used, retained for compatibility
def ReturnString(obj, func=None, arguments=None):
    return String.from_param(obj)\
"""
