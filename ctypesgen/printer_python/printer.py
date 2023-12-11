import os
import os.path
import sys
import time
import shutil
from pathlib import Path
from textwrap import indent

from ctypesgen.ctypedescs import CtypesBitfield, CtypesStruct
from ctypesgen.expressions import ExpressionNode
from ctypesgen.messages import warning_message, status_message


THIS_DIR = Path(__file__).resolve().parent
CTYPESGEN_DIR = THIS_DIR.parent
PREAMBLE_PATH = THIS_DIR/"preamble.py"
DEFAULTHEADER_PATH = THIS_DIR/"defaultheader.py"
LIBRARYLOADER_PATH = CTYPESGEN_DIR/"libraryloader.py"


# TODO(geisserml) think out a proper concept for line breaks

class WrapperPrinter:
    def __init__(self, outpath, options, data):
        outpath = Path(outpath).resolve()
        status_message(f"Writing to {outpath}.")
        self.file = outpath.open("w")
        
        try:
            self.options = options
            self.lib_access = f"_libs['{self.options.library}']"
            
            # FIXME(geisserml) see below
            if self.options.strip_build_path and self.options.strip_build_path[-1] != os.path.sep:
                self.options.strip_build_path += os.path.sep
            
            if not self.options.embed_preamble:
                self.EXT_PREAMBLE = outpath.parent / "_ctg_preamble.py"
                self.EXT_LOADER = outpath.parent / "_ctg_loader.py"
                self._write_external_files()
            
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
            
            self.file.write("\n")
            self.print_group(self.options.inserted_files, "inserted files", self.insert_file)
        
        finally:
            self.file.close()
    
    
    def print_loader(self):
        if self.options.embed_preamble:
            self.file.write("# Begin loader template\n\n")
            with LIBRARYLOADER_PATH.open("r") as loader_file:
                shutil.copyfileobj(loader_file, self.file)
            self.file.write("\n# End loader template\n")
        else:
            self.file.write("from ._ctg_loader import _libs\n")

    def print_library(self, opts):
        
        if not opts.library:
            warning_message("No library name specified. Assuming pure headers without binary symbols.", cls="usage")
            return
        
        content = f"""
{self.lib_access} = _register_library(
    name = '{self.options.library}',
    dirs = {opts.runtime_libdirs},
    search_sys = {opts.allow_system_search},
    dllclass = '{opts.dllclass}',
)
"""
        if self.options.embed_preamble:
            self.file.write(content)
        else:
            loader_txt = self.EXT_LOADER.read_text()
            if f"{self.lib_access} = _register_library(" in loader_txt:
                status_message(f"Library already loaded in shared file, won't rewrite.")
            else:
                status_message(f"Adding library loader to shared file.")
                self.EXT_LOADER.write_text(f"{loader_txt}\n{content}")
    
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

    def srcinfo(self, src, wants_nl=True):
        
        if self.options.no_srcinfo or src is None:
            if wants_nl:
                self.file.write("\n")
            return
        
        filename, lineno = src
        if filename in ("<built-in>", "<command line>"):
            self.file.write("\n# %s\n" % filename)
        else:
            if self.options.strip_build_path and filename.startswith(self.options.strip_build_path):
                filename = filename[len(self.options.strip_build_path):]
            self.file.write("\n# %s: %s\n" % (filename, lineno))

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
        # TODO(geisserml) consider removing custom --header-template as bloat, always use default header?
        if self.options.header_template:
            template = Path(self.options.header_template).read_text()
        else:
            template = DEFAULTHEADER_PATH.read_text()
        self.file.write(template % self.template_subs())

    def print_preamble(self):
        self.file.write("# Begin preamble\n\n")
        if self.options.embed_preamble:
            with open(PREAMBLE_PATH, "r") as fsrc:
                shutil.copyfileobj(fsrc, self.file)
        else:
            self.file.write("from ._ctg_preamble import *\n")
            self.file.write("from ._ctg_preamble import _variadic_function\n")
        self.file.write("\n# End preamble\n")

    def _write_external_files(self):
        if not self.EXT_PREAMBLE.exists():
            shutil.copyfile(PREAMBLE_PATH, self.EXT_PREAMBLE)
        if not self.EXT_LOADER.exists():
            shutil.copyfile(LIBRARYLOADER_PATH, self.EXT_LOADER)

    def print_module(self, module):
        self.file.write("from %s import *\n" % module)
    
    def print_constant(self, constant):
        self.srcinfo(constant.src, wants_nl=False)
        self.file.write("%s = %s" % (constant.name, constant.value.py_string(False)))
    
    def _try_except_wrap(self, entry):
        pad = " "*4
        return f"try:\n{indent(entry, pad)}\nexcept Exception:\n{pad}pass"

    def print_undef(self, undef):
        self.srcinfo(undef.src)
        name = undef.macro.py_string(False)
        self.file.write(f"# undef {name}\n")
        entry = f"del {name}"
        if self.options.guard_macros:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)

    def print_typedef(self, typedef):
        self.srcinfo(typedef.src, wants_nl=False)
        self.file.write("%s = %s" % (typedef.name, typedef.ctype.py_string()))

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

        self.file.write(tab + f"__slots__ = {[n for n, _ in struct.members]}")

    def print_struct_members(self, struct):
        # Fields are defined indepedent of the actual class to handle things like self-references, cyclic struct references and forward declarations
        # https://docs.python.org/3/library/ctypes.html#incomplete-types
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
        self.srcinfo(enum.src, wants_nl=False)
        # NOTE Values of enumerator are output as constants
        self.file.write("enum_%s = c_int" % enum.tag)
    
    def _needs_guard(self, symbol):
        needs_guard = self.options.guard_symbols or getattr(symbol, "is_missing", False)
        return needs_guard
    
    def print_function(self, function):
        assert self.options.library, "Binary symbol requires library"
        self.srcinfo(function.src)
        needs_guard = self._needs_guard(function)
        pad = " "*4 if needs_guard else ""
        if needs_guard:
            self.file.write(
                "if hasattr({L}, '{CN}'):\n".format(L=self.lib_access, CN=function.c_name())
            )
        if function.variadic:
            self._print_variadic_function(function, pad)
        else:
            self._print_fixed_function(function, pad)
    
    
    def _print_fixed_function(self, function, pad):
        self.file.write(indent(
            '{PN} = {L}.{CN}\n'.format(L=self.lib_access, CN=function.c_name(), PN=function.py_name()) +
            "{PN}.argtypes = [{ATS}]\n".format(PN=function.py_name(), ATS=", ".join([a.py_string() for a in function.argtypes])) +
            "{PN}.restype = {RT}".format(PN=function.py_name(), RT=function.restype.py_string()),
            prefix=pad,
        ))
        if function.errcheck:
            self.file.write(
                "\n" + pad + "{PN}.errcheck = {EC}".format(PN=function.py_name(), EC=function.errcheck.py_string())
            )
    
    def _print_variadic_function(self, function, pad):
        # TODO see if we can remove the _variadic_function wrapper and use just plain ctypes
        self.file.write(indent(
            '_func = {L}.{CN}\n'
            "_restype = {RT}\n"
            "_errcheck = {E}\n"
            "_argtypes = [{ATS}]\n"
            "{PN} = _variadic_function(_func,_restype,_argtypes,_errcheck)\n".format(
                L=self.lib_access,
                CN=function.c_name(),
                RT=function.restype.py_string(),
                E=function.errcheck.py_string(),
                ATS=", ".join([a.py_string() for a in function.argtypes]),
                PN=function.py_name(),
            ),
            prefix=pad,
        ))

    def print_variable(self, variable):
        assert self.options.library, "Binary symbol requires library"
        self.srcinfo(variable.src)
        entry = '{PN} = ({PS}).in_dll({L}, "{CN}")'.format(
            PN=variable.py_name(),
            PS=variable.ctype.py_string(),
            L=self.lib_access,
            CN=variable.c_name(),
        )
        if self._needs_guard(variable):
            entry = self._try_except_wrap(entry)
        self.file.write(entry)

    def print_macro(self, macro):
        # important: must check precisely against None because params may be an empty list for a func macro
        if macro.params is None:
            self.print_simple_macro(macro)
        else:
            self.print_func_macro(macro)

    def print_simple_macro(self, macro):
        self.srcinfo(macro.src, wants_nl=self.options.guard_macros)
        entry = "{MN} = {ME}".format(MN=macro.name, ME=macro.expr.py_string(True))
        if self.options.guard_macros:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)

    def print_func_macro(self, macro):
        self.srcinfo(macro.src)
        self.file.write(
            "def {MN}({MP}):\n"
            "    return {ME}".format(
                MN=macro.name, MP=", ".join(macro.params), ME=macro.expr.py_string(True)
            )
        )
    
    def insert_file(self, filepath):
        self.file.write(f"# Begin '{filepath}'\n\n")
        with open(filepath, "r") as fh:
            shutil.copyfileobj(fh, self.file)
        self.file.write(f"\n# End '{filepath}'\n")
