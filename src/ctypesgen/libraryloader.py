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

def _get_library(name, dllclass, libpaths, search_sys):
    
    for lpath in libpaths:
        if os.path.dirname(lpath):
            lpath = pathlib.Path(lpath)
            if not lpath.is_absolute():
                lpath = (pathlib.Path(__file__).parent / lpath).resolve(strict=False)
            lpath = lpath.parent / lpath.name.format(prefix=_LIB_PREFIX, name=name, suffix=_LIB_SUFFIX)
            if lpath.exists():
                return dllclass(lpath)
        else:
            try:
                return dllclass(lpath)
            except OSError:
                pass
    
    lpath = ctypes.util.find_library(name) if search_sys else None
    if not lpath:
        raise ImportError(f"Could not find library {name!r} (libpaths={libpaths}, search_sys={search_sys})")
    
    return dllclass(lpath)

_libs = {}
