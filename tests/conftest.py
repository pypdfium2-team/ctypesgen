import os
import sys
import json
import atexit
import types
import shlex
import shutil
import subprocess
from itertools import product
from pathlib import Path

import ctypesgen.__main__


TEST_DIR = Path(__file__).resolve().parent
CTYPESGEN_DIR = TEST_DIR.parent
COMMON_DIR = TEST_DIR/"common"
TMP_DIR = TEST_DIR/"tmp"

CLEANUP_OK = bool(int(os.environ.get("CLEANUP_OK", "1")))
MAIN_CPP = os.environ.get("CPP", None)

CTG_LIBPATTERN = "{prefix}{name}.{suffix}"

if sys.platform.startswith(("win32", "cygwin", "msys")):
    LIB_PREFIX, LIB_SUFFIX = "", "dll"
elif sys.platform.startswith(("darwin", "ios")):
    LIB_PREFIX, LIB_SUFFIX = "lib", "dylib"
else:  # assume unix pattern or plain name
    LIB_PREFIX, LIB_SUFFIX = "lib", "so"


def _remove_tmpdir():
    if TMP_DIR.exists(): shutil.rmtree(TMP_DIR)

def _init_tmpdir():
    _remove_tmpdir()
    TMP_DIR.mkdir()

_init_tmpdir()
if CLEANUP_OK: atexit.register(_remove_tmpdir)


def ctypesgen_wrapper(args, echo=True):
    args = [str(a) for a in args]
    if echo:
        str_args = ' '.join([shlex.quote(a) for a in ["ctypesgen", *args]])
        print(str_args, file=sys.stderr)
    return ctypesgen.__main__.main(args)

def module_from_code(name, python_code, spoof_dir=None):
    if spoof_dir:
        file_spoof = f"__file__ = {str(spoof_dir/'spoof.py')!r}\n\n"
        python_code = file_spoof + python_code
    module = types.ModuleType(name)
    exec(python_code, module.__dict__)
    return module


COUNTER = 0

def generate(header=None, args=(), lang="py", cpp=MAIN_CPP, allow_gnuc=False, spoof_dir=None):
    
    # Windows notes:
    # - Avoid stdlib tempfiles, they're not usable by anyone except the direct creator, otherwise you'll get permission errors.
    # - The default file encoding seems to be cp1252, which is problematic with special chars (such as the banana in the constants test). Need to specify UTF-8 explicitly. PEP 686 should hopefully improve this.
    
    # Use custom tempfiles scoping so we may retain data for inspection
    # FIXME can cause confusion with partial test suite runs - static naming by test case would be better, including more descriptive
    global COUNTER; COUNTER += 1
    
    cmdargs = []
    tmp_in = None
    if header != None:
        tmp_in = TMP_DIR/f"in_header_{COUNTER:02d}.h"
        tmp_in.write_text(header.strip() + "\n", encoding="utf-8")
        cmdargs += ["-i", tmp_in]
    
    if cpp: cmdargs += ["--cpp", cpp]
    if allow_gnuc: cmdargs += ["-X", "__GNUC__"]
    cmdargs += ["--output-language", lang, *args]
    
    try:
        tmp_out = TMP_DIR/f"out_bindings_{COUNTER:02d}.{lang}"
        cmdargs += ["-o", tmp_out]
        ctypesgen_wrapper(cmdargs)
        content = tmp_out.read_text(encoding="utf-8")
    finally:
        if CLEANUP_OK:
            if tmp_in: tmp_in.unlink()
            tmp_out.unlink()
    
    if lang.startswith("py"):
        return module_from_code("tmp_module", content, spoof_dir)
    elif lang == "json":
        return json.loads(content), str(tmp_in)
    else:
        assert False


def generate_common():
    common_lib = CTG_LIBPATTERN.format(prefix=LIB_PREFIX, name="common", suffix=LIB_SUFFIX)
    _create_common_files()
    _compile_common(common_lib)
    
    ctypesgen_wrapper(["-i", COMMON_DIR/"common.h", "--no-embed-templates", "--linkage-anchor", COMMON_DIR, "-o", COMMON_DIR/"common.py"])
    for file_name, shared in product(["a", "b"], [False, True]):
        _generate_with_common(file_name, shared)


def _create_common_files():
    names = {}
    names["common.h"] = """\
struct mystruct {
    int a;
};
"""
    
    names["a.h"] = """\
#include "common.h"\n
void foo(struct mystruct *m);
"""
    names["a.c"] = """\
#include "a.h"\n
void foo(struct mystruct *m) { }
"""
    names["b.h"] = """\
#include "common.h"\n
void bar(struct mystruct *m);
"""
    names["b.c"] = """\
#include "b.h"\n
void bar(struct mystruct *m) { }
"""

    if COMMON_DIR.exists(): shutil.rmtree(COMMON_DIR)
    COMMON_DIR.mkdir()

    for name, source in names.items():
        (COMMON_DIR/name).write_text(source)


def _compile_common(common_lib):
    subprocess.run(["gcc", "-c", COMMON_DIR/"a.c", "-o", COMMON_DIR/"a.o"])
    subprocess.run(["gcc", "-c", COMMON_DIR/"b.c", "-o", COMMON_DIR/"b.o"])
    subprocess.run(["gcc", "-shared", "-o", COMMON_DIR/common_lib, COMMON_DIR/"a.o", COMMON_DIR/"b.o"])


def _generate_with_common(file_name, shared):
    args = ["-i", COMMON_DIR/f"{file_name}.h", "-I", COMMON_DIR, "-l", "common", "-L", COMMON_DIR/CTG_LIBPATTERN]
    if shared:
        file_name += "_shared"
        args += ["-m", ".common", "--no-embed-templates", "--linkage-anchor", COMMON_DIR]
    else:
        # manually add the `mystruct` symbol (alias to ctypesgen auxiliary symbol struct_mystruct), which is not taken over by default with indirect header inclusion
        # the alternative would be to eagerly include all members from common.h by adding it to the input headers, i.e. args += ["-i", COMMON_DIR/"common.h"]
        args += ["--symbol-rules", "yes=mystruct"]
        file_name += "_unshared"
    args += ["-o", COMMON_DIR/f"{file_name}.py"]
    ctypesgen_wrapper(args)


def cleanup_common():
    if CLEANUP_OK: shutil.rmtree(COMMON_DIR)
