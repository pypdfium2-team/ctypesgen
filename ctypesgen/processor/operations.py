"""
The operations module contains various functions to process the
DescriptionCollection and prepare it for output.
ctypesgen.processor.pipeline calls the operations module.
"""

import re
import os
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
            typedef.add_requirements(set([struct]))

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

    # This dictionary maps names to a string representing where the name
    # came from.
    important_names = {}

    occupied_names = set()
    occupied_names = occupied_names.union(
        # ctypesgen names
        [
            "_libs",
            "_libs_info",
            # the following names are only accessed before the symbols list, so we don't strictly care about them being overridden
            # "sys",
            # "warnings",
            # "pathlib",
            # "_find_library",
            # "_register_library",
        ]
    )
    occupied_names = occupied_names.union(
        # ctypes names, required for symbol prints
        [
            "ctypes",
            "addressof",
            "ArgumentError",
            "cast",
            "CFUNCTYPE",
            "pointer",
            "POINTER",
            "Union",
            "sizeof",
            "Structure",
            "c_buffer",
            "c_byte",
            "c_char",
            "c_char_p",
            "c_double",
            "c_float",
            "c_int",
            "c_int16",
            "c_int32",
            "c_int64",
            "c_int8",
            "c_long",
            "c_longlong",
            "c_ptrdiff_t",
            "c_short",
            "c_size_t",
            "c_ubyte",
            "c_uint",
            "c_uint16",
            "c_uint32",
            "c_uint64",
            "c_uint8",
            "c_ulong",
            "c_ulonglong",
            "c_ushort",
            "c_void",
            "c_void_p",
            "c_voidp",
            "c_wchar",
            "c_wchar_p",
        ]
    )
    for name in occupied_names:
        important_names[name] = "a name needed by ctypes or ctypesgen"
    for name in dir(__builtins__):
        important_names[name] = "a Python builtin"
    for name in opts.imported_symbols:
        important_names[name] = "a name from an included Python module"
    for name in keyword.kwlist:
        important_names[name] = "a Python keyword"

    for description in descriptions:
        if description.py_name() in important_names:
            conflict_name = important_names[description.py_name()]

            original_name = description.casual_name()
            while description.py_name() in important_names:
                if isinstance(description, (StructDescription, EnumDescription)):
                    description.tag += "_"
                else:
                    description.name = "_" + description.name

            if not description.dependents:
                description.warning(
                    "%s has been renamed to %s due to a name "
                    "conflict with %s." % (original_name, description.casual_name(), conflict_name),
                    cls="rename",
                )
            else:
                description.warning(
                    "%s has been renamed to %s due to a name "
                    "conflict with %s. Other objects depend on %s - those "
                    "objects will be skipped."
                    % (original_name, description.casual_name(), conflict_name, original_name),
                    cls="rename",
                )

                for dependent in description.dependents:
                    dependent.include_rule = "never"

            if description.include_rule == "yes":
                important_names[description.py_name()] = description.casual_name()

    # Names of struct members don't conflict with much, but they can conflict
    # with Python keywords.

    for struct in data.structs:
        if not struct.opaque:
            for i, (name, type) in enumerate(struct.members):
                if name in keyword.kwlist:
                    struct.members[i] = ("_" + name, type)
                    struct.warning(
                        'Member "%s" of %s has been renamed to '
                        '"%s" because it has the same name as a Python '
                        "keyword." % (name, struct.casual_name(), "_" + name),
                        cls="rename",
                    )

    # Macro arguments may be have names that conflict with Python keywords.
    # In a perfect world, this would simply rename the parameter instead
    # of throwing an error message.

    for macro in data.macros:
        if macro.params:
            for param in macro.params:
                if param in keyword.kwlist:
                    macro.error(
                        'One of the parameters to %s, "%s" has the '
                        "same name as a Python keyword. %s will be skipped."
                        % (macro.casual_name(), param, macro.casual_name()),
                        cls="name-conflict",
                    )


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
            search_sys = opts.allow_system_search,
            reldir = Path.cwd(),
        )
        library = libraryloader._libs[opts.library]
    except ImportError as e:
        warning_message(e)
        warning_message(f"Could not load library '{opts.library}'. Okay, I'll try to load it at runtime instead.", cls="missing-library")
        return
    
    # don't bother checking symbols that will definitely be excluded
    missing_symbols = {s for s in (data.functions + data.variables) if s.include_rule != "never" and not hasattr(library, s.c_name())}
    if missing_symbols:
        if opts.include_missing_symbols:
            warning_message(
                "Some symbols could not be found. Possible causes include:\n"
                "- Private members (use --exclude-symbols or --no-missing-symbols to handle)\n"
                "- Binary/headers mismatch (ABI unsafe, should be avoided by caller)\n",
                cls="other"
            )
            if not opts.guard_symbols:
                status_message("Missing symbols will be guarded selectively despite --no-symbol-guards")
        status_message(
            f"Missing symbols (len {len(missing_symbols)}):\n{missing_symbols}\n"
            f"Included? - {opts.include_missing_symbols}"
        )
        
        for s in missing_symbols:
            s.is_missing = True
            if not opts.include_missing_symbols:
                s.include_rule = "never"
