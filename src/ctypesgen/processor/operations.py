"""
The operations module contains various functions to process the
DescriptionCollection and prepare it for output.
ctypesgen.processor.pipeline calls the operations module.
"""

import re
import sys
import ctypes
import keyword
import traceback
from pathlib import Path

from ctypesgen import libraryloader
from ctypesgen.descriptions import (
    EnumDescription,
    StructDescription,
    TypedefDescription,
)
from ctypesgen.messages import warning_message, status_message


# Processor functions

def automatically_typedef_structs(data, options):
    """automatically_typedef_structs() aliases "struct_<tag>" to "<tag>" for
    every struct and union."""
    # XXX Check if it has already been aliased in the C code.
    for struct in data.structs:
        if struct.ctype.anonymous: continue  # Don't alias anonymous structs
        typedef = TypedefDescription(struct.tag, struct.ctype, src=struct.src)
        typedef.add_requirements(struct)
        data.typedefs.append(typedef)
        data.all.insert(data.all.index(struct) + 1, typedef)
        data.output_order.append(("typedef", typedef))


def remove_NULL(data, options):
    """remove_NULL() removes any NULL definitions from the C headers because
    ctypesgen supplies its own NULL definition."""
    for macro in data.macros:
        if macro.name == "NULL":
            macro.include_rule = "never"


def mask_external_members(data, opts):
    """mask_external_members() removes descriptions if they came from files
    outside of the header files specified from the command line."""
    # Naively match against header names rather than full paths to avoid relying on pre-processor path expansion details
    # e.g. pcpp does not generally output full paths (integrating pcpp with ctypesgen is experimental)
    input_header_names = [Path(h).name for h in opts.headers + opts.system_headers]
    for desc in data.all:
        if desc.src[0] == "<command line>":
            desc.include_rule = "if_needed"
        elif desc.src[0] == "<built-in>" and not opts.builtin_symbols:
            desc.include_rule = "if_needed"
        elif not (Path(desc.src[0]).name in input_header_names or opts.all_headers):
            desc.include_rule = "if_needed"


def remove_macros(data, opts):
    """remove_macros() removes macros if --no-macros is set."""
    if opts.include_macros: return
    for macro in data.macros:
        macro.include_rule = "never"


def filter_by_regex_rules(data, opts):
    for rule_entry in opts.symbol_rules:
        rule_name, symbols_regex = rule_entry.split("=", maxsplit=1)
        if rule_name not in {"never", "if_needed", "yes"}:
            raise ValueError(f"Unknown include rule {rule_name!r}")
        expr = re.compile(symbols_regex)
        for desc in data.all:
            if expr.fullmatch(desc.py_name()):
                desc.include_rule = rule_name


def fix_conflicting_names(data, opts):
    """If any descriptions from the C code would overwrite Python builtins or
    other important names, fix_conflicting_names() adds underscores to resolve
    the name conflict."""
    
    status_message("Looking for conflicting names...")
    
    our_names = {"_libs", "_libs_info", "UNCHECKED"}
    # probably includes a bit more than we actually use ...
    our_names |= {x for x in dir(ctypes) if not x.startswith("_")}
    
    # This dictionary maps names to a string representing where the name came from.
    protected_names = {}
    for name in our_names:
        protected_names[name] = "a name from ctypes or ctypesgen"
    for name in dir(__builtins__):
        protected_names[name] = "a Python builtin"
    for name in opts.linked_symbols:
        # known issue: linked modules are naively prioritized throughout ctypesgen, i.e. intentional overloads are ignored
        protected_names[name] = "a name from a linked Python module"
    for name in keyword.kwlist:
        protected_names[name] = "a Python keyword"
    
    # This is the order of priority for names
    descriptions = (
        data.functions
        + data.variables
        + data.structs
        + data.typedefs
        + data.enums
        + data.constants
        + data.macros
    )
    
    for desc in descriptions:
        
        if desc.py_name() not in protected_names: continue
            
        conflict_name = protected_names[desc.py_name()]
        original_name = desc.casual_name()
        while desc.py_name() in protected_names:
            if isinstance(desc, (StructDescription, EnumDescription)):
                desc.tag += "_"
            else:
                desc.name += "_"
        
        message = f"{original_name} has been renamed to {desc.casual_name()} due to a name conflict with {conflict_name}."
        if desc.dependents:
            # pre-requisite: no copying of desc objects throughout the pipeline
            message += f" Dependants (should adapt implicitly): {desc.dependents}"
        desc.warning(message)
        
        # Protect renamed symbols that are known to be included, since they diverge from the original input. We must not generally protect included symbols (deliberate redefines).
        # TODO(pipeline) ideally, this should also be done for "if_needed" symbols that were resolved to be included
        if desc.include_rule == "yes":
            protected_names[desc.py_name()] = desc.casual_name()

    # Names of struct members don't conflict with much, but they can conflict with Python keywords.

    for struct in data.structs:
        if struct.opaque: continue  # no members
        for i, (name, type) in enumerate(struct.members):
            # it should be safe to expect there will be no underscored sibling to a keyword, so we needn't loop
            if name not in keyword.kwlist: continue
            struct.members[i] = (f"{name}_", type)
            struct.warning(
                f"Member '{name}' of {struct.casual_name()} has been renamed to '{name}_' because it has the same name as a Python keyword.",
                cls="rename",
            )

    # Macro arguments may be have names that conflict with Python keywords.
    # TODO actually rename parameter

    for macro in data.macros:
        if not macro.params: continue  # may be None
        for param in macro.params:
            if param not in keyword.kwlist: continue
            macro.error(
                f"One of the params to {macro.casual_name()}, '{param}', has the same name as a Python keyword. {macro.casual_name()} will be excluded.",
                cls="name-conflict",
            )
            macro.include_rule = "never"
            break  # params loop


import _ctypes as ctypes_backend

def free_library(lib_handle):
    # https://github.com/python/cpython/issues/58802
    # https://github.com/python/cpython/blob/3.13/Modules/_ctypes/callproc.c
    # On Windows, we have to free libraries explicitly so the backing file may be deleted afterwards (the test suite does this).
    # While we're at it, also free libraries on other platforms for consistency.
    status_message(f"Freeing library handle {lib_handle} ...")
    if sys.platform.startswith("win32"):
        ctypes_backend.FreeLibrary(lib_handle)
    else:
        ctypes_backend.dlclose(lib_handle)


def check_symbols(data, opts):
    
    if opts.no_load_library or not opts.library or opts.dllclass == "pythonapi":
        status_message(f"No library loading.")
        return
    
    try:
        libraryloader.__file__ = str(Path.cwd() / "spoofed_ll.py")
        libraryloader._register_library(
            name = opts.library,
            dllclass = getattr(ctypes, opts.dllclass),
            dirs = opts.compile_libdirs,
            search_sys = opts.search_sys,
        )
        library = libraryloader._libs[opts.library]
    except (ImportError, OSError):
        traceback.print_exc()
        warning_message(f"Could not load library '{opts.library}'. Okay, I'll try to load it at runtime instead.", cls="missing-library")
        return
    
    try:
        missing_symbols = {s for s in (data.functions + data.variables) if s.include_rule != "never" and not hasattr(library, s.c_name())}
    finally:
        free_library(library._handle); del library
    
    if missing_symbols:
        warning_message(f"Some symbols could not be found:\n{missing_symbols}", cls="other")
        if not opts.guard_symbols:
            warning_message("Missing symbols will be excluded due to --no-symbol-guards")
            for s in missing_symbols:
                s.include_rule = "never"
