"""Preprocess a C source file using gcc and convert the result into
   a token stream

Reference is C99:
  * http://www.open-std.org/JTC1/SC22/WG14/www/docs/n1124.pdf
"""

import os
import re
import sys
import copy
import subprocess
from pathlib import Path

from ctypesgen.parser import pplexer, lex
from ctypesgen.parser.lex import LexError
from ctypesgen.messages import warning_message


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
        
        cmd = [*self.options.cpp, "-dD"]
        flags_dict = self._get_default_flags()
        flags_dict["-I"] = self.options.include_search_paths
        cmd += self._serialize_flags_dict(flags_dict)
        cmd += self.options.cppargs + [filename]
        self.cparser.handle_status(cmd)

        pp = subprocess.run(
            cmd,
            universal_newlines=False,  # binary
            stdout=subprocess.PIPE,
            check=True,
        )
        
        if IS_MAC:
            ppout = pp.stdout.decode("utf-8", errors="replace")
        else:
            ppout = pp.stdout.decode("utf-8")
        
        if IS_WINDOWS:
            ppout = ppout.replace("\r\n", "\n")
        
        # We separate lines to two groups: directives and c-source.  Note that
        # #pragma directives actually belong to the source category for this.
        # This is necessary because some source files intermix preprocessor
        # directives with source--this is not tolerated by ctypesgen's single
        # grammar.
        # We put all the source lines first, then all the #define lines.

        source_lines = []
        define_lines = []

        first_token_reg = re.compile(r"^#\s*([^ ]+)($|\s)")

        for line in ppout.split("\n"):
            line += "\n"
            search = first_token_reg.match(line)
            hash_token = search.group(1) if search else None

            if not hash_token or hash_token == "pragma":
                source_lines.append(line)
                define_lines.append("\n")

            elif hash_token.isdigit():
                # Line number information has to go with both groups
                source_lines.append(line)
                define_lines.append(line)

            else:  # hash_token in ("define", "undef"):
                source_lines.append("\n")
                define_lines.append(line)

        text = "".join(source_lines + define_lines)

        if self.options.preproc_savepath:
            self.cparser.handle_status(f"Saving preprocessor output to {self.options.preproc_savepath}.")
            Path(self.options.preproc_savepath).write_text(text)

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
            self.cparser.handle_error("{}; {}".format(e, e.text.partition("\n")[0]), filename, 0)
