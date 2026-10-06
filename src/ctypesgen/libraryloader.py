import ctypes
import ctypes.util
import sys
import os.path
from pathlib import Path

class _Loader:
    
    _CONSIDER_LINK = None
    if sys.platform.startswith(("win32", "cygwin", "msys")):
        _PREFIX, _SUFFIX = "", "dll"
    elif sys.platform.startswith("darwin"):
        _PREFIX, _SUFFIX = "lib", "dylib"
    elif sys.platform.startswith("ios"):
        _PREFIX, _SUFFIX = "lib", "dylib"
        _CONSIDER_LINK = ".fwork"
    else:  # assume unix-like naming pattern
        _PREFIX, _SUFFIX = "lib", "so"
    
    @classmethod
    def _resolve_lpath(cls, lpath, name):
        if not lpath.is_absolute():
            lpath = (Path(__file__).parent / lpath).resolve(strict=False)
        lpath = lpath.parent / lpath.name.format(
            prefix=cls._PREFIX, name=name, suffix=cls._SUFFIX,
        )
        if lpath.exists():
            return lpath
        if cls._CONSIDER_LINK:
            lpath_link = lpath.with_suffix(cls._CONSIDER_LINK)
            if lpath_link.exists():
                lpath = Path(lpath_link.read_text().strip())
                if lpath.exists():
                    return lpath
    
    @classmethod
    def get_library(cls, name, dllclass, libpaths, search_sys):
        for lpath in libpaths:
            if os.path.dirname(lpath):
                lpath = cls._resolve_lpath(Path(lpath), name)
                if lpath:
                    return dllclass(str(lpath))
            else:
                try:
                    return dllclass(lpath)
                except OSError:
                    continue
        
        lpath = ctypes.util.find_library(name) if search_sys else None
        if not lpath:
            raise ImportError(f"Could not find library {name!r} (libpaths={libpaths}, search_sys={search_sys})")
        
        return dllclass(lpath)

_libs = {}
