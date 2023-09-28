import sys
import ctypes
import ctypes.util
from pathlib import Path


def _find_library(libname, libdirs):
    
    if not libdirs:
        return ctypes.util.find_library(libname)
    
    if sys.platform in ("win32", "cygwin", "msys"):
        patterns = ["{}.dll", "lib{}.dll", "{}"]
    elif sys.platform == "darwin":
        patterns = ["lib{}.dylib", "{}.dylib", "lib{}.so", "{}.so", "{}"]
    else:  # assume unix pattern or plain libname
        patterns = ["lib{}.so", "{}.so", "{}"]
    
    RELDIR = Path(__file__).parent
    
    for dir in libdirs:
        # joining an absolute path silently discardy the path before
        dir = (RELDIR / dir).resolve(strict=False)
        for pat in patterns:
            test_path = dir / pat.format(libname)
            if test_path.is_file():
                return str(test_path)


def load_library(libname, libdirs):
    
    libpath = _find_library(libname, libdirs)
    if not libpath:
        raise RuntimeError(f"Library '{libname}' could not be found in {libdirs if libdirs else 'system'}.")
    
    return ctypes.CDLL(libpath)
