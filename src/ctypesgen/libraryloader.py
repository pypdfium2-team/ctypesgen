import sys
import ctypes
import ctypes.util
import os.path
import pathlib

if sys.platform.startswith(("win32", "cygwin", "msys")):
    _LIB_PREFIX, _LIB_SUFFIX = "", "dll"
elif sys.platform.startswith(("darwin", "ios")):
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "dylib"
else:  # assume unix pattern or plain name
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "so"

def _find_library(name, dllclass, libpaths, search_sys):
    
    for lpath_str in libpaths:
        lpath = pathlib.Path(lpath_str)
        have_parent = bool(os.path.dirname(lpath_str))
        if (not lpath.is_absolute()) and have_parent:
            lpath = (pathlib.Path(__file__).parent / lpath).resolve(strict=False)
        if have_parent:
            lpath = lpath.parent / lpath.name.format(prefix=_LIB_PREFIX, name=name, suffix=_LIB_SUFFIX)
        try:
            return dllclass(lpath), lpath
        except OSError:
            pass
    
    lpath = ctypes.util.find_library(name) if search_sys else None
    if not lpath:
        raise ImportError(f"Could not find library {name!r} (libpaths={libpaths}, search_sys={search_sys})")
    
    return dllclass(lpath), lpath

_libs_info, _libs = {}, {}

def _register_library(name, dllclass, **kwargs):
    dll, lpath = _find_library(name, dllclass, **kwargs)
    _libs[name] = dll
    _libs_info[name] = {**kwargs, "path": lpath}
