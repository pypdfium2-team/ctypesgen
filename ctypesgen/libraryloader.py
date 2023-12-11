import sys
import ctypes
import ctypes.util
import warnings
import pathlib

def _find_library(name, dirs, search_sys, reldir=None):
    
    if sys.platform in ("win32", "cygwin", "msys"):
        patterns = ["{}.dll", "lib{}.dll", "{}"]
    elif sys.platform == "darwin":
        patterns = ["lib{}.dylib", "{}.dylib", "lib{}.so", "{}.so", "{}"]
    else:  # assume unix pattern or plain name
        patterns = ["lib{}.so", "{}.so", "{}"]
    
    if not reldir:
        try:
            reldir = pathlib.Path(__file__).parent
        except NameError as e:
            # Issue a warning if unable to determine the containing directory. After this, it's OK to just fail with NameError below if actually attempting to resolve a relative path.
            assert e.name == "__file__"
            warnings.warn("Bindings not stored as file, will be unable to resolve relative dirs")
    
    for dir in dirs:
        dir = pathlib.Path(dir)
        if not dir.is_absolute():
            # note, joining an absolute path silently discardy the path before
            dir = (reldir/dir).resolve(strict=False)
        for pat in patterns:
            libpath = dir / pat.format(name)
            if libpath.is_file():
                return str(libpath)
    
    if search_sys:
        if dirs:
            warnings.warn(f"Could not find library '{name}' in {dirs}, falling back to system")
        libpath = ctypes.util.find_library(name)
        if not libpath:
            raise ImportError(f"Could not find library '{name}' in system")
        return libpath
    else:
        raise ImportError(f"Could not find library '{name}' in {dirs} (system search disabled)")

_libs_info, _libs = {}, {}

def _register_library(name, dllclass, **kwargs):
    libpath = _find_library(name, **kwargs)
    assert libpath, "output expected from _find_library()"
    _libs_info[name] = {"name": name, "dllclass": dllclass, **kwargs, "path": libpath}
    return dllclass(libpath)
