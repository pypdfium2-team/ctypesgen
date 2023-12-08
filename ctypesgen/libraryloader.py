import sys
import ctypes
import ctypes.util
import warnings
import pathlib


def _find_library(libname, libdirs, allow_system_search):
    
    if sys.platform in ("win32", "cygwin", "msys"):
        patterns = ["{}.dll", "lib{}.dll", "{}"]
    elif sys.platform == "darwin":
        patterns = ["lib{}.dylib", "{}.dylib", "lib{}.so", "{}.so", "{}"]
    else:  # assume unix pattern or plain libname
        patterns = ["lib{}.so", "{}.so", "{}"]
    
    try:
        THIS_DIR = pathlib.Path(__file__).parent
    except NameError as e:
        # Issue a warning if unable to determine the containing directory. After this, it's OK to just fail with NameError below if actually attempting to resolve a relative path.
        assert e.name == "__file__"
        warnings.warn("Bindings not stored as file, will be unable to resolve relative dirs")
    
    for dir in libdirs:
        dir = pathlib.Path(dir)
        if not dir.is_absolute():
            # note, joining an absolute path silently discardy the path before
            dir = (THIS_DIR / dir).resolve(strict=False)
        for pat in patterns:
            libpath = dir / pat.format(libname)
            if libpath.is_file():
                return str(libpath)
    
    if allow_system_search:
        if libdirs:
            warnings.warn(f"Could not find library '{libname}' in libdirs {libdirs}, falling back to system")
        libpath = ctypes.util.find_library(libname)
        if not libpath:
            raise ImportError(f"Could not find library '{libname}' in system")
        return libpath
    else:
        raise ImportError(f"Could not find library '{libname}' in libdirs {libdirs} (system search disabled)")
