import shutil
import functools
from pathlib import Path
from textwrap import indent
from contextlib import contextmanager

from ctypesgen.ctypedescs import CtypesBitfield, CtypesStruct
from ctypesgen.expressions import ExpressionNode
from ctypesgen.messages import warning_message, status_message


CTYPESGEN_DIR = Path(__file__).resolve().parent
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


@functools.lru_cache(maxsize=1)
def get_priv_paths():
    priv_paths = [(Path.home(), "~")]
    if Path.cwd() != Path("/"):  # don't strip unix root
        priv_paths.insert(0, (Path.cwd(), "."))
    # sort descending by length to avoid interference
    priv_paths.sort(key=lambda x: len(str(x[0])), reverse=True)
    return priv_paths

def txtpath(p):
    # Returns a path string suitable for embedding into the output, with private paths stripped
    p = Path(p)
    for strip_p, x in get_priv_paths():
        # should be equivalent to `p.is_relative_to(strip_p)` or `p.parts[:len(strip_p.parts)] == strip_p.parts`
        if strip_p in p.parents or p == strip_p:
            return x + str(p)[len(str(strip_p)):]
    return str(p)


# Important: Concerning newlines handling, please read docs/dev_comments.md

class WrapperPrinter:
    
    def __init__(self, outpath, opts, data, cmd_str):
        
        self.opts = opts
        self._srcinfo = self._srcinfo_on if self.opts.add_srcinfo else self._srcinfo_off
        
        with outpath.open("w", encoding="utf-8") as self.file:
            
            self.paragraph_ctx = ParagraphCtxFactory(self.file)
            
            self.file.write(f'R"""\nAuto-generated by:\n{cmd_str}\n"""')
            self.file.write(
                "\n\nimport ctypes"
                "\nfrom ctypes import *"
            )
            
            if opts.modules:
                self.file.write("\n\n# Linked modules")
                for mod in opts.modules:
                    self.file.write(f"\nfrom {mod} import *")
            
            if opts.library:
                if opts.dllclass == "pythonapi":
                    assert opts.library == "python"
                    self.file.write("\n\n_libs = {%r: ctypes.pythonapi}" % opts.library)
                else:
                    self.print_loader(opts)
                    self.print_library(opts)
            else:
                warning_message("No library name specified. Assuming pure headers without binary symbols.", cls="usage")
            
            self.file.write("\n\n\n")
            with self.paragraph_ctx("header members"):
                for kind, desc in data:
                    self.file.write("\n\n")
                    getattr(self, f"print_{kind}")(desc)
                self.file.write("\n")
            
            for fp in opts.inserted_files:
                self.file.write("\n\n\n")
                self._embed_file(fp, f"inserted file '{txtpath(fp)}'")
            
            self.file.write("\n")
    
    
    def _srcinfo_on(self, obj):
        # NOTE Could skip lineno if `fp in ("<built-in>", "<command line>")`, but this doesn't seem worth the if-check
        fp, lineno = obj.src
        self.file.write(f"# {txtpath(fp)}: {lineno}\n")
    
    def _srcinfo_off(self, obj):
        pass
    
    def _embed_file(self, fp, desc):
        with self.paragraph_ctx(desc), open(fp, "r") as src_fh:
            self.file.write("\n\n")
            shutil.copyfileobj(src_fh, self.file)
    
    def _try_except_wrap(self, entry):
        pad = " "*4
        return f"try:\n{indent(entry, pad)}\nexcept:\n{pad}pass"
    
    
    def print_loader(self, opts):
        if opts.embed_templates:
            self.file.write("\n\n\n")
            self._embed_file(LIBRARYLOADER_PATH, "loader template")
        else:
            self.EXT_LOADER = opts.linkage_anchor / "_ctg_loader.py"
            if not self.EXT_LOADER.exists():
                shutil.copyfile(LIBRARYLOADER_PATH, self.EXT_LOADER)
            n_dots = len(opts.output.parts) - len(opts.linkage_anchor.parts)
            self.file.write(
                "\n\n# Shared library handles"
                f"\nfrom {'.'*n_dots}_ctg_loader import _libs"
            )
    
    
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
        if opts.embed_templates:
            self.file.write(f"\n\n\n{content}")
        else:
            loader_txt = self.EXT_LOADER.read_text()
            if name_define in loader_txt:
                status_message("Library already loaded in shared file, won't rewrite.")
            else:
                # we need to share libraries in a common file to build same-library headers separately while loading the library only once
                status_message("Adding library loader to shared file.")
                self.EXT_LOADER.write_text(f"{loader_txt}\n\n{content}\n")
    
    
    def print_function(self, function):
        assert self.opts.library, "Binary symbol requires --library LIBNAME"
        self._srcinfo(function)
        
        # we have to do string based attribute access because the CN might conflict with a python keyword, while the PN is supposed to be renamed
        template = """\
{PN} = _libs['{L}']['{CN}']
{PN}.argtypes = [{ATS}]
{PN}.restype = {RT}\
"""
        fields = dict(
            L=self.opts.library,
            CN=function.c_name(),
            PN=function.py_name(),
            ATS=", ".join([a.py_string() for a in function.argtypes]),
            RT=function.restype.py_string(),
        )
        if function.errcheck:
            template += "\n{PN}.errcheck = {EC}"
            fields["EC"] = function.errcheck.py_string()
        
        if self.opts.guard_symbols:
            template = "if hasattr(_libs['{L}'], '{CN}'):\n" + indent(template, prefix=" "*4)
        
        self.file.write(template.format(**fields))
    
    
    def print_variable(self, variable):
        assert self.opts.library, "Binary symbol requires --library LIBNAME"
        self._srcinfo(variable)
        entry = "{PN} = ({PS}).in_dll(_libs['{L}'], '{CN}')".format(
            PN=variable.py_name(),
            PS=variable.ctype.py_string(),
            L=self.opts.library,
            CN=variable.c_name(),
        )
        if self.opts.guard_symbols:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)
    
    
    def print_struct(self, struct):
        self._srcinfo(struct)
        base = {"union": "Union", "struct": "Structure"}[struct.variety]
        self.file.write(f"class {struct.variety}_{struct.tag} ({base}):")
        pad = "\n" + " "*4
        
        if struct.opaque:
            self.file.write(pad + "pass")
            return
        
        # FIXME(geisserml) The two blocks below look like they do evaluation work that doesn't belong in the printer, but in an earlier part of the control flow...
        
        # is this supposed to be packed?
        if struct.attrib.get("packed", False):
            aligned = struct.attrib.get("aligned", [1])
            assert len(aligned) == 1, "cgrammar gave more than one arg for aligned attribute"
            aligned = aligned[0]
            if isinstance(aligned, ExpressionNode):
                # FIXME for non-constant expression nodes, this will fail
                aligned = aligned.evaluate(None)
            self.file.write(pad + f"_pack_ = {aligned}")
        
        # handle unnamed fields.
        unnamed_fields = []
        names = set([x[0] for x in struct.members])
        n = 1
        for mi in range(len(struct.members)):
            mem = list(struct.members[mi])
            if mem[0] is None:
                while True:
                    name = f"unnamed_{n}"
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
        # Fields are defined indepedent of the actual class to handle forward declarations, including self-references and cyclic structs
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
        # NOTE values of enumerator are output as constants
        self._srcinfo(enum)
        self.file.write(f"enum_{enum.tag} = c_int")
    
    def print_constant(self, constant):
        self._srcinfo(constant)
        self.file.write(f"{constant.name} = {constant.value.py_string(False)}")
    
    def print_typedef(self, typedef):
        self._srcinfo(typedef)
        self.file.write(f"{typedef.name} = {typedef.ctype.py_string()}")
    
    def print_macro(self, macro):
        self._srcinfo(macro)
        # important: must check precisely against None because params may be an empty list for a func macro
        if macro.params is None:  # simple macro
            entry = f"{macro.name} = {macro.expr.py_string(True)}"
            if self.opts.guard_macros:
                entry = self._try_except_wrap(entry)
            self.file.write(entry)
        else:  # func macro
            self.file.write(
                f"def {macro.name}({', '.join(macro.params)}):"
                f"\n    return {macro.expr.py_string(True)}"
            )
    
    def print_undef(self, undef):
        self._srcinfo(undef)
        name = undef.macro.py_string(False)
        entry = f"del {name}"
        if self.opts.guard_macros:
            entry = self._try_except_wrap(entry)
        self.file.write(entry)
