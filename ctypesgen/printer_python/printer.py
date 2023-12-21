import shutil
from pathlib import Path
from textwrap import indent
from contextlib import contextmanager

from ctypesgen.ctypedescs import CtypesBitfield, CtypesStruct
from ctypesgen.expressions import ExpressionNode
from ctypesgen.messages import warning_message, status_message


# Newlines policy for the python printer:
#
# - Under no circumstances shall any entry end with \n. Instead, use leading \n in separator fashion.
# - Note that the body of Paragraph Contexts may end with a newline for a padding before the End marker. This does not violate the rule, because the resulting paragraph (with markers) will *not* end with \n.
# - As a rule of thumb, avoid initial \n's in sub-methods. Instead, try to leave the connection work to the root parser, which is more flexible (imagine what would happen if it were conditional what goes in the first line). However, exceptions may be made where it makes sense.
# - The file as a whole shall have a trailing \n.


THIS_DIR = Path(__file__).resolve().parent
CTYPESGEN_DIR = THIS_DIR.parent
PREAMBLE_PATH = THIS_DIR/"preamble.py"
DEFAULTHEADER_PATH = THIS_DIR/"defaultheader.py"
LIBRARYLOADER_PATH = CTYPESGEN_DIR/"libraryloader.py"


def ParagraphCtxFactory(file):
    @contextmanager
    def paragraph_ctx(txt):
        file.write(f"# -- Begin {txt} --")
        try:
            yield
        finally:
            file.write(f"\n# -- End {txt} --")
    return paragraph_ctx


class WrapperPrinter:
    
    def __init__(self, outpath, options, data, argv):
        outpath = Path(outpath).resolve()
        status_message(f"Writing to {outpath}.")
        self.file = outpath.open("w", encoding="utf-8")
        
        try:
            self.options = options
            self.paragraph_ctx = ParagraphCtxFactory(self.file)
            
            self.print_info(argv)
            self.file.write("\n\n")
            self.print_templates(self.options, outpath)
            
            if self.options.library:
                # print_library() handles newlines internally, because it does not write to this file at all if embed_preamble is False
                self.print_library(self.options)
            else:
                warning_message("No library name specified. Assuming pure headers without binary symbols.", cls="usage")
            
            if self.options.modules:
                self.file.write("\n\n\n# Linked modules")
                for mod in self.options.modules:
                    self.file.write("\n")
                    self.print_module(mod)
            
            self.file.write("\n\n\n")
            with self.paragraph_ctx("header members"):
                for kind, desc in data.output_order:
                    if not desc.included:
                        continue
                    self.file.write("\n")
                    self._handle_srcinfo(kind, desc)
                    self.file.write("\n")
                    getattr(self, f"print_{kind}")(desc)
                self.file.write("\n")
            
            for fp in self.options.inserted_files:
                self.file.write("\n\n\n")
                self.insert_file(fp)
            
            self.file.write("\n")
        
        finally:
            self.file.close()
    
    
    # this is outsourced on behalf of root parser readability
    def _handle_srcinfo(self, kind, desc):
        if not desc.src or kind == "struct_fields":
            return
        filepath, lineno = desc.src
        if filepath in ("<built-in>", "<command line>"):
            self.file.write("\n# %s" % filepath)
        else:
            filepath = self._strip_private_paths(str(filepath))
            self.file.write("\n# %s: %s" % (filepath, lineno))
    
    
    # sort descending by length to avoid interference
    _PRIVATE_PATHS_TABLE = [(str(p), s) for p, s in [(Path.cwd(), "."), (Path.home(), "~")]]
    _PRIVATE_PATHS_TABLE.sort(key=lambda x: len(x[0]), reverse=True)
    
    @classmethod
    def _strip_private_paths(cls, txt):
        for p, s in cls._PRIVATE_PATHS_TABLE:
            txt = txt.replace(p, s)
        return txt
    
    def _embed_file(self, fp, desc):
        with self.paragraph_ctx(desc), open(fp, "r") as src_fh:
            self.file.write("\n\n")
            shutil.copyfileobj(src_fh, self.file)
    
    def _try_except_wrap(self, entry):
        pad = " "*4
        return f"try:\n{indent(entry, pad)}\nexcept Exception:\n{pad}pass"
    
    
    def print_info(self, argv):
        # TODO(py38) consider shlex.join()
        argv_str = ' '.join([f'"{a}"' if ' ' in a else a for a in argv])
        argv_str = self._strip_private_paths(argv_str)
        self.file.write(f"# Auto-generated by: ctypesgen {argv_str}")
    
    
    def print_templates(self, opts, outpath):
        if opts.embed_preamble:
            self._embed_file(PREAMBLE_PATH, "preamble")
            if opts.library:
                self.file.write("\n\n\n")
                self._embed_file(LIBRARYLOADER_PATH, "loader template")
        else:
            self.EXT_PREAMBLE = outpath.parent / "_ctg_preamble.py"
            self.EXT_LOADER = outpath.parent / "_ctg_loader.py"
            if not self.EXT_PREAMBLE.exists():
                shutil.copyfile(PREAMBLE_PATH, self.EXT_PREAMBLE)
            if not self.EXT_LOADER.exists():
                shutil.copyfile(LIBRARYLOADER_PATH, self.EXT_LOADER)
            self.file.write("from ._ctg_preamble import *")
            if opts.library:
                self.file.write("\nfrom ._ctg_loader import _libs")
    
    
    def print_library(self, opts):
        name_define = f"name = '{opts.library}'"
        content = f"""\
# Load library '{opts.library}'
_register_library(
    {name_define},
    dllclass = ctypes.{opts.dllclass},
    dirs = {opts.runtime_libdirs},
    search_sys = {opts.search_sys},
)\
"""
        if opts.embed_preamble:
            self.file.write(f"\n\n\n{content}")
        else:
            loader_txt = self.EXT_LOADER.read_text()
            if name_define in loader_txt:
                status_message(f"Library already loaded in shared file, won't rewrite.")
            else:
                # we need to share libraries in a common file so we can build same-library headers separately while loading the library only once
                status_message(f"Adding library loader to shared file.")
                self.EXT_LOADER.write_text(f"{loader_txt}\n\n{content}\n")
    
    
    def print_module(self, module):
        self.file.write("from %s import *" % module)
    
    
    def print_function(self, function):
        assert self.options.library, "Binary symbol requires --library LIBNAME"
        
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
    
    
    def print_struct(self, struct):
        base = {"union": "Union", "struct": "Structure"}[struct.variety]
        self.file.write(f"class {struct.variety}_{struct.tag} ({base}):")
        pad = "\n" + " "*4
        
        if struct.opaque:
            self.file.write(pad + "pass")
            return
        
        # is this supposed to be packed?
        if struct.attrib.get("packed", False):
            aligned = struct.attrib.get("aligned", [1])
            assert len(aligned) == 1, "cgrammar gave more than one arg for aligned attribute"
            aligned = aligned[0]
            if isinstance(aligned, ExpressionNode):
                # TODO: for non-constant expression nodes, this will fail:
                aligned = aligned.evaluate(None)
            self.file.write(pad + f"_pack_ = {aligned}")
        
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
            self.file.write(pad + f"_anonymous_ = {unnamed_fields}")
        
        self.file.write(pad + f"__slots__ = {[n for n, _ in struct.members]}")
    
    def print_struct_fields(self, struct):
        # Fields are defined indepedent of the actual class to handle things like self-references, cyclic struct references and forward declarations
        # https://docs.python.org/3/library/ctypes.html#incomplete-types
        self.file.write("%s_%s._fields_ = [" % (struct.variety, struct.tag))
        for name, ctype in struct.members:
            if isinstance(ctype, CtypesBitfield):
                self.file.write(
                    "\n    ('%s', %s, %s),"
                    % (name, ctype.py_string(), ctype.bitfield.py_string(False))
                )
            else:
                self.file.write("\n    ('%s', %s)," % (name, ctype.py_string()))
        self.file.write("\n]")
    
    
    def print_enum(self, enum):
        # NOTE Values of enumerator are output as constants
        self.file.write("enum_%s = c_int" % enum.tag)
    
    def print_constant(self, constant):
        self.file.write("%s = %s" % (constant.name, constant.value.py_string(False)))
    
    def print_typedef(self, typedef):
        self.file.write("%s = %s" % (typedef.name, typedef.ctype.py_string()))
    
    
    def print_variable(self, variable):
        assert self.options.library, "Binary symbol requires --library LIBNAME"
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
            self._print_simple_macro(macro)
        else:
            self._print_func_macro(macro)
    
    def _print_simple_macro(self, macro):
        entry = "{MN} = {ME}".format(MN=macro.name, ME=macro.expr.py_string(True))
        if self.options.guard_macros:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)
    
    def _print_func_macro(self, macro):
        self.file.write(
            "def {MN}({MP}):"
            "\n    return {ME}".format(
                MN=macro.name, MP=", ".join(macro.params), ME=macro.expr.py_string(True)
            )
        )
    
    def print_undef(self, undef):
        name = undef.macro.py_string(False)
        self.file.write(f"# undef {name}")
        entry = f"\ndel {name}"
        if self.options.guard_macros:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)
    
    
    def insert_file(self, filepath):
        self._embed_file(filepath, f"inserted file '{filepath}'")
