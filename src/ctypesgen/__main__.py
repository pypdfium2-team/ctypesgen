import re
import sys
import shlex
import shutil
import importlib
import contextlib
import argparse
import itertools
from pathlib import Path
from pprint import pformat

from ctypesgen import (
    messages as msgs,
    parser as core_parser,
    processor,
    version,
    printer_python,
    printer_json,
)
from ctypesgen.printer_python import (
    txtpath, get_priv_paths,
)


# -- Helper functions for main_impl() --

@contextlib.contextmanager
def tmp_searchpath(path):
    path = str(path)
    sys.path.insert(0, path)
    try:
        yield
    finally:
        popped = sys.path.pop(0)
        assert popped is path

def _is_relative_to(path, other):
    # check if 'path' is equal to or contained in 'other'
    # this implies that 'path' is longer than 'other', and 'other' a directory
    assert len(path.parts) >= len(other.parts) and other.is_dir()
    if sys.version_info >= (3, 9):
        return path.is_relative_to(other)
    else:
        return path == other or other in path.parents

def find_symbols_in_modules(modnames, outpath, anchor):
    
    # NOTE(geisserml) Concerning relative imports, I've been unable to find another way than adding the output dir's parent to sys.path, given that the module itself may contain relative imports.
    # It seems like this may be a limitation of python's import system, though technically one would imagine the output dir's path itself should be sufficient.
    
    assert isinstance(modnames, (tuple, list))  # not str
    assert isinstance(outpath, Path) and outpath.is_absolute()
    if anchor:
        assert isinstance(anchor, Path) and anchor.is_absolute()
    
    symbols = set()
    for modname in modnames:
        
        n_dots = len(modname) - len(modname.lstrip("."))
        if not n_dots > 0:
            module = importlib.import_module(modname)
        else:
            tight_anchor = outpath.parents[n_dots-1]
            assert _is_relative_to(tight_anchor, anchor)
            diff = tight_anchor.parts[len(anchor.parts):]
            import_path = ".".join(["", *diff, modname[n_dots:]])
            if modname != import_path:
                msgs.status_message(f"Resolved runtime import {modname!r} to compile-time {import_path!r} (rerooted from outpath to linkage anchor)")
            with tmp_searchpath(anchor.parent):
                module = importlib.import_module(import_path, anchor.name)
        
        module_syms = [s for s in dir(module) if not re.fullmatch(r"__\w+__", s)]
        assert len(module_syms) > 0, f"No symbols found in module {module.__name__!r} - linkage would be pointless"
        msgs.status_message(f"Symbols found in {module.__name__!r}: {module_syms}")
        symbols.update(module_syms)
    
    return symbols


# -- Main implementation --

def main_impl(args, cmd_str):
    
    assert args.headers or args.system_headers, "Either --headers or --system-headers required."
    
    if any(m.startswith(".") for m in args.modules) or not args.embed_templates:
        assert args.linkage_anchor, "Relative linked modules or --no-embed-templates require --linkage-anchor"
    if args.linkage_anchor:
        assert _is_relative_to(args.output, args.linkage_anchor)
    
    if args.cpp:
        assert shutil.which(args.cpp[0]), f"Given pre-processor {args.cpp[0]!r} is not available."
    else:
        if shutil.which("gcc"):
            args.cpp = ["gcc", "-E"]
        elif shutil.which("cpp"):
            args.cpp = ["cpp"]
        elif shutil.which("clang"):
            args.cpp = ["clang", "-E"]
        else:
            raise RuntimeError("C pre-processor auto-detection failed: neither gcc nor clang available.")
    
    # Important: must not use +=, this would mutate the original object, which is problematic when default=[] is used and ctypesgen called repeatedly from within python
    args.compile_libdirs = args.compile_libdirs + args.universal_libdirs
    args.runtime_libdirs = args.runtime_libdirs + args.universal_libdirs
    
    # Figure out what names will be defined by linked-in python modules
    args.linked_symbols = find_symbols_in_modules(args.modules, args.output, args.linkage_anchor)
    
    raw_data = core_parser.parse(args.headers, args)
    processor.process(raw_data, args)
    data = [(k, d) for k, d in raw_data.output_order if d.included]
    if not data:
        if raw_data.all:
            msgs.status_message(f"Non-included members - perhaps you meant to run with --all-headers?\n{raw_data.all}")
        raise RuntimeError("No included target members - output would be empty.")
    printer = {"py": printer_python, "json": printer_json}[args.output_language].WrapperPrinter
    msgs.status_message(f"Printing to {args.output}.")
    printer(args.output, args, data, cmd_str)
    
    msgs.status_message("Wrapping complete.")


# -- Argument Parser (Backports) --

if sys.version_info >= (3, 9):
    from argparse import BooleanOptionalAction

else:
    # backport, adapted from argparse sources
    class BooleanOptionalAction (argparse.Action):
        def __init__(self, option_strings, dest, **kwargs):
            
            _option_strings = []
            for option_string in option_strings:
                _option_strings.append(option_string)
                
                if option_string.startswith('--'):
                    option_string = '--no-' + option_string[2:]
                    _option_strings.append(option_string)
            
            super().__init__(option_strings=_option_strings, dest=dest, nargs=0, **kwargs)
        
        def __call__(self, parser, namespace, values, option_string=None):
            if option_string in self.option_strings:
                setattr(namespace, self.dest, not option_string.startswith('--no-'))
        
        def format_usage(self):
            return ' | '.join(self.option_strings)


# -- Argument Parser ---

def generic_path_t(p):
    return Path(p).expanduser().resolve()

def checked_path_t(p, check, exc):
    p = generic_path_t(p)
    if not check(p): raise exc(f"{p}")
    return p

def input_file_t(p):
    return checked_path_t(p, check=Path.is_file, exc=FileNotFoundError)

def input_dir_t(p):
    return checked_path_t(p, check=Path.is_dir, exc=FileNotFoundError)


class LocalArgumentParser (argparse.ArgumentParser):
    def convert_arg_line_to_args(self, arg_line):
        return shlex.split(arg_line)


def get_parser():
    
    # FIXME argparse parameters are not ordered consistently...
    # TODO expand use of BooleanOptionalAction
    
    parser = LocalArgumentParser(
        prog="ctypesgen",
        fromfile_prefix_chars="@",
    )
    
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
        type=input_file_t,
        default=[],  # FIXME perilous
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
        type=generic_path_t,
        metavar="FILE",
        help="Write bindings to FILE. Beware: If FILE exists already, it will be silently overwritten.",
    )
    parser.add_argument(
        "--system-headers",
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
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
        default=[],  # FIXME perilous
        metavar="MODULE",
        help="Use symbols from python module MODULE (site-packages or local import). For local import, either as dot-prefixed import relative to the output file, or as absolute import. Local imports need --no-embed-templates and --linkage-anchor. Local absolute imports also need adding the parent dir to PYTHONPATH.",
    )
    parser.add_argument(
        "--linkage-anchor",
        type=input_dir_t,
        help="The top-level package to use as anchor when importing relative linked modules at compile time. Further, --no-embed-templates needs to know the package root to handle shared templates and libraries. To avoid ambiguity, this option is mandatory in both cases.",
    )
    parser.add_argument(
        "-I", "--includedirs",
        dest="include_search_paths",
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
        metavar="INCLUDEDIR",
        help="add INCLUDEDIR as a directory to search for headers",
    )
    parser.add_argument(
        "-L", "--universal-libdirs",
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
        metavar="LIBDIR",
        help="Add LIBDIR to the search path (both compile-time and run-time)",
    )
    parser.add_argument(
        "--compile-libdirs",
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
        metavar="LIBDIR",
        help="Add LIBDIR to the compile-time library search path.",
    )
    parser.add_argument(
        "--runtime-libdirs",
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
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
        "--no-embed-templates",
        action="store_false",
        dest="embed_templates",
        help="Do not embed boilerplate code in output file (e.g. library loader). Defining --output-language to Python is a prerequisite.",
    )

    # Parser options
    parser.add_argument(
        "--cpp",
        type=shlex.split,
        help="The command to invoke the C preprocessor, including any necessary options. By default, we try to find a supported preprocessor automatically. Example: to always use clang, pass --cpp \"clang -E\".",
    )
    parser.add_argument(
        "-D", "--define",
        dest="cppargs",
        type=lambda n: ("-D", n),
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
        metavar="NAME",
        help="Add a definition to the preprocessor via commandline",
    )
    parser.add_argument(
        "-U", "--undefine",
        dest="cppargs",
        type=lambda n: ("-U", n),
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
        metavar="NAME",
        help="Instruct the preprocessor to undefine the specified macro via commandline",
    )
    parser.add_argument(
        "-X", "--no-default-cppflags",
        nargs="*",
        action="extend",
        default=None,
        metavar="ENTRY",
        help="Remove ENTRY from preprocessor defaults, e.g. -X __GNUC__ can be used to not implicitly undefine __GNUC__. If only the flag is passed but never any values, it removes all defaults.",
    )
    parser.add_argument(
        "--preproc-savepath",
        metavar="FILENAME",
        help="Save preprocessor output to the specified FILENAME",
    )
    parser.add_argument(
        "--preproc-errcheck",
        action=BooleanOptionalAction,
        help="Whether to fail fast if the preprocessor returned a non-zero exit code. Defaults to True, unless on Windows.",
        default=not sys.platform.startswith("win"),
    )
    parser.add_argument(
        "--optimize-lexer",
        action="store_true",
        help="Run the lexer in optimized mode by using a pre-compiled lextab file included in the sources. This allows to run ctypesgen in python's optimized mode, which discards docstrings (PLY relies on docstrings for lexer declarations). It may also improve performance, at the cost of disabling most error checking. If the lexer has been changed, re-generate lextab.py by deleting it and running ctypesgen with this option, in python's normal operating mode. See also chapter '4.13 Optimized mode' of the PLY manual.",
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
        default=[],  # FIXME perilous
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
        type=input_file_t,
        nargs="+",
        action="extend",
        default=[],  # FIXME perilous
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
        default="CDLL",
        choices=("CDLL", "WinDLL", "OleDLL", "pythonapi"),
        help="The ctypes library class to use. 'CDLL' corresponds to the 'cdecl' calling convention, 'WinDLL' to windows-only 'stdcall'. We do not currently support libraries with mixed calling convention. As a special case, you may use 'pythonapi' to bind against Python's C API (passing matching headers and '-l python' is a pre-requisite). 'pythonapi' implies --no-load-library.",
    )
    parser.add_argument(
        "--no-symbol-guards",
        dest="guard_symbols",
        action="store_false",
        help="Do not add hasattr(...) if-guards around binary symbols. Use when input headers and runtime binary are guaranteed to match. If missing symbols are encountered during library loading, they will be excluded from the output.",
    )
    parser.add_argument(
        "--no-macro-guards",
        dest="guard_macros",
        action="store_false",
        help="Do not wrap macros in try/except.",
    )
    parser.add_argument(
        "--no-srcinfo",
        dest="add_srcinfo",
        action="store_false",
        help="Skip adding comments indicating header source file and line number of symbols. This may be useful for cleaner diffs of tracked bindings. (If you wish to know the origin of a symbol, grep for it in the input headers).",
    )
    parser.add_argument(
        "--string-template",
        type=input_file_t,
        metavar="FILE",
        help="Use string template from FILE, implementing the String and WideString types, which will be used as a substitute for char* or wchar_t*, respectively. If all your data is NUL-terminated, you could use e.g. c_char_p and c_wchar_p, or derivatives thereof (override from_param() or _check_retval_() if desired).",
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
    return parser


# -- Entry points and their helper functions --

# Adapted from https://stackoverflow.com/a/59395868/15547292

def _get_parser_defaults(parser):
    defaults = {}
    for action in parser._actions:
        if (not action.required and action.default is not argparse.SUPPRESS
            and action.dest not in ("help", "version")):
            defaults[action.dest] = action.default
    return defaults

def _get_parser_requires(parser):
    return [a.dest for a in parser._actions if a.required]

def api_main(args):
    """
    Pure API entry point (experimental).
    
    Not officially supported. Use at own risk.
    API callers should prefer to go through argparse-based main() where possible.
    
    Part of the reason why this isn't recommended is that no type-checking or conversion is being done; you have to make sure on your own that you pass in the expected types.
    In particular, when you pass a string where a list of strings is expetced, you may get the maddest exceptions (because a string is also iterable).
    """
    
    get_priv_paths.cache_clear()  # preparation: refresh CWD for path stripping
    parser = get_parser()
    
    required_args = _get_parser_requires(parser)
    defaults = _get_parser_defaults(parser)
    print(required_args, defaults, args, sep="\n", file=sys.stderr)
    
    assert all(r in args for r in required_args), f"Must provide all required arguments: {required_args}"
    
    real_args = defaults.copy()
    real_args.update(args)
    real_args = argparse.Namespace(**real_args)
    
    args_str = str(pformat(args))
    for p, x in get_priv_paths():
        args_str = args_str.replace(str(p), x)
    return main_impl(real_args, f"ctypesgen.api_main(\n{args_str}\n)")


def postparse(args):
    args.cppargs = list( itertools.chain(*args.cppargs) )

def main(given_argv=sys.argv[1:]):
    """
    Argparse-based API entry point (recommended).
    Beware: argparse may raise SystemExit - you might want to try/except guard against this.
    """
    get_priv_paths.cache_clear()  # preparation: refresh CWD for path stripping
    args = get_parser().parse_args(given_argv)
    postparse(args)
    cmd_str = " ".join(["ctypesgen"] + [shlex.quote(txtpath(a)) for a in given_argv])
    main_impl(args, cmd_str)


# -- Run main() if this script is invoked --

if __name__ == "__main__":
    main()
