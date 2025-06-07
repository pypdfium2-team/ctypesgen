"""Preprocess a C source file using gcc and convert the result into
   a token stream

Reference is C99:
  * http://www.open-std.org/JTC1/SC22/WG14/www/docs/n1124.pdf
"""

import os
import re
import sys
import copy
import shlex
import subprocess
from pathlib import Path

from ctypesgen.parser import pplexer, lex
from ctypesgen.parser.lex import LexError
from ctypesgen.messages import warning_message, status_message


IS_WINDOWS = sys.platform.startswith("win")
IS_MAC = sys.platform.startswith("darwin")

# --------------------------------------------------------------------------
# Lexers
# --------------------------------------------------------------------------


class PreprocessorLexer(lex.Lexer):
    def __init__(self):
        lex.Lexer.__init__(self)
        self.filename = "<input>"
        self.in_define = False

    def input(self, data, filename=None):
        if filename:
            self.filename = filename
        self.lasttoken = None

        lex.Lexer.input(self, data)

    def token(self):
        result = lex.Lexer.token(self)
        if result:
            self.lasttoken = result.type
            result.filename = self.filename
        else:
            self.lasttoken = None

        return result


# --------------------------------------------------------------------------
# Grammars
# --------------------------------------------------------------------------


class PreprocessorParser:
    def __init__(self, options, cparser):
        self.options = options
        self.cparser = cparser  # An instance of CParser
        
        self.default_flags = {"-D": {}, "-U": []}
        self.default_flags["-D"].update({
            "__extension__": "",
            "__asm__(x)": "",
            "__asm(x)": "",
            "__const": "const",
            "CTYPESGEN": "1",
        })
        if IS_MAC:
            # On macOS, explicitly add these defines to keep from getting syntax
            # errors in the macOS standard headers.
            self.default_flags["-D"].update({
                "_Nullable": "",
                "_Nonnull": "",
            })
            # This fixes Issue #6 where OS X 10.6+ adds a C extension that breaks
            # the parser. Blocks shouldn't be needed for ctypesgen support anyway.
            self.default_flags["-U"] += ["__BLOCKS__"]
        
        # Legacy behaviour is to implicitly undefine '__GNUC__'
        # Continue doing this, unless user explicitly requested to allow it via -X __GNUC__
        self.default_flags["-U"] += ["__GNUC__"]
        
        self.matches = []
        self.output = []
        self.lexer = lex.lex(
            cls=PreprocessorLexer,
            optimize=options.optimize_lexer,
            lextab="lextab",
            outputdir=os.path.dirname(__file__),
            module=pplexer,
        )
    
    
    def _get_default_flags(self):
        
        if self.options.no_default_cppflags is None:
            return self.default_flags
        elif not self.options.no_default_cppflags:
            return {}
        
        flags_dict = copy.deepcopy(self.default_flags)
        crossout = self.options.no_default_cppflags
        for params in flags_dict.values():
            deletor = params.pop if isinstance(params, dict) else params.remove
            unfound = []
            for x in crossout:
                deletor(x) if x in params else unfound.append(x)
            crossout = unfound
        if crossout:
            warning_message(f"No defaults to remove for {crossout!r}")
        
        return flags_dict
    
    
    @staticmethod
    def _serialize_flags_dict(flags_dict):
        serialized = []
        for flag, params in flags_dict.items():
            if isinstance(params, dict):
                params = [f"{k}={v}" for k, v in params.items()]
            for p in params:
                serialized += [flag, p]
        return serialized
    

    def parse(self, filename):
        """Parse a file and save its output"""
        
        cmd = [*self.options.cpp, filename, "-dD"]
        flags_dict = self._get_default_flags()
        cmd += self._serialize_flags_dict(flags_dict)
        for p in self.options.include_search_paths:
            cmd += ["-I", p]
        cmd += self.options.cppargs
        self.cparser.handle_status(' '.join([shlex.quote(c) for c in cmd]))
        
        pp = subprocess.run(
            cmd,
            universal_newlines=False,  # binary
            stdout=subprocess.PIPE,
        )
        if pp.returncode != 0:
            msg = f"Pre-processor returned non-zero exit code {pp.returncode}"
            if self.options.preproc_errcheck:
                raise RuntimeError(msg)
            else:
                warning_message(msg)
        
        if self.options.preproc_savepath:
            self.cparser.handle_status(f"Saving preprocessor output to {self.options.preproc_savepath}.")
            self.options.preproc_savepath.write_bytes(pp.stdout)
        
        if IS_MAC:
            ppout = pp.stdout.decode("utf-8", errors="replace")
        else:
            ppout = pp.stdout.decode("utf-8")
        
        if IS_WINDOWS:
            ppout = ppout.replace("\r\n", "\n")
        
        text = ppout
        
        # NOTE(geisserml) The procedure below is rather displeasing. I couldn't find an evident reason for the separation anymore, and ctypesgen's test suite passes without it, so let's comment this out as long as we don't hear of a counter-example.
        # That said, improving the parser may be preferable over post-processing if we can help it.
        
#         # We separate lines to two groups: directives and c-source.  Note that
#         # #pragma directives actually belong to the source category for this.
#         # This is necessary because some source files intermix preprocessor
#         # directives with source--this is not tolerated by ctypesgen's single
#         # grammar.
#         # We put all the source lines first, then all the #define lines.
#         
#         source_lines = []
#         define_lines = []
#         
#         first_token_reg = re.compile(r"^#\s*([^\s]+)(.*)", flags=re.DOTALL)
#         
#         for line in ppout.splitlines(True):
#             match = first_token_reg.match(line)
#             if match:
#                 hash_token = match.group(1)
#                 # dispose of possible whitespace between hash and specifier, the lexer doesn't like this (though a good pre-processor should have normalized this already)
#                 if hash_token in ("pragma", "define", "undef"):
#                     line = f"#{hash_token}{match.group(2)}"
#             else:
#                 hash_token = None
#             
#             if not hash_token or hash_token == "pragma":
#                 source_lines.append(line)
#                 # define_lines.append("\n")
#             
#             elif hash_token in ("define", "undef"):
#                 # source_lines.append("\n")
#                 define_lines.append(line)
#             
#             elif hash_token.isdigit():
#                 # Line number information has to go with both groups
#                 source_lines.append(line)
#                 define_lines.append(line)
#             
#             else:  # hash_token.startswith("#"):
#                 # It's a directive, but not a #define or #undef. Remove it.
#                 warning_message(f"Skip unhandled directive {hash_token!r}")
#                 # source_lines.append("\n")
#                 # define_lines.append("\n")
#         
#         text = "".join(source_lines + define_lines)
        
        self.lexer.input(text)
        self.output = []
        
        try:
            while True:
                token = self.lexer.token()
                if token is not None:
                    self.output.append(token)
                else:
                    break
        except LexError as e:
            # FIXME This will produce an incomplete output, any members after the offending line will be missing.
            # TODO If possible, skip past the error and continue lexing. In the meantime, we should at least propagate a non-zero return code in the end.
            self.cparser.handle_error("{}; {}".format(e, e.text.partition("\n")[0]), filename, 0)
