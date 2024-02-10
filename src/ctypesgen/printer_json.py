import json
from ctypesgen.ctypedescs import CtypesBitfield


# From:
# http://stackoverflow.com/questions/1036409/recursively-convert-python-object-graph-to-dictionary
def todict(obj, classkey="Klass"):
    if isinstance(obj, dict):
        for k in obj.keys():
            obj[k] = todict(obj[k], classkey)
        return obj
    elif isinstance(obj, str) or isinstance(obj, bytes):
        # must handle strings before __iter__
        return obj
    elif hasattr(obj, "__iter__"):
        return [todict(v, classkey) for v in obj]
    elif hasattr(obj, "__dict__"):
        data = dict(
            [
                (key, todict(value, classkey))
                for key, value in obj.__dict__.items()
                if not callable(value) and not key.startswith("_")
            ]
        )
        if classkey is not None and hasattr(obj, "__class__"):
            data[classkey] = obj.__class__.__name__
        return data
    else:
        return obj


class WrapperPrinter:
    def __init__(self, outpath, options, data, argv):
        self.options = options

        self.print_library(self.options.library)
        method_table = {
            "function": self.print_function,
            "macro": self.print_macro,
            "struct": self.print_struct,
            "struct_fields": self.print_struct_fields,
            "typedef": self.print_typedef,
            "variable": self.print_variable,
            "enum": self.print_enum,
            "constant": self.print_constant,
            "undef": self.print_undef,
        }

        res = []
        for kind, desc in data:
            item = method_table[kind](desc)
            if item: res.append(item)
        with outpath.open("w", encoding="utf-8") as fh:
            fh.write(json.dumps(res, sort_keys=True, indent=4))
            fh.write("\n")

    def print_library(self, library):
        return {"load_library": library}

    def print_constant(self, constant):
        return {"type": "constant", "name": constant.name, "value": constant.value.py_string(False)}

    def print_undef(self, undef):
        return {"type": "undef", "value": undef.macro.py_string(False)}

    def print_typedef(self, typedef):
        return {"type": "typedef", "name": typedef.name, "ctype": todict(typedef.ctype)}

    def print_struct(self, struct):
        res = {"type": struct.variety, "name": struct.tag, "attrib": struct.attrib}
        if not struct.opaque:
            res["fields"] = []
            for name, ctype in struct.members:
                field = {"name": name, "ctype": todict(ctype)}
                if isinstance(ctype, CtypesBitfield):
                    field["bitfield"] = ctype.bitfield.py_string(False)
                res["fields"].append(field)
        return res

    def print_struct_fields(self, struct):
        pass  # FIXME loses info about forward declarations?

    def print_enum(self, enum):
        res = {"type": "enum", "name": enum.tag}

        if not enum.opaque:
            res["fields"] = []
            for name, ctype in enum.members:
                field = {"name": name, "ctype": todict(ctype)}
                res["fields"].append(field)
        return res

    def print_function(self, function):
        res = {
            "type": "function",
            "name": function.c_name(),
            "variadic": function.variadic,
            "args": todict(function.argtypes),
            "return": todict(function.restype),
            "attrib": function.attrib,
        }
        if self.options.library:
            res["source"] = self.options.library
        return res

    def print_variable(self, variable):
        res = {"type": "variable", "ctype": todict(variable.ctype), "name": variable.c_name()}
        if self.options.library:
            res["source"] = self.options.library
        return res

    def print_macro(self, macro):
        if macro.params:
            return {
                "type": "macro_function",
                "name": macro.name,
                "args": macro.params,
                "body": macro.expr.py_string(True),
            }
        else:
            # The macro translator makes heroic efforts but it occasionally fails.
            # Beware the contents of the value!
            return {"type": "macro", "name": macro.name, "value": macro.expr.py_string(True)}
