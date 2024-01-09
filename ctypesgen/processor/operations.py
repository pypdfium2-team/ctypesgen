"""
The operations module contains various functions to process the
DescriptionCollection and prepare it for output.
ctypesgen.processor.pipeline calls the operations module.
"""

import re
import sys
import ctypes
import keyword
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
    # FIXME Check if it has already been aliased in the C code.

    for struct in data.structs:
        if not struct.ctype.anonymous:  # Don't alias anonymous structs
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
    
    # FIXME(geisserml) shouldn't we rather honor the full path?
    known_headers = [Path(x).name for x in opts.headers]

    for desc in data.all:
        if desc.src is not None:
            if desc.src[0] == "<command line>":
                # FIXME(geisserml) I don't understand the intent behind this clause. When does <command line> occur?
                desc.include_rule = "if_needed"
            elif desc.src[0] == "<built-in>":
                if not opts.builtin_symbols:
                    desc.include_rule = "if_needed"
            elif Path(desc.src[0]).name not in known_headers:
                if not opts.all_headers:
                    desc.include_rule = "if_needed"


def remove_macros(data, opts):
    """remove_macros() removes macros if --no-macros is set."""
    if not opts.include_macros:
        for macro in data.macros:
            macro.include_rule = "never"


def filter_by_regex_rules(data, opts):
    valid_rules = {"never", "if_needed", "yes"}
    for rules_entry in opts.symbol_rules:
        rule_name, symbols_regex = rules_entry.split("=", maxsplit=1)
        assert rule_name in valid_rules
        expr = re.compile(symbols_regex)
        for object in data.all:
            if expr.fullmatch(object.py_name()):
                object.include_rule = rule_name


def fix_conflicting_names(data, opts):
    """If any descriptions from the C code would overwrite Python builtins or
    other important names, fix_conflicting_names() adds underscores to resolve
    the name conflict."""
    
    status_message("Looking for conflicting names...")
    
    our_names = {"_libs", "_libs_info"}
    # probably includes a bit more than we actually use ...
    our_names |= {x for x in dir(ctypes) if not x.startswith("_")}
    
    # This dictionary maps names to a string representing where the name came from.
    protected_names = {}
    for name in our_names:
        protected_names[name] = "a name from ctypes or ctypesgen"
    for name in dir(__builtins__):
        protected_names[name] = "a Python builtin"
    for name in opts.linked_symbols:
        # note: the dependency resolver honors linked modules, but we can get conflicts with eagerly included symbols
        # FIXME(geisserml) in case of intentional name shadowing, shouldn't we prioritize our input over linked modules ?
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
        
        if desc.py_name() in protected_names:
        
            conflict_cause = protected_names[desc.py_name()]
            original_info = desc.casual_name()
            while desc.py_name() in protected_names:
                if isinstance(desc, (StructDescription, EnumDescription)):
                    desc.tag += "_"
                else:
                    desc.name += "_"
            
            message = f"{original_info} has been renamed to {desc.casual_name()} due to a name conflict with {conflict_cause}."
            if desc.dependents:
                # pre-requisite: no copying of desc objects throughout the pipeline
                message += f" Dependants (should adapt implicitly): {desc.dependents}"
            desc.warning(message)
            
            # Protect renamed symbols that are known to be included, since they diverge from the original input. We needn't generally protect included symbols, as the preprocessed symbol list should not contain duplicates.
            # TODO(pipeline) should this be put between the two calculate_final_inclusion() steps to also do this for included if_needed symbols ?
            if desc.include_rule == "yes":
                protected_names[desc.py_name()] = desc.casual_name()
    
    # Names of struct members don't conflict with much, but they can conflict with Python keywords.
    for struct in data.structs:
        if struct.opaque: continue  # no members
        for i, (name, type) in enumerate(struct.members):
            # it should be safe to expect there will be no underscored sibling to a keyword, so we needn't loop
            if name in keyword.kwlist:
                name += "_"
                struct.members[i] = (name, type)
                struct.warning(
                    f"Member '{name}' of {struct.casual_name()} has been renamed to '{name}_' because it has the same name as a Python keyword.",
                    cls="rename",
                )

    # Macro arguments may be have names that conflict with Python keywords.
    # TODO actually rename parameter
    for macro in data.macros:
        if not macro.params: continue  # may be None
        for param in macro.params:
            if param in keyword.kwlist:
                macro.error(
                    f"One of the params to {macro.casual_name()}, '{param}', has the same name as a Python keyword. {macro.casual_name()} will be excluded.",
                    cls="name-conflict",
                )
                macro.include_rule = "never"
                break  # params loop


import _ctypes as ctypes_backend

def free_library(lib_handle):
    # https://github.com/python/cpython/issues/58802
    # On windows, we have to free libraries explicitly so the backing file may be deleted afterwards.
    # While we're at it, also free libraries on other platforms for consistency.
    status_message(f"Freeing library handle {lib_handle} ...")
    if sys.platform.startswith("win32"):
        ctypes_backend.FreeLibrary(lib_handle)
    else:
        ctypes_backend.dlclose(lib_handle)


def check_symbols(data, opts):
    
    if opts.no_load_library:
        status_message(f"Bypass load_library '{opts.library}'.")
        return
    if not opts.library:
        status_message(f"No library given, nothing to load.")
        return

    try:
        libraryloader._register_library(
            name = opts.library,
            dllclass = getattr(ctypes, opts.dllclass),
            dirs = opts.compile_libdirs,
            search_sys = opts.search_sys,
            reldir = Path.cwd(),
        )
        library = libraryloader._libs[opts.library]
    except ImportError as e:
        warning_message(e)
        warning_message(f"Could not load library '{opts.library}'. Okay, I'll try to load it at runtime instead.", cls="missing-library")
        return
    
    try:
        # don't bother checking symbols that will definitely be excluded
        # TODO(pipeline) should this be put between the two calculate_final_inclusion() calls to skip if_needed symbols that won't be part of the output ?
        missing_symbols = {s for s in (data.functions + data.variables) if s.include_rule != "never" and not hasattr(library, s.c_name())}
    finally:
        free_library(library._handle)
        del library
    
    if missing_symbols:
        warning_message(
            f"{len(missing_symbols)} symbols could not be found. Possible causes include:\n"
            "- Private members (use --symbol-rules to exclude)\n"
            "- Binary/headers mismatch (ABI unsafe, should be avoided by caller)\n"
            f"{missing_symbols}",
            cls="other"
        )
        
        if not opts.guard_symbols:
            warning_message("Missing symbols will be excluded due to --no-symbol-guards")
            for s in missing_symbols:
                s.include_rule = "never"
