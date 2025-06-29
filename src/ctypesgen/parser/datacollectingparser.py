"""
DataCollectingParser subclasses ctypesparser.CtypesParser and builds Description
objects from the CtypesType objects and other information from CtypesParser.
After parsing is complete, a DescriptionCollection object can be retrieved by
calling DataCollectingParser.data().
"""

import os
from tempfile import mkstemp

from ctypesgen.ctypedescs import CtypesEnum, CtypesType, CtypesTypeVisitor
from ctypesgen.descriptions import (
    ConstantDescription,
    DescriptionCollection,
    EnumDescription,
    FunctionDescription,
    MacroDescription,
    StructDescription,
    TypedefDescription,
    UndefDescription,
    VariableDescription,
)
from ctypesgen.expressions import ConstantExpressionNode
from ctypesgen.messages import error_message, status_message
from ctypesgen.parser import ctypesparser
from ctypesgen.parser.cdeclarations import Attrib


class DataCollectingParser(ctypesparser.CtypesParser, CtypesTypeVisitor):
    """
    Main class for the Parser component. Steps for use:
    >>> p = DataCollectingParser(names_of_header_files,options)
    >>> p.parse()
    >>> data = p.data()  # A dictionary of constants, enums, structs, functions, etc.
    """
    
    def __init__(self, headers, options):
        super().__init__(options)
        self.headers = headers
        self.options = options
        
        self.constants = []
        self.typedefs = []
        self.structs = []
        self.enums = []
        self.functions = []
        self.variables = []
        self.macros = []
        
        self.all = []
        self.output_order = []
        
        # NULL is a useful macro to have defined
        null = ConstantExpressionNode(None)
        nullmacro = ConstantDescription("NULL", null, ("<built-in>", 1))
        self.constants.append(nullmacro)
        self.all.append(nullmacro)
        self.output_order.append(("constant", nullmacro))
        
        # A list of tuples describing macros; saved to be processed after
        # everything else has been parsed
        self.saved_macros = []
        # A set of structs that are already known
        self.already_seen_structs = set()
        # A dict of structs that have only been seen in opaque form
        self.already_seen_opaque_structs = {}
        # A set of enums that are already known
        self.already_seen_enums = set()
        # A dict of enums that have only been seen in opaque form
        self.already_seen_opaque_enums = {}
    
    def parse(self):
        fd, fname = mkstemp(suffix=".h")
        with os.fdopen(fd, "w") as f:
            for header in self.options.system_headers:
                f.write(f"#include <{header}>\n")
            for header in self.headers:
                # self.headers: list of resolved Path objects
                f.write(f'#include "{header}"\n')
            f.flush()
        try:
            super().parse(fname, self.options.debug_level)
        finally:
            os.unlink(fname)

        for name, params, expr, (filename, lineno) in self.saved_macros:
            self.handle_macro(name, params, expr, filename, lineno)
    
    def handle_define_constant(self, name, expr, filename, lineno):
        # Called by CParser
        # Save to handle later
        self.saved_macros.append((name, None, expr, (filename, lineno)))
    
    def handle_define_unparseable(self, name, params, value, filename, lineno):
        # Called by CParser
        if params:
            original_string = "#define %s(%s) %s" % (name, ",".join(params), " ".join(value))
        else:
            original_string = "#define %s %s" % (name, " ".join(value))
        macro = MacroDescription(name, params, None, src=(filename, lineno))
        macro.error(f"Could not parse macro '{original_string}'", cls="macro")
        macro.original_string = original_string
        self.macros.append(macro)
        self.all.append(macro)
        self.output_order.append(("macro", macro))
    
    def handle_define_macro(self, name, params, expr, filename, lineno):
        # Called by CParser
        # Save to handle later
        self.saved_macros.append((name, params, expr, (filename, lineno)))
    
    def handle_undefine(self, macro, filename, lineno):
        # save to handle later to get order correct
        self.saved_macros.append(("#undef", None, macro, (filename, lineno)))
    
    def handle_ctypes_typedef(self, name, ctype, filename, lineno):
        # Called by CtypesParser
        ctype.visit(self)
        typedef = TypedefDescription(name, ctype, src=(filename, repr(lineno)))
        self.typedefs.append(typedef)
        self.all.append(typedef)
        self.output_order.append(("typedef", typedef))

    def handle_ctypes_new_type(self, ctype, filename, lineno):
        # Called by CtypesParser
        if isinstance(ctype, CtypesEnum):
            self.handle_enum(ctype, filename, lineno)
        else:
            self.handle_struct(ctype, filename, lineno)
    
    def handle_ctypes_function(
        self, name, restype, argtypes, errcheck, variadic, attrib, filename, lineno
    ):
        # Called by CtypesParser
        restype.visit(self)
        for argtype in argtypes:
            argtype.visit(self)
        
        function = FunctionDescription(
            name, restype, argtypes, errcheck, variadic, attrib, src=(filename, repr(lineno))
        )
        
        self.functions.append(function)
        self.all.append(function)
        self.output_order.append(("function", function))
    
    def handle_ctypes_variable(self, name, ctype, filename, lineno):
        # Called by CtypesParser
        ctype.visit(self)
        variable = VariableDescription(name, ctype, src=(filename, repr(lineno)))
        self.variables.append(variable)
        self.all.append(variable)
        self.output_order.append(("variable", variable))

    def handle_struct(self, ctypestruct, filename, lineno):
        # Called from within DataCollectingParser
        
        # When we find an opaque struct, we make a StructDescription for it
        # and record it in self.already_seen_opaque_structs. If we later
        # find a transparent struct with the same tag, we fill in the
        # opaque struct with the information from the transparent struct,
        # append the fields body to the outputs, and remove the opaque
        # struct from the record
        
        name = f"{ctypestruct.variety} {ctypestruct.tag}"
        if name in self.already_seen_structs:
            return
        
        if ctypestruct.opaque:
            if name not in self.already_seen_opaque_structs:
                struct = StructDescription(
                    ctypestruct.tag,
                    ctypestruct.attrib,
                    ctypestruct.variety,
                    None,  # No members
                    True,  # Opaque
                    ctypestruct,
                    src=(filename, str(lineno)),
                )
                
                self.already_seen_opaque_structs[name] = struct
                self.structs.append(struct)
                self.all.append(struct)
                self.output_order.append(("struct", struct))
        
        else:
            for membername, ctype in ctypestruct.members:
                ctype.visit(self)
            
            if name in self.already_seen_opaque_structs:
                # Fill in older version
                struct = self.already_seen_opaque_structs[name]
                struct.opaque = False
                struct.members = ctypestruct.members
                struct.ctype = ctypestruct
                struct.src = ctypestruct.src
                self.output_order.append(("struct_fields", struct))
                del self.already_seen_opaque_structs[name]
            
            else:
                struct = StructDescription(
                    ctypestruct.tag,
                    ctypestruct.attrib,
                    ctypestruct.variety,
                    ctypestruct.members,
                    False,  # Not opaque
                    src=(filename, str(lineno)),
                    ctype=ctypestruct,
                )
                self.structs.append(struct)
                self.all.append(struct)
                self.output_order.append(("struct", struct))
                self.output_order.append(("struct_fields", struct))
            
            self.already_seen_structs.add(name)
    
    def handle_enum(self, ctypeenum, filename, lineno):
        # Called from within DataCollectingParser.
        
        # Process for handling opaque enums is the same as process for opaque
        # structs. See handle_struct() for more details.
        
        tag = ctypeenum.tag
        if tag in self.already_seen_enums:
            return
        
        if ctypeenum.opaque:
            if tag not in self.already_seen_opaque_enums:
                enum = EnumDescription(ctypeenum.tag, None, ctypeenum, src=(filename, str(lineno)))
                enum.opaque = True
                
                self.already_seen_opaque_enums[tag] = enum
                self.enums.append(enum)
                self.all.append(enum)
                self.output_order.append(("enum", enum))
        
        else:
            if tag in self.already_seen_opaque_enums:
                # Fill in older opaque version
                enum = self.already_seen_opaque_enums[tag]
                enum.opaque = False
                enum.ctype = ctypeenum
                enum.src = ctypeenum.src
                enum.members = ctypeenum.enumerators
                del self.already_seen_opaque_enums[tag]
            
            else:
                enum = EnumDescription(
                    ctypeenum.tag,
                    ctypeenum.enumerators,
                    src=(filename, str(lineno)),
                    ctype=ctypeenum,
                )
                enum.opaque = False
                self.enums.append(enum)
                self.all.append(enum)
                self.output_order.append(("enum", enum))
            
            self.already_seen_enums.add(tag)
            
            for enumname, expr in ctypeenum.enumerators:
                constant = ConstantDescription(enumname, expr, src=(filename, lineno))
                self.constants.append(constant)
                self.all.append(constant)
                self.output_order.append(("constant", constant))
    
    def handle_macro(self, name, params, expr, filename, lineno):
        # Called from within DataCollectingParser
        src = (filename, lineno)
        
        if expr is None:
            expr = ConstantExpressionNode(True)
            constant = ConstantDescription(name, expr, src)
            self.constants.append(constant)
            self.all.append(constant)
            return
        
        if type(expr) is Attrib:
            return
        
        expr.visit(self)
        
        if isinstance(expr, CtypesType):
            if params:
                macro = MacroDescription(name, "", src)
                macro.error(
                    f"{macro.casual_name()} has parameters but evaluates to a type. Ctypesgen does not support it.",
                    cls="macro",
                )
                self.macros.append(macro)
                self.all.append(macro)
                self.output_order.append(("macro", macro))
            
            else:
                typedef = TypedefDescription(name, expr, src)
                self.typedefs.append(typedef)
                self.all.append(typedef)
                self.output_order.append(("typedef", typedef))
        
        elif name == "#undef":
            undef = UndefDescription(expr, src)
            self.all.append(undef)
            self.output_order.append(("undef", undef))
        else:
            macro = MacroDescription(name, params, expr, src)
            self.macros.append(macro)
            self.all.append(macro)
            self.output_order.append(("macro", macro))
        
        # Macros could possibly contain things like __FILE__, __LINE__, etc...
        # This could be supported, but it would be a lot of work and require a considerable amount of templates
    
    def handle_error(self, message, filename, lineno):
        # Called by CParser
        error_message(f"{filename}:{lineno}: {message}", cls="cparser")
    
    def handle_status(self, message):
        # Called by CParser
        status_message(message)
    
    def visit_struct(self, struct):
        self.handle_struct(struct, struct.src[0], struct.src[1])
    
    def visit_enum(self, enum):
        self.handle_enum(enum, enum.src[0], enum.src[1])
    
    def data(self):
        return DescriptionCollection(
            self.constants,
            self.typedefs,
            self.structs,
            self.enums,
            self.functions,
            self.variables,
            self.macros,
            self.all,
            self.output_order,
        )
