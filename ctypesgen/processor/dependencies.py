"""
The dependencies module determines which descriptions depend on which other
descriptions.
"""

from ctypesgen.descriptions import MacroDescription, UndefDescription
from ctypesgen.ctypedescs import visit_type_and_collect_info


def find_dependencies(data, opts):
    """Visit each description in `data` and figure out which other descriptions
    it depends on, putting the results in desc.requirements. Also find errors in
    ctypedecls or expressions attached to the description and transfer them to the
    description."""

    struct_names = {}
    enum_names = {}
    typedef_names = {}
    ident_names = {}

    # Start the lookup tables with names from linked modules

    for name in opts.linked_symbols:
        typedef_names[name] = None
        ident_names[name] = None
        if name.startswith("struct_") or name.startswith("enum_"):
            variety = name.split("_")[0]
            tag = "_".join(name.split("_")[1:])
            struct_names[(variety, tag)] = None
        if name.startswith("enum_"):
            enum_names[name] = None

    def depend(desc, nametable, name):
        """Try to add `name` as a requirement for `desc`, looking `name` up in
        `nametable`. Returns True if found."""

        if name in nametable:
            requirement = nametable[name]
            if requirement:
                desc.add_requirements(requirement)
            return True
        else:
            return False

    def co_depend(desc, nametable, name):
        """
        Try to add `name` as a requirement for `desc`, looking `name` up in
        `nametable`.  Also try to add desc as a requirement for `name`.

        Returns Description of `name` if found.
        """

        requirement = nametable.get(name, None)
        if requirement is None:
            return

        desc.add_requirements(requirement)
        requirement.add_requirements(desc)
        return requirement

    def find_dependencies_for(desc, kind):
        """Find all the descriptions that `desc` depends on and add them as
        dependencies for `desc`. Also collect error messages regarding `desc` and
        convert unlocateable descriptions into error messages."""

        if kind == "constant":
            roots = [desc.value]
        elif kind == "struct":
            roots = []
        elif kind == "struct_fields":
            roots = [desc.ctype]
        elif kind == "enum":
            roots = []
        elif kind == "typedef":
            roots = [desc.ctype]
        elif kind == "function":
            roots = desc.argtypes + [desc.restype]
        elif kind == "variable":
            roots = [desc.ctype]
        elif kind == "macro":
            roots = [desc.expr] if desc.expr else []
        elif kind == "undef":
            roots = [desc.macro]
        else:
            assert False, f"unknown kind {kind!r}"

        cstructs, cenums, ctypedefs, errors, identifiers = [], [], [], [], []

        for root in roots:
            s, e, t, errs, i = visit_type_and_collect_info(root)
            cstructs.extend(s)
            cenums.extend(e)
            ctypedefs.extend(t)
            errors.extend(errs)
            identifiers.extend(i)

        unresolvables = []

        for cstruct in cstructs:
            if kind == "struct" and desc.variety == cstruct.variety and desc.tag == cstruct.tag:
                continue
            if not depend(desc, struct_names, (cstruct.variety, cstruct.tag)):
                unresolvables.append(f"{cstruct.variety} '{cstruct.tag}'")

        for cenum in cenums:
            if kind == "enum" and desc.tag == cenum.tag:
                continue
            if not depend(desc, enum_names, cenum.tag):
                unresolvables.append(f"enum '{cenum.tag}'")

        for ctypedef in ctypedefs:
            if not depend(desc, typedef_names, ctypedef):
                unresolvables.append(f"typedef '{ctypedef}'")

        for ident in identifiers:
            if isinstance(desc, MacroDescription) and desc.params and ident in desc.params:
                continue

            elif opts.include_undefs and isinstance(desc, UndefDescription):
                macro_desc = None
                if ident == desc.macro.name:
                    macro_desc = co_depend(desc, ident_names, ident)
                if macro_desc is None or not isinstance(macro_desc, MacroDescription):
                    unresolvables.append(f"identifier '{ident}'")

            elif not depend(desc, ident_names, ident):
                unresolvables.append(f"identifier '{ident}'")

        for u in unresolvables:
            errors.append((f"{desc.casual_name()} depends on an unknown {u}.", None))

        for err, cls in errors:
            err += f" {desc.casual_name()} will not be output"
            desc.error(err, cls=cls)

    def add_to_lookup_table(desc, kind):
        """Add `desc` to the lookup table so that other descriptions that use
        it can find it."""
        
        if kind == "struct":
            target, key = struct_names, (desc.variety, desc.tag)
        elif kind == "enum":
            target, key = enum_names, desc.tag
        elif kind == "typedef":
            target, key = typedef_names, desc.name
        elif kind in ("function", "constant", "variable", "macro"):
            target, key = ident_names, desc.name
        else:
            assert kind in ("undef", "struct_fields"), f"unknown kind {kind!r}"
            return
        
        if key not in target:
            target[key] = desc

    # Macros are handled differently from everything else because macros can
    # call other macros that are referenced after them in the input file, but
    # no other type of description can look ahead like that.
    
    macros = []
    for kind, desc in data.output_order:
        add_to_lookup_table(desc, kind)
        find_dependencies_for(desc, kind) if kind != "macro" else macros.append(desc)

    for desc in macros:
        find_dependencies_for(desc, "macro")
