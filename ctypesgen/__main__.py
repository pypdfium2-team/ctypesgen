"""
Command-line interface for ctypesgen
"""

import re
import sys
import importlib
import contextlib
import argparse
from pathlib import Path

from ctypesgen import (
    messages as msgs,
    options as core_options,
    parser as core_parser,
    processor,
    version,
)
from ctypesgen.printer_python import WrapperPrinter as PythonPrinter
from ctypesgen.printer_json import WrapperPrinter as JsonPrinter

@contextlib.contextmanager
def tmp_searchpath(path, active):
    if active:
        sys.path.insert(0, path)
        try:
            yield
        finally:
            sys.path.pop(0)
    else:
        yield
        return

def find_symbols_in_modules(modnames, outpath):
    symbols = set()
    for modname in modnames:
        include_path = str(outpath.parents[1].resolve())
        with tmp_searchpath(include_path, active=modname.startswith(".")):
            module = importlib.import_module(modname, outpath.parent.name)
        module_syms = [s for s in dir(module) if not re.fullmatch(r"__\w+__", s)]
        assert len(module_syms) > 0, "Linked modules must provide symbols"
        msgs.status_message(f"Found symbols {module_syms} in module {module}")
        symbols.update(module_syms)
    return symbols


# FIXME argparse parameters are not ordered consistently...
def main(givenargs=None):
    
    parser = argparse.ArgumentParser()
    
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
        "-i", "--include",
        "--headers",
        dest="headers",
        required=True,
        nargs="+",
        action="extend",
        default=[],
        help="Sequence of header files",
    )
    parser.add_argument(
        "-l",
        "--library",
        metavar="LIBRARY",
        help="link to LIBRARY",
    )
    parser.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="write wrapper to FILE [default stdout]",
    )
    parser.add_argument(
        "--other-headers",
        nargs="+",
        action="extend",
        default=[],
        metavar="HEADER",
        help="include system header HEADER (e.g. stdio.h or stdlib.h)",
    )
    parser.add_argument(
        "-m",
        "--modules",
        "--link-modules",
        dest="modules",
        nargs="+",
        action="extend",
        default=[],
        metavar="MODULE",
        help="Use symbols from python module MODULE. The syntax is similar to a python import: If prefixed with ., it will be interpreted relative to the output dir. Otherwise, the module will be imported from installed packages.",
    )
    parser.add_argument(
        "-I",
        "--includedirs",
        dest="include_search_paths",
        nargs="+",
        action="extend",
        default=[],
        metavar="INCLUDEDIR",
        help="add INCLUDEDIR as a directory to search for headers",
    )
    parser.add_argument(
        "-L",
        "--universal-libdirs",
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
        dest="allow_system_search",
        help="Deactivate fallback system library search; mandate that the library be contained in the given libdirs instead."
    )
    parser.add_argument(
        "--no-embed-preamble",
        action="store_false",
        dest="embed_preamble",
        help="Do not embed preamble and loader in output file. "
        "Defining --output as a file and --output-language to "
        "Python is a prerequisite.",
    )

    # Parser options
    parser.add_argument(
        # NOTE(geisserml) "cpp" is ambiguous - in this context, it does not refer to c++, but to the C pre-processor
        "--cpp",
        dest="cpp",
        default="gcc -E",
        help="The command to invoke the c preprocessor, including any "
        "necessary options (default: gcc -E)",
    )
    parser.add_argument(
        "--allow-gnu-c",
        action="store_true",
        dest="allow_gnu_c",
        help="Specify whether to undefine the '__GNUC__' macro, "
        "while invoking the C preprocessor.\n"
        "(default: False. i.e. ctypesgen adds an implicit undefine using '-U __GNUC__'.)\n"
        "Specify this flag to avoid ctypesgen undefining '__GNUC__' as shown above.",
    )
    parser.add_argument(
        "-D",
        "--define",
        nargs="+",
        action="extend",
        default=[],
        dest="cpp_defines",
        metavar="MACRO",
        help="Add a definition to the preprocessor via commandline",
    )
    parser.add_argument(
        "-U",
        "--undefine",
        nargs="+",
        action="extend",
        default=[],
        dest="cpp_undefines",
        metavar="NAME",
        help="Instruct the preprocessor to undefine the specified macro via commandline",
    )
    parser.add_argument(
        "--save-preprocessed-headers",
        metavar="FILENAME",
        dest="save_preprocessed_headers",
        help="Save the preprocessed headers to the specified FILENAME",
    )
    parser.add_argument(
        "--optimize-lexer",
        dest="optimize_lexer",
        action="store_true",
        help="Run the lexer in optimized mode.  This mode requires write "
        "access to lextab.py file stored within the ctypesgen package.",
    )

    # Processor options
    parser.add_argument(
        "-a",
        "--all-headers",
        action="store_true",
        dest="all_headers",
        help="include symbols from all headers, including system headers",
    )
    parser.add_argument(
        "--builtin-symbols",
        action="store_true",
        dest="builtin_symbols",
        help="include symbols automatically generated by the preprocessor",
    )
    parser.add_argument(
        "--no-macros",
        action="store_false",
        dest="include_macros",
        help="Don't output macros.",
    )
    parser.add_argument(
        "--no-undefs",
        action="store_false",
        dest="include_undefs",
        help="Do not remove macro definitions as per #undef directives",
    )
    # FIXME There may still be situations where these symbol filter options aren't sufficient to achieve the desired result, due to the grouped processing with pre-defined order. For full control, we'd need a way to take a chain of include/exclude and process it in given order. Also, we might need separate resets, but maybe excluding more specific patterns from a match can be handled on regex level, anyway.
    parser.add_argument(
        "--include-extra-symbols",
        nargs="+",
        action="extend",
        default=[],
        metavar="REGEXPR",
        help="Regular expression of symbols to include. This overrides the default selector, and is overridden by --exclude-symbols or --reset-symbols. Note, multiple symbols will be merged into a single expression by doing something like (e1|e2|e3). This applies to the other symbol options as well.",
    )
    parser.add_argument(
        # FIXME limited applicability (see Beware: ...)
        "--exclude-symbols",
        nargs="+",
        action="extend",
        default=[],
        metavar="REGEXPR",
        help="Regular expression of symbols to exclude. This overrides the default selector and --include-extra-symbols, and is overridden by --reset-symbols. Beware: --exclude-symbols implicitly removes any dependent symbols, without merging aliases.",
    )
    parser.add_argument(
        "--reset-symbols",
        nargs="+",
        action="extend",
        default=[],
        metavar="REGEXPR",
        help="Regular expression of symbols to reset to the default selector. Overrides --include-extra-symbols, --exclude-symbols and --no-macros."
    )
    parser.add_argument(
        "--no-stddef-types",
        action="store_true",
        dest="no_stddef_types",
        help="Do not support extra C types from stddef.h",
    )
    parser.add_argument(
        "--no-gnu-types",
        action="store_true",
        dest="no_gnu_types",
        help="Do not support extra GNU C types",
    )
    parser.add_argument(
        "--no-python-types",
        action="store_true",
        dest="no_python_types",
        help="Do not support extra C types built in to Python",
    )
    # TODO turn into dest="load_library" and "store_false"
    parser.add_argument(
        "--no-load-library",
        action="store_true",
        help="Do not try to load library during the processing"
    )
    parser.add_argument(
        "--no-missing-symbols",
        dest="include_missing_symbols",
        action="store_false",
        help="If given, exclude missing symbols from the output, as determined on library loading.",
    )

    # Printer options
    parser.add_argument(
        "--header-template",
        dest="header_template",
        metavar="TEMPLATE",
        help="Use TEMPLATE as the header template in the output file.",
    )
    parser.add_argument(
        "--strip-build-path",
        dest="strip_build_path",
        metavar="BUILD_PATH",
        help="Strip build path from header paths in the wrapper file.",
    )
    parser.add_argument(
        "--insert-files",
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
    parser.add_argument(
        "--dllclass",
        default=None,  # auto
        choices=("CDLL", "WinDLL", "OleDLL", "PyDLL"),
        help="The ctypes library class to use. 'CDLL' corresponds to the 'cdecl' calling convention, 'WinDLL' to windows-only 'stdcall'. See ctypes docs for more options. Note, this fork of ctypesgen does not currently support libraries with mixed calling convention.",
    )
    parser.add_argument(
        "--no-srcinfo",
        action="store_true",
        help="Skip comments stating where members are defined (header, line)."
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
        dest="show_long_errors",
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
        dest="debug_level",
        default=0,
        type=int,
        help="Run ctypesgen with specified debug level (also applies to yacc parser)",
    )

    parser.set_defaults(**core_options.default_values)
    args = parser.parse_args(givenargs)

    args.compile_libdirs += args.universal_libdirs
    args.runtime_libdirs += args.universal_libdirs

    # Figure out what names will be defined by imported Python modules
    args.imported_symbols = find_symbols_in_modules(args.modules, Path(args.output))
    
    printer = {"py": PythonPrinter, "json": JsonPrinter}[args.output_language]
    
    descriptions = core_parser.parse(args.headers, args)
    processor.process(descriptions, args)
    printer(args.output, args, descriptions)

    msgs.status_message("Wrapping complete.")

    if not descriptions.all:
        msgs.warning_message("There wasn't anything of use in the specified header file(s).", cls="usage")
        # Note what may be a common mistake
        if not args.all_headers:
            msgs.warning_message("Perhaps you meant to run with --all-headers to include objects from included sub-headers?", cls="usage")


if __name__ == "__main__":
    main()
