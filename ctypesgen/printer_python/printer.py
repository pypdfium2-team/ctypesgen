import os
import os.path
import sys
import time
import shutil
from os.path import join
from textwrap import indent

from ctypesgen.ctypedescs import CtypesBitfield, CtypesStruct
from ctypesgen.expressions import ExpressionNode
from ctypesgen.messages import error_message, warning_message, status_message


THIS_DIR = os.path.dirname(__file__)
CTYPESGEN_DIR = join(THIS_DIR, os.path.pardir)
PREAMBLE_PATH = join(THIS_DIR, "preamble.py")
DEFAULTHEADER_PATH = join(THIS_DIR, "defaultheader.py")
LIBRARYLOADER_PATH = join(CTYPESGEN_DIR, "libraryloader.py")


# TODO(geisserml) think out a proper concept for line breaks
# TODO(geisserml) consider to remove or rewrite --no-embed-preamble

class WrapperPrinter:
    def __init__(self, outpath, options, data):
        status_message("Writing to %s." % (outpath or "stdout"))
        self.file = open(outpath, "w") if outpath else sys.stdout
        
        try:
            self.options = options
            
            # FIXME(geisserml) see below
            if self.options.strip_build_path and self.options.strip_build_path[-1] != os.path.sep:
                self.options.strip_build_path += os.path.sep
            
            if not self.options.embed_preamble and outpath:
                self._copy_preamble_loader_files(outpath)
            
            self.print_header()
            self.file.write("\n")
            
            self.print_preamble()
            self.file.write("\n")
            
            self.print_loader()
            self.file.write("\n")
            
            self.print_library(self.options)
            self.file.write("\n")
            self.print_group(self.options.modules, "modules", self.print_module)
            
            method_table = {
                "function": self.print_function,
                "macro": self.print_macro,
                "struct": self.print_struct,
                "struct-body": self.print_struct_members,
                "typedef": self.print_typedef,
                "variable": self.print_variable,
                "enum": self.print_enum,
                "constant": self.print_constant,
                "undef": self.print_undef,
            }
            
            for kind, desc in data.output_order:
                if desc.included:
                    method_table[kind](desc)
                    self.file.write("\n")
            
            self.print_group(self.options.inserted_files, "inserted files", self.insert_file)
        
        finally:
            if self.file != sys.stdout:
                self.file.close()
    
    
    def print_loader(self):
        if self.options.embed_preamble:
            self.file.write("# Begin loader template\n\n")
            with open(LIBRARYLOADER_PATH, "r") as loader_file:
                self.file.write(loader_file.read())
            self.file.write("\n# End loader template")
        else:
            self.file.write("from .ctypes_loader import _find_library\n\n")

    def print_library(self, opts):
        if not opts.library:
            notice = "No library name specified. Assuming pure headers without binary symbols."
            warning_message(notice, cls="usage")
            self.file.write(f'\nwarnings.warn("{notice}")\n')
        else:
            loader_info = dict(
                libname = opts.library,
                libdirs = opts.runtime_libdirs,
                allow_system_search = opts.allow_system_search,
            )
            self.file.write("""
# Begin library load

_loader_info = %s
_loader_info["libpath"] = _find_library(**_loader_info)
assert _loader_info["libpath"], f"Could not find library with config {_loader_info}"
_lib = ctypes.CDLL(_loader_info["libpath"])

# End library load
""" % (loader_info, )
            )
    
    def print_group(self, list, name, function):
        if list:
            self.file.write("# Begin %s\n" % name)
            for obj in list:
                function(obj)
            self.file.write("\n")
            self.file.write("# %d %s\n" % (len(list), name))
            self.file.write("# End %s\n" % name)
        else:
            self.file.write("# No %s\n" % name)
        self.file.write("\n")

    def srcinfo(self, src, inline=False):
        
        if self.options.no_srcinfo or src is None:
            if not inline:
                self.file.write("\n")
            return
        
        filename, lineno = src
        pad = "  " if inline else "\n"
        if filename in ("<built-in>", "<command line>"):
            self.file.write(pad + "# %s" % filename)
        else:
            if self.options.strip_build_path and filename.startswith(self.options.strip_build_path):
                filename = filename[len(self.options.strip_build_path):]
            self.file.write(pad + "# %s: %s" % (filename, lineno))
        
        if not inline:
            self.file.write("\n")

    def template_subs(self):
        # TODO(geisserml) address BUG(160)
        template_subs = {
            "date": time.ctime(),
            "argv": " ".join([x for x in sys.argv if not x.startswith("--strip-build-path")]),
            "name": os.path.basename(self.options.headers[0]),
        }

        # NOTE not used by default header; % formatting ignores superfluous members
        for opt, value in self.options.__dict__.items():
            if type(value) == str:
                template_subs[opt] = value
            elif isinstance(value, (list, tuple)):
                template_subs[opt] = (os.path.sep).join(value)
            else:
                template_subs[opt] = repr(value)

        return template_subs

    def print_header(self):
        template_file = None

        if self.options.header_template:
            path = self.options.header_template
            try:
                template_file = open(path, "r")
            except IOError:
                error_message(
                    f"Cannot load header template from file '{path}' - using default template.",
                    cls="missing-file",
                )

        if not template_file:
            template_file = open(DEFAULTHEADER_PATH, "r")

        template_subs = self.template_subs()
        self.file.write(template_file.read() % template_subs)

        template_file.close()

    def print_preamble(self):
        self.file.write("# Begin preamble\n\n")
        if self.options.embed_preamble:
            with open(PREAMBLE_PATH, "r") as preamble_file:
                filecontent = preamble_file.read()
                filecontent = filecontent.replace("# ~POINTER~", "").strip() + "\n"
                self.file.write(filecontent)
        else:
            self.file.write("from .ctypes_preamble import *\n")
            self.file.write("from .ctypes_preamble import _variadic_function\n")

        self.file.write("\n# End preamble\n")

    def _copy_preamble_loader_files(self, path):
        if os.path.isfile(path):
            dst = os.path.dirname(os.path.abspath(path))
        else:
            error_message(
                "Cannot copy preamble and loader files",
                cls="missing-file",
            )
            return

        c_preamblefile = join(dst, "ctypes_preamble.py")
        if os.path.isfile(c_preamblefile):
            return

        pointer = """def POINTER(obj):
    p = ctypes.POINTER(obj)

    # Convert None to a real NULL pointer to work around bugs
    # in how ctypes handles None on 64-bit platforms
    if not isinstance(p.from_param, classmethod):

        def from_param(cls, x):
            if x is None:
                return cls()
            else:
                return x

        p.from_param = classmethod(from_param)

    return p

"""

        with open(PREAMBLE_PATH) as preamble_file:
            preamble_file_content = preamble_file.read()
            filecontent = preamble_file_content.replace("# ~POINTER~", pointer).strip() + "\n"

        with open(c_preamblefile, "w") as f:
            f.write(filecontent)

        shutil.copyfile(LIBRARYLOADER_PATH, join(dst, "ctypes_loader.py"))

    def print_module(self, module):
        self.file.write("from %s import *\n" % module)

    def print_constant(self, constant):
        self.file.write("%s = %s" % (constant.name, constant.value.py_string(False)))
        self.srcinfo(constant.src, inline=True)

    def print_undef(self, undef):
        # TODO remove try/except, or use only if --guard-symbols given
        self.srcinfo(undef.src)
        self.file.write(
            "# #undef {macro}\n"
            "try:\n"
            "    del {macro}\n"
            "except NameError:\n"
            "    pass\n".format(macro=undef.macro.py_string(False))
        )

    def print_typedef(self, typedef):
        self.file.write("%s = %s" % (typedef.name, typedef.ctype.py_string()))
        self.srcinfo(typedef.src, inline=True)

    def print_struct(self, struct):
        self.srcinfo(struct.src)
        base = {"union": "Union", "struct": "Structure"}[struct.variety]
        
        self.file.write(f"class {struct.variety}_{struct.tag} ({base}):\n")
        tab = " "*4
        
        if struct.opaque:
            self.file.write(tab + "pass")
            return

        # is this supposed to be packed?
        if struct.attrib.get("packed", False):
            aligned = struct.attrib.get("aligned", [1])
            assert len(aligned) == 1, "cgrammar gave more than one arg for aligned attribute"
            aligned = aligned[0]
            if isinstance(aligned, ExpressionNode):
                # TODO: for non-constant expression nodes, this will fail:
                aligned = aligned.evaluate(None)
            self.file.write(tab + f"_pack_ = {aligned}\n")

        # handle unnamed fields.
        unnamed_fields = []
        names = set([x[0] for x in struct.members])
        anon_prefix = "unnamed_"
        n = 1
        for mi in range(len(struct.members)):
            mem = list(struct.members[mi])
            if mem[0] is None:
                while True:
                    name = "%s%i" % (anon_prefix, n)
                    n += 1
                    if name not in names:
                        break
                mem[0] = name
                names.add(name)
                if type(mem[1]) is CtypesStruct:
                    unnamed_fields.append(name)
                struct.members[mi] = mem
        
        if len(unnamed_fields) > 0:
            self.file.write(tab + f"_anonymous_ = {unnamed_fields}\n")

        self.file.write(tab + f"__slots__ = {[n for n, _ in struct.members]}\n")

    def print_struct_members(self, struct):
        # Fields must be defined indepedent of the actual class to handle self-references, cyclic struct references and forward declarations
        self.file.write("%s_%s._fields_ = [\n" % (struct.variety, struct.tag))
        for name, ctype in struct.members:
            if isinstance(ctype, CtypesBitfield):
                self.file.write(
                    "    ('%s', %s, %s),\n"
                    % (name, ctype.py_string(), ctype.bitfield.py_string(False))
                )
            else:
                self.file.write("    ('%s', %s),\n" % (name, ctype.py_string()))
        self.file.write("]")

    def print_enum(self, enum):
        self.file.write("enum_%s = c_int" % enum.tag)
        self.srcinfo(enum.src, inline=True)
        # Values of enumerator are output as constants.

    def print_function(self, function):
        if function.variadic:
            self.print_variadic_function(function)
        else:
            self.print_fixed_function(function)

    def print_fixed_function(self, function):
        self.srcinfo(function.src)

        # NOTE pypdfium2-ctypesgen currently does not support the windows-only stdcall convention
        # this could theoretically be done by adding a second library handle _lib_stdcall = ctypes.WinDLL(...) on windows and using that for stdcall functions
        # see also https://github.com/pypdfium2-team/ctypesgen/issues/1
        assert not function.attrib.get("stdcall", False)
        
        pad = " "*4 if self.options.guard_symbols else ""
        if self.options.guard_symbols:
            self.file.write(
                'if hasattr(_lib, "{CN}"):\n'.format(CN=function.c_name())
            )
        
        self.file.write(indent(
            '{PN} = _lib.{CN}\n'.format(CN=function.c_name(), PN=function.py_name()) +
            "{PN}.argtypes = [{ATS}]\n".format(PN=function.py_name(), ATS=", ".join([a.py_string() for a in function.argtypes])) +
            "{PN}.restype = {RT}".format(PN=function.py_name(), RT=function.restype.py_string()),
            prefix=pad,
        ))
        if function.errcheck:
            self.file.write(
                "\n" + pad + "{PN}.errcheck = {EC}".format(PN=function.py_name(), EC=function.errcheck.py_string())
            )
    
    def print_variadic_function(self, function):
        # TODO see if we can remove the _variadic_function wrapper and use just plain ctypes
        
        assert not function.attrib.get("stdcall", False)
        self.srcinfo(function.src)
        
        pad = " "*4 if self.options.guard_symbols else ""
        if self.options.guard_symbols:
            self.file.write(
                'if hasattr(_lib, {CN}):\n'.format(CN=function.c_name())
            )
        
        self.file.write(indent(
            '_func = _lib.{CN}\n'
            "_restype = {RT}\n"
            "_errcheck = {E}\n"
            "_argtypes = [{ATS}]\n"
            "{PN} = _variadic_function(_func,_restype,_argtypes,_errcheck)\n".format(
                CN=function.c_name(),
                RT=function.restype.py_string(),
                E=function.errcheck.py_string(),
                ATS=", ".join([a.py_string() for a in function.argtypes]),
                PN=function.py_name(),
            ),
            prefix=pad,
        ))

    def print_variable(self, variable):
        # TODO consider to remove try/except, or use only if guard_symbols is True
        self.srcinfo(variable.src)
        self.file.write(
            "try:\n"
            '    {PN} = ({PS}).in_dll(_lib, "{CN}")\n'
            "except:\n"
            "    pass\n".format(
                PN=variable.py_name(),
                PS=variable.ctype.py_string(),
                CN=variable.c_name(),
            )
        )

    def print_macro(self, macro):
        if macro.params:
            self.print_func_macro(macro)
        else:
            self.print_simple_macro(macro)

    def print_simple_macro(self, macro):
        # NOTE(geisserml) previously, macros had a try/except wrapper - we removed it
        # broken macros should be skipped explicitly and the respective issue may be reported
        # -> TODO consider re-introducing try/except if guard_symbols is True
        self.file.write(
            "{MN} = {ME}".format(MN=macro.name, ME=macro.expr.py_string(True))
        )
        self.srcinfo(macro.src, inline=True)

    def print_func_macro(self, macro):
        self.srcinfo(macro.src)
        self.file.write(
            "def {MN}({MP}):\n"
            "    return {ME}".format(
                MN=macro.name, MP=", ".join(macro.params), ME=macro.expr.py_string(True)
            )
        )
    
    def insert_file(self, filename):
        try:
            inserted_file = open(filename, "r")
        except IOError:
            error_message('Cannot open file "%s". Skipped it.' % filename, cls="missing-file")

        self.file.write(
            '# Begin "{filename}"\n'
            "\n{file}\n"
            '# End "{filename}"\n'.format(filename=filename, file=inserted_file.read())
        )

        inserted_file.close()
