"""
A brief explanation of the processing steps:
1. The dependencies module builds a dependency graph for the descriptions.

2. Operation functions are called to perform various operations on the
descriptions. The operation functions are found in operations.py.

3. If an operation function decides to exclude a description from the output, it
sets 'description.include_rule' to "never"; if an operation function decides not
to include a description by default, but to allow if required, it sets
'description.include_rule' to "if_needed".

4. If an operation function encounters an error that makes a description unfit
for output, it appends a string error message to 'description.errors'.
'description.warnings' is a list of warning messages that will be displayed but
will not prevent the description from being output.

5. Based on 'description.include_rule', calculate_final_inclusion() decides
which descriptions to include in the output. It sets 'description.included' to
True or False.

6. For each description, print_errors_encountered() checks if there are error
messages in 'description.errors'. If so, print_errors_encountered() prints the
error messages, but only if 'description.included' is True - it doesn't bother
the user with error messages regarding descriptions that would not be in the
output anyway. It also prints 'description.warnings'.

7. calculate_final_inclusion() is called again to recalculate based on
the errors that print_errors_encountered() has flagged.

"""

from ctypesgen.descriptions import MacroDescription
from ctypesgen.messages import log
from ctypesgen.processor.dependencies import find_dependencies
from ctypesgen.processor.operations import (
    automatically_typedef_structs,
    filter_by_regex_rules,
    check_symbols,
    fix_conflicting_names,
    mask_external_members,
    remove_macros,
    remove_NULL,
)


def process(data, options):
    # FIXME(pipeline) can we do fix_conflicting_names() and check_symbols() after we know the decision of symbols with include rule "if_needed", to avoid unnecessary operations?
    
    log.info("Processing description list.")
    
    find_dependencies(data, options)
    automatically_typedef_structs(data, options)
    mask_external_members(data, options)
    remove_macros(data, options)
    filter_by_regex_rules(data, options)
    remove_NULL(data, options)
    if options.output_language.startswith("py"):
        fix_conflicting_names(data, options)
    
    check_symbols(data, options)
    calculate_final_inclusion(data, options)
    print_errors_encountered(data, options)
    calculate_final_inclusion(data, options)


def calculate_final_inclusion(data, opts):
    """Calculates which descriptions will be included in the output library.

    An object with include_rule="never" is never included.
    An object with include_rule="yes" is included if its requirements can be included.
    An object with include_rule="if_needed" is included if an object to be included
        requires it and if its requirements can be included.
    """

    def can_include_desc(desc):
        if desc.can_include is None:
            if desc.include_rule == "never":
                desc.can_include = False
            elif desc.include_rule in ("yes", "if_needed"):
                desc.can_include = True
                for req in desc.requirements:
                    if not can_include_desc(req):
                        desc.can_include = False
            else:
                assert False, f"unknown include rule {desc.include_rule!r}"
        return desc.can_include

    def do_include_desc(desc):
        if desc.included:
            return  # We've already been here
        desc.included = True
        for req in desc.requirements:
            do_include_desc(req)

    for desc in data.all:
        desc.can_include = None  # None means "Not Yet Decided"
        desc.included = False

    for desc in data.all:
        if desc.include_rule == "yes" and can_include_desc(desc):
            do_include_desc(desc)


def print_errors_encountered(data, opts):
    # See descriptions.py for an explanation of the error-handling mechanism
    for desc in data.all:
        # If description would not have been included, dont bother user by
        # printing warnings.
        if desc.included or opts.show_all_errors:
            if opts.show_long_errors or len(desc.errors) + len(desc.warnings) <= 2:
                for error in desc.errors:
                    # Macro errors will always be displayed as warnings.
                    if isinstance(desc, MacroDescription):
                        if opts.show_macro_warnings:
                            log.warning(error)
                    else:
                        log.error(error)
                for warning in desc.warnings:
                    log.warning(warning)

            else:
                if desc.errors:
                    error1 = desc.errors[0]
                    log.error(error1)
                    numerrs = len(desc.errors) - 1
                    numwarns = len(desc.warnings)
                    if numwarns:
                        log.error(f"{numerrs} more errors and {numwarns} more warnings for {desc.casual_name()}")
                    else:
                        log.error(f"{numerrs} more errors for {desc.casual_name()}")
                else:
                    warning1 = desc.warnings[0]
                    log.warning(warning1)
                    log.warning(f"{len(desc.warnings)-1} more errors for {desc.casual_name()}")
        if desc.errors:
            # process() will recalculate to take this into account
            desc.include_rule = "never"
