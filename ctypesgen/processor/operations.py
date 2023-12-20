"""
The operations module contains various functions to process the
DescriptionCollection and prepare it for output.
ctypesgen.processor.pipeline calls the operations module.
"""

import re
import os
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
    # XXX Check if it has already been aliased in the C code.

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


def remove_descriptions_in_system_headers(data, opts):
    """remove_descriptions_in_system_headers() removes descriptions if they came
    from files outside of the header files specified from the command line."""

    known_headers = [os.path.basename(x) for x in opts.headers]

    for description in data.all:
        if description.src is not None:
            if description.src[0] == "<command line>":
                description.include_rule = "if_needed"
            elif description.src[0] == "<built-in>":
                if not opts.builtin_symbols:
                    description.include_rule = "if_needed"
            elif os.path.basename(description.src[0]) not in known_headers:
                if not opts.all_headers:
                    # If something else requires this, include it even though
                    # it is in a system header file.
                    description.include_rule = "if_needed"


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
    important_names = {}
    for name in our_names:
        important_names[name] = "a name from ctypes or ctypesgen"
    for name in dir(__builtins__):
        important_names[name] = "a Python builtin"
    for name in opts.imported_symbols:
        important_names[name] = "a name from an included Python module"
    for name in keyword.kwlist:
        important_names[name] = "a Python keyword"
    
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
    
    # FIXME(geisserml) This does not actually update dependents, just recursively exlcude them. Confound it!
    # Yet, the scope of this issue should hopefully be limited thanks to the struct_* and enum_* prefixes, and functions trying to use the direct definition.
    
    for desc in descriptions:
        if desc.py_name() in important_names:
            conflict_name = important_names[desc.py_name()]

            original_name = desc.casual_name()
            while desc.py_name() in important_names:
                if isinstance(desc, (StructDescription, EnumDescription)):
                    desc.tag += "_"
                else:
                    desc.name = "_" + desc.name
            
            message = "%s has been renamed to %s due to a name conflict with %s." % \
                      (original_name, desc.casual_name(), conflict_name)
            if desc.dependents:
                message += " Dependant objects will be excluded (FIXME)."
                for dependent in desc.dependents:
                    dependent.include_rule = "never"
            desc.warning(message)
            
            if desc.include_rule == "yes":
                important_names[desc.py_name()] = desc.casual_name()

    # Names of struct members don't conflict with much, but they can conflict
    # with Python keywords.

    for struct in data.structs:
        if struct.opaque: continue  # no members
        for i, (name, type) in enumerate(struct.members):
            if name in keyword.kwlist:
                struct.members[i] = ("_" + name, type)
                struct.warning(
                    "Member '%s' of %s has been renamed to '%s' because it has the same name "
                    "as a Python keyword." % (name, struct.casual_name(), "_" + name),
                    cls="rename",
                )

    # Macro arguments may be have names that conflict with Python keywords.
    # TODO actually rename parameter

    for macro in data.macros:
        if not macro.params: continue  # may be None
        for param in macro.params:
            if param in keyword.kwlist:
                macro.error(
                    "One of the params to %s, '%s' has the same name as a Python keyword. "
                    "%s will be excluded." % (macro.casual_name(), param, macro.casual_name()),
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
