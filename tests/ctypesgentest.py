"""ctypesgentest is a simple module for testing ctypesgen on various C constructs.

It consists of a single function, test(). test() takes a string that represents
a C header file, along with some keyword arguments representing options. It
processes the header using ctypesgen and returns a tuple containing the
resulting module object and the output that ctypesgen produced.
"""

import os
import sys
from io import StringIO
import glob
import json
from contextlib import contextmanager
import types
import subprocess
from shutil import rmtree
from itertools import product
from pathlib import Path

from ctypesgen.__main__ import main as ctypesgen_main
from ctypesgen import options, messages, parser, processor
from ctypesgen import printer_python, printer_json, VERSION


# TODO migrate test suite to pathlib.Path type

TEST_DIR = str(Path(__file__).resolve().parent)


module_factory = types.ModuleType

# set redirect_stdout to False if using console based debugger like pdb
redirect_stdout = True


@contextmanager
def redirect(stdout=sys.stdout):
    backup = sys.stdout
    sys.stdout = stdout
    try:
        yield stdout
    finally:
        sys.stdout = backup

# TODO(geisserml) migrate generate() to actual package CLI

def generate(header, **more_options):

    assert isinstance(header, str)
    with open("temp.h", "wb") as f:
        f.write(header.encode('utf-8'))

    test_options = options.get_default_options()
    test_options.headers = ["temp.h"]
    for opt, val in more_options.items():
        setattr(test_options, opt, val)

    if redirect_stdout:
        # Redirect output
        sys.stdout = StringIO()

    # Step 1: Parse
    descriptions = parser.parse(test_options.headers, test_options)

    # Step 2: Process
    processor.process(descriptions, test_options)

    # Step 3: Print
    if test_options.output_language.startswith("py"):

        def module_from_code(name, python_code):
            module = module_factory(name)
            exec(python_code, module.__dict__)
            return module

        # we have to redirect stdout, as WrapperPrinter is only able to write
        # to files or stdout
        with redirect(stdout=StringIO()) as printer_output:
            # do not discard WrapperPrinter object, as the target file gets
            # closed on printer deletion
            _ = printer_python.WrapperPrinter(None, test_options, descriptions)
            generated_python_code = printer_output.getvalue()
            module = module_from_code("temp", generated_python_code)
            retval = module

    elif test_options.output_language == "json":
        with redirect(stdout=StringIO()) as printer_output:
            # do not discard WrapperPrinter object, as the target file gets
            # closed on printer deletion
            _ = printer_json.WrapperPrinter(None, test_options, descriptions)
            JSON = json.loads(printer_output.getvalue())
            retval = JSON
    else:
        raise RuntimeError("No such output language `" + test_options.output_language + "'")

    if redirect_stdout:
        # Un-redirect output
        output = sys.stdout.getvalue()
        sys.stdout.close()
        sys.stdout = sys.__stdout__
    else:
        output = ""

    return retval, output


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

COMMON_DIR = str(Path(TEST_DIR)/"common")
COMMON_RELATIVE_PKG = str(Path(COMMON_DIR).relative_to(Path.cwd())).replace(os.path.sep, ".")


def generate_common():
    common_lib = "libcommon.dll" if sys.platform == "win32" else "libcommon.so"
    _create_common_files()
    _compile_common(common_lib)
    
    ctypesgen_main(["-i", f"{COMMON_DIR}/common.h", "--no-embed-preamble", "-o", f"{COMMON_DIR}/common.py"])
    for file_name, shared in product(["a", "b"], [False, True]):
        _generate_common(file_name, shared)


def cleanup_common():
    # Attention: currently not working on MS Windows.
    # cleanup_common() tries to delete "common.dll" while it is still loaded
    # by ctypes. See unittest for further details.
    # rmtree(COMMON_DIR)  # XXX commented out for testing
    pass


def _compile_common(common_lib):
    subprocess.run(["gcc", "-c", f"{COMMON_DIR}/a.c", "-o", f"{COMMON_DIR}/a.o"])
    subprocess.run(["gcc", "-c", f"{COMMON_DIR}/b.c", "-o", f"{COMMON_DIR}/b.o"])
    subprocess.run(["gcc", "-shared", "-o", f"{COMMON_DIR}/{common_lib}", f"{COMMON_DIR}/a.o", f"{COMMON_DIR}/b.o"])


def _generate_common(file_name, shared):
    args = ["-i", f"{COMMON_DIR}/{file_name}.h", "-I", COMMON_DIR, "-l", "common", "-L", COMMON_DIR]
    if shared:
        file_name += "_shared"
        args += ["-m", f"{COMMON_RELATIVE_PKG}/.common", "--no-embed-preamble"]
    else:
        # manually add the `mystruct` symbol (alias to ctypesgen auxiliary symbol struct_mystruct), which is not taken over by default with indirect header inclusion
        args += ["--include-extra-symbols", "mystruct"]
        file_name += "_unshared"
    args += ["-o", f"{COMMON_DIR}/{file_name}.py"]
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
        os.mkdir(COMMON_DIR)
    except FileExistsError:
        rmtree(COMMON_DIR)
        os.mkdir(COMMON_DIR)

    for (name, source) in names.items():
        with open(f"{COMMON_DIR}/{name}", "w") as f:
            f.write(source)
