import os
import sys
import json
import atexit
import types
import subprocess
import shutil
from itertools import product
from pathlib import Path

import ctypesgen.__main__


TEST_DIR = Path(__file__).resolve().parent
COMMON_DIR = TEST_DIR/"common"
TMP_DIR = TEST_DIR/"tmp"
COUNTER = 0
CLEANUP_OK = bool(int(os.environ.get("CLEANUP_OK", "1")))


def _remove_tmpdir():
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)

def _init_tmpdir():
    _remove_tmpdir()
    TMP_DIR.mkdir()

_init_tmpdir()
if CLEANUP_OK:
    atexit.register(_remove_tmpdir)


def ctypesgen_main(args):
    return ctypesgen.__main__.main([str(a) for a in args])


def module_from_code(name, python_code):
    # exec'ed modules do not have __file__, but we could define it manually as an anchor point for relative paths (commented out because no test case needs this yet)
    # file_spoof = f"__file__ = '{TEST_DIR/'spoof.py'}'\n\n"
    # python_code = file_spoof + python_code
    module = types.ModuleType(name)
    exec(python_code, module.__dict__)
    return module


def generate(header_str, args=[], lang="py"):
    
    # Windows notes:
    # - Avoid stdlib tempfiles, they're not usable by anyone except the direct creator, otherwise you'll get permission errors.
    # - The default file encoding seems to be cp1252, which is problematic with special chars (such as the banana in the constants test). Need to specify UTF-8 explicitly. PEP 686 should hopefully improve this.
    
    # Use custom tempfiles scoping so we may retain data for inspection
    # FIXME can cause confusion with partial test suite runs - static naming by test case would be better, also more descriptive
    global COUNTER
    COUNTER += 1
    
    tmp_in = TMP_DIR/f"in_header_{COUNTER:02d}.h"
    tmp_in.write_text(header_str.strip() + "\n", encoding="utf-8")
    try:
        tmp_out = TMP_DIR/f"out_bindings_{COUNTER:02d}.{lang}"
        ctypesgen_main(["-i", tmp_in, "-o", tmp_out, "--output-language", lang, *args])
        content = tmp_out.read_text(encoding="utf-8")
    finally:
        if CLEANUP_OK:
            tmp_in.unlink()
            tmp_out.unlink()
    
    if lang.startswith("py"):
        return module_from_code("tmp_module", content)
    elif lang == "json":
        return json.loads(content), str(tmp_in)
    else:
        assert False


# -- Functions facilitating tests of use of cross inclusion --


def generate_common():
    common_lib = "libcommon.dll" if sys.platform == "win32" else "libcommon.so"
    _create_common_files()
    _compile_common(common_lib)
    
    ctypesgen_main(["-i", COMMON_DIR/"common.h", "--no-embed-preamble", "-o", COMMON_DIR/"common.py"])
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

    if COMMON_DIR.exists():
        shutil.rmtree(COMMON_DIR)
    COMMON_DIR.mkdir()

    for (name, source) in names.items():
        with (COMMON_DIR/name).open("w") as f:
            f.write(source)


def _compile_common(common_lib):
    subprocess.run(["gcc", "-c", COMMON_DIR/"a.c", "-o", COMMON_DIR/"a.o"])
    subprocess.run(["gcc", "-c", COMMON_DIR/"b.c", "-o", COMMON_DIR/"b.o"])
    subprocess.run(["gcc", "-shared", "-o", COMMON_DIR/common_lib, COMMON_DIR/"a.o", COMMON_DIR/"b.o"])


def _generate_with_common(file_name, shared):
    args = ["-i", COMMON_DIR/f"{file_name}.h", "-I", COMMON_DIR, "-l", "common", "-L", COMMON_DIR]
    if shared:
        file_name += "_shared"
        args += ["-m", ".common", "--no-embed-preamble"]
    else:
        # manually add the `mystruct` symbol (alias to ctypesgen auxiliary symbol struct_mystruct), which is not taken over by default with indirect header inclusion
        args += ["--symbol-rules", "yes=mystruct"]
        file_name += "_unshared"
    args += ["-o", COMMON_DIR/f"{file_name}.py"]
    ctypesgen_main(args)


def cleanup_common():
    if CLEANUP_OK:
        shutil.rmtree(COMMON_DIR)
