import shutil
from pathlib import Path
from textwrap import indent
from contextlib import contextmanager

from ctypesgen.ctypedescs import CtypesBitfield, CtypesStruct
from ctypesgen.expressions import ExpressionNode
from ctypesgen.messages import warning_message, status_message


THIS_DIR = Path(__file__).resolve().parent
CTYPESGEN_DIR = THIS_DIR.parent
PREAMBLE_PATH = THIS_DIR/"preamble.py"
DEFAULTHEADER_PATH = THIS_DIR/"defaultheader.py"
LIBRARYLOADER_PATH = CTYPESGEN_DIR/"libraryloader.py"


def ParagraphCtxFactory(file):
    @contextmanager
    def paragraph_ctx(txt):
        file.write(f"# -- Begin {txt} --\n\n")
        try:
            yield
        finally:
            file.write(f"\n# -- End {txt} --\n")
    return paragraph_ctx


# TODO(geisserml) think out a proper concept for line breaks

class WrapperPrinter:
    def __init__(self, outpath, options, data, argv):
        outpath = Path(outpath).resolve()
        status_message(f"Writing to {outpath}.")
        self.file = outpath.open("w")
        
        try:
            self.options = options
            self.paragraph_ctx = ParagraphCtxFactory(self.file)
            
            if not self.options.embed_preamble:
                self.EXT_PREAMBLE = outpath.parent / "_ctg_preamble.py"
                self.EXT_LOADER = outpath.parent / "_ctg_loader.py"
                self._write_external_files()
            
            self.print_info(argv)
            self.file.write("\n")
            
            self.print_preamble()
            self.file.write("\n")
            
            if self.options.library:
                
                self.print_loader()
                self.file.write("\n")
                
                self.print_library(self.options)
                self.file.write("\n")
            
            else:
                warning_message("No library name specified. Assuming pure headers without binary symbols.", cls="usage")
            
            self.print_group(self.options.modules, self.print_module, "modules")
            self.file.write("\n")
            
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
            self.print_group(self.options.inserted_files, self.insert_file, "inserted files")
        
        finally:
            self.file.close()
    
    
    def _embed_file(self, fp, desc):
        with self.paragraph_ctx(desc), open(fp, "r") as src_fh:
            shutil.copyfileobj(src_fh, self.file)
    
    # sort descending by length to avoid interference
    _PRIVATE_PATHS_TABLE = [(str(p), s) for p, s in [(Path.cwd(), "."), (Path.home(), "~")]]
    _PRIVATE_PATHS_TABLE.sort(key=lambda x: len(x[0]), reverse=True)
    
    @classmethod
    def _strip_private_paths(cls, txt):
        for p, s in cls._PRIVATE_PATHS_TABLE:
            txt = txt.replace(p, s)
        return txt
    
    
    def print_info(self, argv):
        # TODO(py38) consider shlex.join()
        argv_str = ' '.join([f'"{a}"' if ' ' in a else a for a in argv])
        argv_str = self._strip_private_paths(argv_str)
        self.file.write(
            f"# Auto-generated by: ctypesgen {argv_str}\n"
        )
    
    
    def print_loader(self):
        if self.options.embed_preamble:
            self._embed_file(LIBRARYLOADER_PATH, "loader template")
        else:
            self.file.write("from ._ctg_loader import _libs\n")
    
    
    def print_library(self, opts):
        name_define = f"name = '{self.options.library}'"
        content = f"""\
_register_library(
    {name_define},
    dllclass = ctypes.{opts.dllclass},
    dirs = {opts.runtime_libdirs},
    search_sys = {opts.search_sys},
)
"""
        if self.options.embed_preamble:
            self.file.write(content)
        else:
            loader_txt = self.EXT_LOADER.read_text()
            if name_define in loader_txt:
                status_message(f"Library already loaded in shared file, won't rewrite.")
            else:
                # we need to share libraries in a common file so we can build same-library headers separately while loading the library only once
                status_message(f"Adding library loader to shared file.")
                self.EXT_LOADER.write_text(f"{loader_txt}\n\n{content}")
    
    
    def print_group(self, list, function, name):
        if list:
            with self.paragraph_ctx(name):
                for obj in list:
                    function(obj)
                self.file.write(f"\n# {len(list)} {name}\n")
        else:
            self.file.write(f"# -- No {name} --\n")
    
    
    def srcinfo(self, src, wants_nl=True):
        
        if self.options.no_srcinfo or src is None:
            if wants_nl:
                self.file.write("\n")
            return
        
        filepath, lineno = src
        if filepath in ("<built-in>", "<command line>"):
            self.file.write("\n# %s\n" % filepath)
        else:
            filepath = self._strip_private_paths(str(filepath))
            self.file.write("\n# %s: %s\n" % (filepath, lineno))
    
    
    def print_preamble(self):
        if self.options.embed_preamble:
            self._embed_file(PREAMBLE_PATH, "preamble")
        else:
            self.file.write("from ._ctg_preamble import *\n")
    
    
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
    
    
    def print_function(self, function):
        assert self.options.library, "Binary symbol requires --library LIBNAME"
        self.srcinfo(function.src)
        
        # we have to do string based attribute access because the CN might conflict with a python keyword, while the PN is supposed to be renamed
        template = """\
{PN} = _libs['{L}']['{CN}']
{PN}.argtypes = [{ATS}]
{PN}.restype = {RT}\
"""
        fields = dict(
            L=self.options.library,
            CN=function.c_name(),
            PN=function.py_name(),
            ATS=", ".join([a.py_string() for a in function.argtypes]),
            RT=function.restype.py_string(),
        )
        if function.errcheck:
            template += "\n{PN}.errcheck = {EC}"
            fields["EC"] = function.errcheck.py_string()
        
        if self.options.guard_symbols:
            template = "if hasattr(_libs['{L}'], '{CN}'):\n" + indent(template, prefix=" "*4)
        if function.variadic:
            template = "# Variadic function '{CN}'\n" + template
        
        self.file.write(template.format(**fields))
    
    
    def print_variable(self, variable):
        assert self.options.library, "Binary symbol requires --library LIBNAME"
        self.srcinfo(variable.src)
        entry = "{PN} = ({PS}).in_dll(_libs['{L}'], '{CN}')".format(
            PN=variable.py_name(),
            PS=variable.ctype.py_string(),
            L=self.options.library,
            CN=variable.c_name(),
        )
        if self.options.guard_symbols:
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
        self._embed_file(filepath, f"inserted file '{filepath}'")
