"""
ctypesgen.ctypedescs contains classes to represent a C type. All of them
classes are subclasses of CtypesType.

Unlike in previous versions of ctypesgen, CtypesType and its subclasses are
completely independent of the parser module.

The most important method of CtypesType and its subclasses is the py_string
method. str(ctype) returns a string which, when evaluated in the wrapper
at runtime, results in a ctypes type object.

For example, a CtypesType
representing an array of four integers could be created using:

>>> ctype = CtypesArray(CtypesSimple("int",True,0),4)

str(ctype) would evaluate to "c_int * 4".
"""

ctypes_type_map = {
    # typename   signed  longs
    ("void", True, 0): "None",
    ("int", True, 0): "c_int",
    ("int", False, 0): "c_uint",
    ("int", True, 1): "c_long",
    ("int", False, 1): "c_ulong",
    ("char", True, 0): "c_char",
    ("char", False, 0): "c_ubyte",
    ("short", True, 0): "c_short",
    ("short", False, 0): "c_ushort",
    ("float", True, 0): "c_float",
    ("double", True, 0): "c_double",
    ("double", True, 1): "c_longdouble",
    ("int8_t", True, 0): "c_int8",
    ("__int8_t", True, 0): "c_int8",
    ("__int8", True, 0): "c_int8",
    ("int16_t", True, 0): "c_int16",
    ("__int16_t", True, 0): "c_int16",
    ("__int16", True, 0): "c_int16",
    ("int32_t", True, 0): "c_int32",
    ("__int32_t", True, 0): "c_int32",
    ("__int32", True, 0): "c_int32",
    ("int64_t", True, 0): "c_int64",
    ("__int64", True, 0): "c_int64",
    ("__int64_t", True, 0): "c_int64",
    ("uint8_t", False, 0): "c_uint8",
    ("__uint8", False, 0): "c_uint8",
    ("__uint8_t", False, 0): "c_uint8",
    ("uint16_t", False, 0): "c_uint16",
    ("__uint16", False, 0): "c_uint16",
    ("__uint16_t", False, 0): "c_uint16",
    ("uint32_t", False, 0): "c_uint32",
    ("__uint32", False, 0): "c_uint32",
    ("__uint32_t", False, 0): "c_uint32",
    ("uint64_t", False, 0): "c_uint64",
    ("__uint64", False, 0): "c_uint64",
    ("__uint64_t", False, 0): "c_uint64",
    ("_Bool", True, 0): "c_bool",
}

ctypes_type_map_python_builtin = {
    ("int", True, -1): "c_short",
    ("int", False, -1): "c_ushort",
    ("int", True, 2): "c_longlong",
    ("int", False, 2): "c_ulonglong",
    ("size_t", True, 0): "c_size_t",
    ("off64_t", True, 0): "c_int64",
    ("wchar_t", True, 0): "c_wchar",
    ("ptrdiff_t", True, 0): "c_ssize_t",
    ("ssize_t", True, 0): "c_ssize_t",
    ("va_list", True, 0): "c_void_p",
}


# This protocol is used for walking type trees.
class CtypesTypeVisitor:
    def visit_struct(self, struct):
        pass

    def visit_enum(self, enum):
        pass

    def visit_typedef(self, name):
        pass

    def visit_error(self, error, cls):
        pass

    def visit_identifier(self, identifier):
        # This one comes from inside ExpressionNodes. There may be
        # ExpressionNode objects in array count expressions.
        pass


def visit_type_and_collect_info(ctype):
    class Visitor(CtypesTypeVisitor):
        def visit_struct(self, struct):
            structs.append(struct)

        def visit_enum(self, enum):
            enums.append(enum)

        def visit_typedef(self, typedef):
            typedefs.append(typedef)

        def visit_error(self, error, cls):
            errors.append((error, cls))

        def visit_identifier(self, identifier):
            identifiers.append(identifier)

    structs = []
    enums = []
    typedefs = []
    errors = []
    identifiers = []
    v = Visitor()
    ctype.visit(v)
    return structs, enums, typedefs, errors, identifiers


# Remove one level of indirection from function pointer; needed for typedefs
# and function parameters.
def remove_function_pointer(t):
    if type(t) == CtypesPointer and type(t.destination) == CtypesFunction:
        return t.destination
    elif type(t) == CtypesPointer:
        t.destination = remove_function_pointer(t.destination)
        return t
    else:
        return t


class CtypesType:
    def __init__(self):
        super(CtypesType, self).__init__()
        self.errors = []

    def __repr__(self):
        return f"<Ctype ({type(self).__name__}) '{self.py_string()}'>"

    def error(self, message, cls=None):
        self.errors.append((message, cls))

    def visit(self, visitor):
        for error, cls in self.errors:
            visitor.visit_error(error, cls)


class CtypesSimple(CtypesType):
    """Represents a builtin type, like "char" or "int"."""

    def __init__(self, name, signed, longs):
        super(CtypesSimple, self).__init__()
        self.name = name
        self.signed = signed
        self.longs = longs

    def py_string(self, ignore_can_be_ctype=None):
        return ctypes_type_map[(self.name, self.signed, self.longs)]


class CtypesSpecial(CtypesType):
    def __init__(self, name):
        super(CtypesSpecial, self).__init__()
        self.name = name

    def py_string(self, ignore_can_be_ctype=None):
        return self.name


class CtypesTypedef(CtypesType):
    """Represents a type defined by a typedef."""

    def __init__(self, name):
        super(CtypesTypedef, self).__init__()
        self.name = name

    def visit(self, visitor):
        if not self.errors:
            visitor.visit_typedef(self.name)
        super(CtypesTypedef, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        return self.name


class CtypesBitfield(CtypesType):
    def __init__(self, base, bitfield):
        super(CtypesBitfield, self).__init__()
        self.base = base
        self.bitfield = bitfield

    def visit(self, visitor):
        self.base.visit(visitor)
        super(CtypesBitfield, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        return self.base.py_string()


class CtypesPointer(CtypesType):
    def __init__(self, destination, qualifiers):
        super(CtypesPointer, self).__init__()
        self.destination = destination
        self.qualifiers = qualifiers

    def visit(self, visitor):
        if self.destination:
            self.destination.visit(visitor)
        super(CtypesPointer, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        return "POINTER(%s)" % self.destination.py_string()


class CtypesArray(CtypesType):
    def __init__(self, base, count):
        super(CtypesArray, self).__init__()
        self.base = base
        self.count = count

    def visit(self, visitor):
        self.base.visit(visitor)
        if self.count:
            self.count.visit(visitor)
        super(CtypesArray, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        if self.count is None:
            # In a function declaration, an empty array is equivalent to a pointer.
            # For struct FAMs, the ctypesparser changes count None to ConstantExpressionNode(0).
            return "POINTER(%s)" % self.base.py_string()
        if type(self.base) == CtypesArray:
            return "(%s) * int(%s)" % (self.base.py_string(), self.count.py_string(False))
        else:
            return "%s * int(%s)" % (self.base.py_string(), self.count.py_string(False))


class CtypesNoErrorCheck:
    def py_string(self, ignore_can_be_ctype=None):
        return "None"

    def __bool__(self):
        return False

    __nonzero__ = __bool__


class CtypesFunction(CtypesType):
    def __init__(self, restype, parameters, variadic, attrib=dict()):
        super(CtypesFunction, self).__init__()
        self.restype = restype
        self.errcheck = CtypesNoErrorCheck()
        self.argtypes = [remove_function_pointer(p) for p in parameters]
        self.variadic = variadic
        self.attrib = attrib

    def visit(self, visitor):
        self.restype.visit(visitor)
        for a in self.argtypes:
            a.visit(visitor)
        super(CtypesFunction, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        return "CFUNCTYPE(%s, %s)" % (
            self.restype.py_string(),
            ", ".join([a.py_string() for a in self.argtypes]),
        )


last_tagnum = 0

def anon_struct_tagnum():
    global last_tagnum
    last_tagnum += 1
    return last_tagnum


class CtypesStruct(CtypesType):
    def __init__(self, tag, attrib, variety, members, src=None):
        super(CtypesStruct, self).__init__()
        self.tag = tag
        self.attrib = attrib
        self.variety = variety  # "struct" or "union"
        self.members = members
        self.opaque = self.members is None
        self.src = src
        tag_is_int = type(self.tag) == int
        self.anonymous = tag_is_int or not self.tag
        if self.anonymous:
            self.tag = f"anon_{self.tag if tag_is_int else anon_struct_tagnum()}"
    

    def get_required_types(self):
        types = super(CtypesStruct, self).get_required_types()
        types.add((self.variety, self.tag))
        return types

    def visit(self, visitor):
        visitor.visit_struct(self)
        if not self.opaque:
            for name, ctype in self.members:
                ctype.visit(visitor)
        super(CtypesStruct, self).visit(visitor)

    def get_subtypes(self):
        return set() if self.opaque else {m[1] for m in self.members}

    def py_string(self, ignore_can_be_ctype=None):
        return f"{self.variety}_{self.tag}"


last_tagnum = 0

def anon_enum_tag():
    global last_tagnum
    last_tagnum += 1
    return f"anon_{last_tagnum}"


class CtypesEnum(CtypesType):
    def __init__(self, tag, enumerators, src=None):
        super(CtypesEnum, self).__init__()
        self.tag = tag
        self.anonymous = not self.tag
        if self.anonymous:
            self.tag = anon_enum_tag()
        self.enumerators = enumerators
        self.opaque = self.enumerators is None
        self.src = src

    def visit(self, visitor):
        visitor.visit_enum(self)
        super(CtypesEnum, self).visit(visitor)

    def py_string(self, ignore_can_be_ctype=None):
        return f"enum_{self.tag}"
