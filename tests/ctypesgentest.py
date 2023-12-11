"""ctypesgentest is a simple module for testing ctypesgen on various C constructs.

It consists of a single function, test(). test() takes a string that represents
a C header file, along with some keyword arguments representing options. It
processes the header using ctypesgen and returns a tuple containing the
resulting module object and the output that ctypesgen produced.
"""

import os
import sys
import glob
import json
import types
import subprocess
import shutil
from itertools import product
import tempfile
from pathlib import Path

import ctypesgen.__main__
from ctypesgen import messages, VERSION


TEST_DIR = Path(__file__).resolve().parent
COMMON_DIR = TEST_DIR/"common"


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
    
    tmp_header = tempfile.NamedTemporaryFile()
    tmp_header.write(header_str.encode())
    tmp_header.seek(0)
    tmp_out = tempfile.NamedTemporaryFile()
    ctypesgen_main(["-i", tmp_header.name, "-o", tmp_out.name, "--output-language", lang, *args])
    
    tmp_header_name = tmp_header.name
    tmp_header.close()
    tmp_out.seek(0)
    content = tmp_out.read().decode()
    tmp_out.close()
    
    if lang.startswith("py"):
        return module_from_code("tmp_module", content)
    elif lang == "json":
        return json.loads(content), tmp_header_name
    else:
        assert False


def cleanup(filepattern="temp.*"):
    fnames = glob.glob(filepattern)
    for fname in fnames:
        os.unlink(fname)


def set_logging_level(log_level):
    messages.log.setLevel(log_level)


def ctypesgen_version():
    return VERSION


def sort_anon_fn(anon_tag):
    return int(anon_tag.split("_")[1])


class JsonHelper:
    """
    Utility class preparing generated JSON result for testing.

    JSON stores the path to some source items. These need to be genericized in
    order for tests to succeed on all machines/user accounts. This is also the
    case for "anon_" tags, which are "reset" for each test to start from
    "anon_1".
    """

    def __init__(self):
        self.anons = list()

    def prepare(self, json):
        """Prepares generated JSON result for testing"""
        self._search_anon_tags(json)
        unique_list = list(set(self.anons))
        unique_sorted_list = sorted(unique_list, key=sort_anon_fn)

        mapped_tags = dict()
        counter = 1
        for i in unique_sorted_list:
            mapped_tags[i] = "anon_{0}".format(counter)
            counter += 1

        for (old_tag, new_tag) in mapped_tags.items():
            self._replace_anon_tag(json, old_tag, new_tag)

    def _replace_anon_tag(self, json, tag, new_tag):
        """Replaces source paths and resets anon_ tags to increment from 1"""
        if isinstance(json, list):
            for item in json:
                self._replace_anon_tag(item, tag, new_tag)
            return
        if isinstance(json, dict):
            for key, value in json.items():
                if key == "name" and isinstance(value, str):
                    if value == tag:
                        json[key] = new_tag
                elif key == "tag" and isinstance(value, str):
                    if value == tag:
                        json[key] = new_tag
                elif key == "src" and isinstance(value, list):
                    if value and "temp.h" in value[0]:
                        value[0] = "/some-path/temp.h"
                else:
                    self._replace_anon_tag(value, tag, new_tag)

    def _search_anon_tags(self, json):
        """Search for anon_ tags"""
        if isinstance(json, list):
            for item in json:
                self._search_anon_tags(item)
            return
        if isinstance(json, dict):
            for key, value in json.items():
                if key == "name" and isinstance(value, str):
                    if value.startswith("anon_"):
                        self.anons.append(value)
                else:
                    self._search_anon_tags(value)


# -- Functions facilitating tests of use of cross inclusion --


def generate_common():
    common_lib = "libcommon.dll" if sys.platform == "win32" else "libcommon.so"
    _create_common_files()
    _compile_common(common_lib)
    
    ctypesgen_main(["-i", COMMON_DIR/"common.h", "--no-embed-preamble", "-o", COMMON_DIR/"common.py"])
    for file_name, shared in product(["a", "b"], [False, True]):
        _generate_common(file_name, shared)


def cleanup_common():
    # Attention: currently not working on MS Windows.
    # cleanup_common() tries to delete "common.dll" while it is still loaded
    # by ctypes. See unittest for further details.
    shutil.rmtree(COMMON_DIR)


def _compile_common(common_lib):
    subprocess.run(["gcc", "-c", COMMON_DIR/"a.c", "-o", COMMON_DIR/"a.o"])
    subprocess.run(["gcc", "-c", COMMON_DIR/"b.c", "-o", COMMON_DIR/"b.o"])
    subprocess.run(["gcc", "-shared", "-o", COMMON_DIR/common_lib, COMMON_DIR/"a.o", COMMON_DIR/"b.o"])


def _generate_common(file_name, shared):
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

    try:
        COMMON_DIR.mkdir()
    except FileExistsError:
        shutil.rmtree(COMMON_DIR)
        COMMON_DIR.mkdir()

    for (name, source) in names.items():
        with (COMMON_DIR/name).open("w") as f:
            f.write(source)
