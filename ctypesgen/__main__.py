"""
Command-line interface for ctypesgen
"""

import re
import sys
import shlex
import shutil
import importlib
import contextlib
import argparse
import itertools
from pathlib import Path

from ctypesgen import (
    messages as msgs,
    parser as core_parser,
    processor,
    version,
    printer_python,
    printer_json,
)


@contextlib.contextmanager
def tmp_searchpath(path):
    path = str(path)
    sys.path.insert(0, path)
    try:
        yield
    finally:
        popped = sys.path.pop(0)
        assert popped is path


def find_symbols_in_modules(modnames, outpath):
    
    symbols = set()
    
    for modname in modnames:
        
        if modname.startswith("."):
            # NOTE(geisserml) Concerning relative imports, I've been unable to find another way than adding the output dir's parent to sys.path, given that the module itself may contain relative imports.
            # It seems like this may be a limitation of python's import system, though technically one would imagine the output dir's path itself should be sufficient.
            anchor_dir = outpath.parent
            with tmp_searchpath(anchor_dir.parent):
                module = importlib.import_module(modname, anchor_dir.name)
        else:
            module = importlib.import_module(modname)
        
        module_syms = [s for s in dir(module) if not re.fullmatch(r"__\w+__", s)]
        assert len(module_syms) > 0, "Linked modules must provide symbols"
        msgs.status_message(f"Found symbols {module_syms} in module {module}")
        symbols.update(module_syms)
    
    return symbols


# FIXME argparse parameters are not ordered consistently...
# TODO consider BooleanOptionalAction (with compat backport)
def main(given_argv=sys.argv[1:]):
    
    parser = argparse.ArgumentParser(prog="ctypesgen")
    
    if sys.version_info < (3, 8):  # compat
        
        class ExtendAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                items = getattr(namespace, self.dest) or []
                items.extend(values)
                setattr(namespace, self.dest, items)
        
        parser.register('action', 'extend', ExtendAction)
    
    # Version
    parser.add_argument(
        "--version",
        action="version",
        version=version.VERSION_NUMBER,
    )

    # Parameters
    parser.add_argument(
        # do not add --include for a migration period because this previously did what is now called --system-headers
        "-i", "--headers",
        dest="headers",
        nargs="+",
        action="extend",
        type=lambda p: Path(p).resolve(),
        default=[],
        help="Sequence of header files",
    )
    parser.add_argument(
        "-l", "--library",
        metavar="LIBRARY",
        help="Link to LIBRARY",
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        metavar="FILE",
        help="Write bindings to FILE",
    )
    parser.add_argument(
        "--system-headers",
        nargs="+",
        action="extend",
        default=[],
        metavar="HEADER",
        # pypdfium2-team change: eagerly include members
        help="Include and bind against members from system header HEADER, with '.h' suffix (e.g. stdio.h, stdlib.h, python3.X/Python.h). Will be translated to a <...> style include and passed to the pre-processor. Provided for portability. If the full path is known, it may be preferable to use the regular --headers option.",
    )
    parser.add_argument(
        "-m", "--modules",
        "--link-modules",
        dest="modules",
        nargs="+",
        action="extend",
        default=[],
        metavar="MODULE",
        help="Use symbols from python module MODULE. If prefixed with '.', the import is interpreted relative to the output dir. Otherwise, we import from installed packages. (Note, in case of a relative import, the output dir's parent is temporarily added to PYTHONPATH due to import system limitations, so you'll want to make sure there are no conflicts.)",
    )
    parser.add_argument(
        "-I", "--includedirs",
        dest="include_search_paths",
        nargs="+",
        action="extend",
        default=[],
        metavar="INCLUDEDIR",
        help="add INCLUDEDIR as a directory to search for headers",
    )
    parser.add_argument(
        "-L", "--universal-libdirs",
        nargs="+",
        action="extend",
        default=[],
        metavar="LIBDIR",
        help="Add LIBDIR to the search path (both compile-time and run-time)",
    )
    parser.add_argument(
        "--compile-libdirs",
        nargs="+",
        action="extend",
        default=[],
        metavar="LIBDIR",
        help="Add LIBDIR to the compile-time library search path.",
    )
    parser.add_argument(
        "--runtime-libdirs",
        nargs="+",
        action="extend",
        default=[],
        metavar="LIBDIR",
        help="Add LIBDIR to the run-time library search path.",
    )
    parser.add_argument(
        "--no-system-libsearch",
        action="store_false",
        dest="search_sys",
        help="Deactivate fallback system library search; mandate that the library be contained in the given libdirs instead."
    )
    parser.add_argument(
        "--no-embed-preamble",
        action="store_false",
        dest="embed_preamble",
        help="Do not embed preamble and loader in output file. Defining --output-language to Python is a prerequisite.",
    )

    # Parser options
    parser.add_argument(
        "--cpp",
        help="The command to invoke the C preprocessor, including any necessary options. By default, we try to find a supported preprocessor automatically. Example: to always use clang, pass --cpp \"clang -E\". (In a shell env, note the quotes for the arguments to end up in the right parser. Nested quotes in the command are also honored.)",
    )
    parser.add_argument(
        "--allow-gnu-c",
        action="store_true",
        dest="allow_gnu_c",
        help="Specify whether to undefine the '__GNUC__' macro, while invoking the C preprocessor. (default: False. i.e. ctypesgen adds an implicit undefine using '-U __GNUC__'.) Specify this flag to avoid ctypesgen undefining '__GNUC__' as shown above.",
    )
    parser.add_argument(
        "-D", "--define",
        dest="cppargs",
        type=lambda n: ("-D", n),
        nargs="+",
        action="extend",
        default=[],
        metavar="NAME",
        help="Add a definition to the preprocessor via commandline",
    )
    parser.add_argument(
        "-U", "--undefine",
        dest="cppargs",
        type=lambda n: ("-U", n),
        nargs="+",
        action="extend",
        default=[],
        metavar="NAME",
        help="Instruct the preprocessor to undefine the specified macro via commandline",
    )
    parser.add_argument(
        "--preproc-savepath",
        metavar="FILENAME",
        help="Save preprocessor output to the specified FILENAME",
    )
    parser.add_argument(
        "--optimize-lexer",
        action="store_true",
        help="Run the lexer in optimized mode. This mode requires write "
        "access to lextab.py file stored within the ctypesgen package.",
    )

    # Processor options
    parser.add_argument(
        "-a", "--all-headers",
        action="store_true",
        help="include symbols from all headers, including system headers",
    )
    parser.add_argument(
        "--builtin-symbols",
        action="store_true",
        help="include symbols automatically generated by the preprocessor",
    )
    parser.add_argument(
        "--no-macros",
        action="store_false",
        dest="include_macros",
        help="Don't output macros. May be overridden selectively by --symbol-rules.",
    )
    parser.add_argument(
        "--no-undefs",
        action="store_false",
        dest="include_undefs",
        help="Do not remove macro definitions as per #undef directives",
    )
    parser.add_argument(
        "--symbol-rules",
        nargs="+",
        action="extend",
        default=[],
        help="Sequence of symbol inclusion rules of format RULE=exp1|exp2|..., where RULE is one of [never, if_needed, yes], followed by a python fullmatch regular expression (multiple REs may be concatenated using the vertical line char). Will be applied in order from left to right, after dependency resolution.",
    )
    parser.add_argument(
        "--no-stddef-types",
        action="store_true",
        help="Do not support extra C types from stddef.h",
    )
    parser.add_argument(
        "--no-gnu-types",
        action="store_true",
        help="Do not support extra GNU C types",
    )
    parser.add_argument(
        "--no-python-types",
        action="store_true",
        help="Do not support extra C types built in to Python",
    )
    # TODO turn into dest="load_library" and "store_false" ?
    parser.add_argument(
        "--no-load-library",
        action="store_true",
        help="Do not try to load library during the processing"
    )

    # Printer options
    parser.add_argument(
        "--insert-files",
        dest="inserted_files",
        nargs="+",
        action="extend",
        default=[],
        metavar="FILENAME",
        help="Add the contents of FILENAME to the end of the wrapper file.",
    )
    parser.add_argument(
        "--output-language",
        metavar="LANGUAGE",
        default="py",
        choices=("py", "json"),
        help="Choose output language",
    )
    # TODO add direct support for ctypes.pythonapi
    parser.add_argument(
        "--dllclass",
        default="CDLL",
        choices=("CDLL", "WinDLL", "OleDLL", "PyDLL"),
        help="The ctypes library class to use. 'CDLL' corresponds to the 'cdecl' calling convention, 'WinDLL' to windows-only 'stdcall'. We do not currently support libraries with mixed calling convention.",
    )
    parser.add_argument(
        "--no-symbol-guards",
        dest="guard_symbols",
        action="store_false",
        help="Do not add hasattr(_lib, ...) if-guards. Use when input headers and runtime binary are guaranteed to match. Note, if the library was loaded and missing symbols were determined, these would still be guarded selectively, if included.",
    )
    parser.add_argument(
        "--no-macro-guards",
        dest="guard_macros",
        action="store_false",
        help="Do not wrap macros in try/except.",
    )

    # Error options
    parser.add_argument(
        "--all-errors",
        action="store_true",
        dest="show_all_errors",
        help="Display all warnings and errors even if they would not affect output.",
    )
    parser.add_argument(
        "--show-long-errors",
        action="store_true",
        help="Display long error messages instead of abbreviating error messages.",
    )
    parser.add_argument(
        "--no-macro-warnings",
        action="store_false",
        dest="show_macro_warnings",
        help="Do not print macro warnings.",
    )
    parser.add_argument(
        "--debug-level",
        default=0,
        type=int,
        help="Run ctypesgen with specified debug level (also applies to yacc parser)",
    )
    
    args = parser.parse_args(given_argv)
    
    if not (args.headers or args.system_headers):
        raise ValueError("Either --headers or --system-headers required.")
    
    if args.cpp:
        # split while preserving quotes
        args.cpp = shlex.split(args.cpp)
    else:
        if shutil.which("gcc"):
            args.cpp = ["gcc", "-E"]
        elif shutil.which("cpp"):
            args.cpp = ["cpp"]
        elif shutil.which("clang"):
            args.cpp = ["clang", "-E"]
        else:
            raise RuntimeError("C pre-processor auto-detection failed: neither gcc nor clang available.")
    
    args.cppargs = list( itertools.chain(*args.cppargs) )
    
    # important: must not use +=, this would mutate the original object, which is problematic when calling ctypesgen natively from the python API
    args.compile_libdirs = args.compile_libdirs + args.universal_libdirs
    args.runtime_libdirs = args.runtime_libdirs + args.universal_libdirs
    
    # Figure out what names will be defined by imported Python modules
    args.linked_symbols = find_symbols_in_modules(args.modules, Path(args.output).resolve())
    
    printer = {"py": printer_python, "json": printer_json}[args.output_language].WrapperPrinter
    descs = core_parser.parse(args.headers, args)
    processor.process(descs, args)
    data = [(k, d) for k, d in descs.output_order if d.included]
    if not data:
        raise RuntimeError("No target members found.")
    printer(args.output, args, data, given_argv)
    
    msgs.status_message("Wrapping complete.")
    


if __name__ == "__main__":
    main()
