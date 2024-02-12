import sys
import ctypes
import ctypes.util
import pathlib

def _find_library(name, dirs, search_sys):
    
    if sys.platform in ("win32", "cygwin", "msys"):
        patterns = ["{}.dll", "lib{}.dll", "{}"]
    elif sys.platform == "darwin":
        patterns = ["lib{}.dylib", "{}.dylib", "lib{}.so", "{}.so", "{}"]
    else:  # assume unix pattern or plain name
        patterns = ["lib{}.so", "{}.so", "{}"]
    
    for dir in dirs:
        dir = pathlib.Path(dir)
        if not dir.is_absolute():
            dir = (pathlib.Path(__file__).parent / dir).resolve(strict=False)
        for pat in patterns:
            libpath = dir / pat.format(name)
            if libpath.is_file():
                return str(libpath)
    
    libpath = ctypes.util.find_library(name) if search_sys else None
    if not libpath:
        raise ImportError(f"Could not find library '{name}' (dirs={dirs}, search_sys={search_sys})")
    
    return libpath

_libs_info, _libs = {}, {}

def _register_library(name, dllclass, **kwargs):
    libpath = _find_library(name, **kwargs)
    _libs_info[name] = {**kwargs, "path": libpath}
    _libs[name] = dllclass(libpath)
