"""
ctypesgen.parser.ctypesparser contains a class, CtypesParser, which is a
subclass of ctypesgen.parser.cparser.CParser. CtypesParser overrides the
handle_declaration() method of CParser. It turns the low-level type declarations
produced by CParser into CtypesType instances and breaks the parser's general
declarations into function, variable, typedef, constant, and type descriptions.
"""

__all__ = ["CtypesParser"]

from ctypesgen.ctypedescs import (
    CtypesArray,
    CtypesBitfield,
    CtypesEnum,
    CtypesFunction,
    CtypesPointer,
    CtypesSimple,
    CtypesStruct,
    CtypesTypedef,
    CtypesSpecial,
    ctypes_type_map,
    ctypes_type_map_python_builtin,
    remove_function_pointer,
)
from ctypesgen.expressions import (
    BinaryExpressionNode,
    ConstantExpressionNode,
    IdentifierExpressionNode,
)
from ctypesgen.parser.cdeclarations import (
    Attrib,
    EnumSpecifier,
    Pointer,
    StructTypeSpecifier,
)
from ctypesgen.parser.cparser import CParser


def make_enum_from_specifier(specifier):
    tag = specifier.tag
    
    enumerators = []
    last_name = None
    for e in specifier.enumerators:
        if e.expression:
            value = e.expression
        else:
            if last_name:
                value = BinaryExpressionNode(
                    "addition",
                    (lambda x, y: x + y),
                    "(%s + %s)",
                    (False, False),
                    IdentifierExpressionNode(last_name),
                    ConstantExpressionNode(1),
                )
            else:
                value = ConstantExpressionNode(0)
        
        enumerators.append((e.name, value))
        last_name = e.name
    
    return CtypesEnum(tag, enumerators, src=(specifier.filename, specifier.lineno))


def get_decl_id(decl):
    """Return the identifier of a given declarator"""
    while isinstance(decl, Pointer):
        decl = decl.pointer
    p_name = ""
    if decl is not None and decl.identifier is not None:
        p_name = decl.identifier
    return p_name


class CtypesParser(CParser):
    """Parse a C file for declarations that can be used by ctypes.
    
    Subclass and override the handle_ctypes_* methods.
    """
    
    def __init__(self, options):
        super().__init__(options)
        self.options = options
        self.type_map = ctypes_type_map
        if self.options.add_python_types:
            self.type_map.update(ctypes_type_map_python_builtin)
    
    def make_struct_from_specifier(self, specifier):
        
        # this method produces the input for the printer
        
        variety = {True: "union", False: "struct"}[specifier.is_union]
        tag = specifier.tag
        
        if specifier.declarations:
            members = []
            for declaration in specifier.declarations:
                declarator = declaration.declarator
                t = self.get_ctypes_type(
                    declaration.type, declarator, check_qualifiers=True
                )
                if declarator is None:
                    # Anonymous field in nested union/struct (C11/GCC).
                    name = None
                else:
                    while declarator.pointer:
                        declarator = declarator.pointer
                    name = declarator.identifier
                members.append((name, remove_function_pointer(t)))
            
            # handle FAM (flexible array member) at end of struct as zero-sized array (see GH issue #219)
            _, last_ctype = members[-1]
            if isinstance(last_ctype, CtypesArray) and last_ctype.count is None:
                last_ctype.count = ConstantExpressionNode(0)
        
        else:
            members = None
        
        return CtypesStruct(
            tag, specifier.attrib, variety, members, src=(specifier.filename, specifier.lineno)
        )

    def get_ctypes_type(self, typ, declarator, check_qualifiers=False):
        signed = True
        typename = "int"
        longs = 0
        t = None
        
        for specifier in typ.specifiers:
            if isinstance(specifier, StructTypeSpecifier):
                t = self.make_struct_from_specifier(specifier)
            elif isinstance(specifier, EnumSpecifier):
                t = make_enum_from_specifier(specifier)
            elif specifier == "signed":
                signed = True
            elif specifier == "unsigned":
                signed = False
            elif specifier == "long":
                longs += 1
            elif specifier == "short":
                longs = -1
            else:
                typename = str(specifier)
        
        if not t:
            # It is a numeric type of some sort
            if (typename, signed, longs) in self.type_map:
                t = CtypesSimple(typename, signed, longs)
            
            elif signed and not longs:
                t = CtypesTypedef(typename)
            
            else:
                name = " ".join(typ.specifiers)
                if typename in [x[0] for x in self.type_map.keys()]:
                    # It's an unsupported variant of a builtin type
                    error = f"Ctypes does not support the type '{name}'."
                else:
                    error = f"Ctypes does not support adding additional specifiers to typedefs, such as '{name}'"
                t = CtypesTypedef(name)
                t.error(error, cls="unsupported-type")
            
            if declarator and declarator.bitfield:
                t = CtypesBitfield(t, declarator.bitfield)
        
        qualifiers = []
        qualifiers.extend(typ.qualifiers)
        while declarator and declarator.pointer:
            if declarator.parameters is not None:
                variadic = "..." in declarator.parameters
                
                params = []
                for param in declarator.parameters:
                    if param == "...":
                        break
                    param_name = get_decl_id(param.declarator)
                    ct = self.get_ctypes_type(param.type, param.declarator)
                    ct.identifier = param_name
                    params.append(ct)
                t = CtypesFunction(t, params, variadic, self.options)
            
            a = declarator.array
            while a:
                t = CtypesArray(t, a.size)
                a = a.array
            
            qualifiers.extend(declarator.qualifiers)
            t = CtypesPointer(t, tuple(typ.qualifiers) + tuple(declarator.qualifiers))
            declarator = declarator.pointer
        
        if declarator and declarator.parameters is not None:
            variadic = "..." in declarator.parameters
            params = []
            for param in declarator.parameters:
                if param == "...":
                    break
                param_name = get_decl_id(param.declarator)
                ct = self.get_ctypes_type(param.type, param.declarator)
                ct.identifier = param_name
                params.append(ct)
            t = CtypesFunction(t, params, variadic, self.options, declarator.attrib)
        
        if declarator:
            a = declarator.array
            while a:
                t = CtypesArray(t, a.size)
                a = a.array
        
        if (
            self.options.string_template
            and isinstance(t, CtypesPointer)
            and isinstance(t.destination, CtypesSimple)
        ):
            if t.destination.name == "char" and t.destination.signed:
                t = CtypesSpecial("String")
            elif t.destination.name == "wchar_t":
                t = CtypesSpecial("WideString")
        
        return t
    
    def handle_declaration(self, declaration, filename, lineno):
        t = self.get_ctypes_type(declaration.type, declaration.declarator)
        
        if type(t) in (CtypesStruct, CtypesEnum):
            self.handle_ctypes_new_type(remove_function_pointer(t), filename, lineno)
        
        declarator = declaration.declarator
        if declarator is None:
            # XXX TEMPORARY while struct with no typedef not filled in
            return
        while declarator.pointer:
            declarator = declarator.pointer
        name = declarator.identifier
        if declaration.storage == "typedef":
            self.handle_ctypes_typedef(name, remove_function_pointer(t), filename, lineno)
        elif type(t) == CtypesFunction:
            attrib = Attrib(t.attrib)
            attrib.update(declaration.attrib)
            self.handle_ctypes_function(
                name, t.restype, t.argtypes, t.errcheck, t.variadic, attrib, filename, lineno
            )
        elif declaration.storage != "static":
            self.handle_ctypes_variable(name, t, filename, lineno)
    
    # ctypes parser interface. Override these methods in your subclass.
    
    def handle_ctypes_new_type(self, ctype, filename, lineno):
        raise NotImplementedError()
    
    def handle_ctypes_typedef(self, name, ctype, filename, lineno):
        raise NotImplementedError()
    
    def handle_ctypes_function(
        self, name, restype, argtypes, errcheck, variadic, attrib, filename, lineno
    ):
        raise NotImplementedError()
    
    def handle_ctypes_variable(self, name, ctype, filename, lineno):
        raise NotImplementedError()
