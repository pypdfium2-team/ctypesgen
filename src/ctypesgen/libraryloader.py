import sys
import ctypes
import ctypes.util
import pathlib

if sys.platform.startswith(("win32", "cygwin", "msys")):
    _LIB_PREFIX, _LIB_SUFFIX = "", "dll"
elif sys.platform.startswith(("darwin", "ios")):
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "dylib"
else:  # assume unix pattern or plain name
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "so"

def _find_library(name, libpaths, search_sys):
    
    for lpath in libpaths:
        lpath = pathlib.Path(lpath)
        if not lpath.is_absolute():
            lpath = (pathlib.Path(__file__).parent / lpath).resolve(strict=False)
        lpath = lpath.parent / lpath.name.format(prefix=_LIB_PREFIX, name=name, suffix=_LIB_SUFFIX)
        if lpath.is_file():  # XXX
            return lpath
    
    lpath = ctypes.util.find_library(name) if search_sys else None
    if not lpath:
        raise ImportError(f"Could not find library '{name}' (libpaths={libpaths}, search_sys={search_sys})")
    
    return lpath

_libs_info, _libs = {}, {}

def _register_library(name, dllclass, **kwargs):
    libpath = _find_library(name, **kwargs)
    _libs_info[name] = {**kwargs, "path": libpath}
    _libs[name] = dllclass(libpath)
