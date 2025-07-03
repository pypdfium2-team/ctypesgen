import sys
import ctypes
import ctypes.util
import pathlib

def _find_library(name, libpaths, search_sys):
    
    if sys.platform.startswith(("win32", "cygwin", "msys")):
        prefix, suffix = "", "dll"
    elif sys.platform.startswith(("darwin", "ios")):
        prefix, suffix = "lib", "dylib"
    else:  # assume unix pattern or plain name
        prefix, suffix = "lib", "so"
    
    for lpath in libpaths:
        lpath = pathlib.Path(lpath)
        if not lpath.is_absolute():
            lpath = (pathlib.Path(__file__).parent / lpath).resolve(strict=False)
        lpath = lpath.parent / lpath.name.format(prefix=prefix, name=name, suffix=suffix)
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
