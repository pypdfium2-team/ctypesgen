"""Preprocess a C source file using gcc and convert the result into
   a token stream

Reference is C99:
  * http://www.open-std.org/JTC1/SC22/WG14/www/docs/n1124.pdf

"""

__docformat__ = "restructuredtext"

import os
import re
import sys
import subprocess

from ctypesgen.parser import pplexer, lex
from ctypesgen.parser.lex import LexError


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
        
        self.default_defs = [
            "__extension__=",
            "__const=const",
            "__asm__(x)=",
            "__asm(x)=",
            "CTYPESGEN=1",
        ]

        # On macOS, explicitly add these defines to keep from getting syntax
        # errors in the macOS standard headers.
        if IS_MAC:
            self.default_defs += [
                "_Nullable=",
                "_Nonnull=",
            ]
        
        # Legacy behaviour is to implicitly undefine '__GNUC__'
        # Continue doing this, unless user explicitly requested to allow it.
        # TODO allow for more flexible overrides of defaults?
        self.default_undefs = []
        if not self.options.allow_gnu_c:
            self.default_undefs += ["__GNUC__"]
        
        # This fixes Issue #6 where OS X 10.6+ adds a C extension that breaks
        # the parser. Blocks shouldn't be needed for ctypesgen support anyway.
        if IS_MAC:
            self.default_undefs += ["__BLOCKS__"]

        self.matches = []
        self.output = []
        self.lexer = lex.lex(
            cls=PreprocessorLexer,
            optimize=options.optimize_lexer,
            lextab="lextab",
            outputdir=os.path.dirname(__file__),
            module=pplexer,
        )


    def parse(self, filename):
        """Parse a file and save its output"""

        cmd = self.options.cpp + ["-dD"]
        for path in self.options.include_search_paths:
            cmd += ["-I", path]
        
        # apply in this order so given params always override defaults
        for u in self.default_undefs:
            cmd += ["-U", u]
        for d in self.default_defs:
            cmd += ["-D", d]
        # note: the input order of given undefs/defs is not currently honored due to argparse gathering in two separate lists, i.e. we rely on the caller not to pass a matching undefine after a define (this would be redundant, anyway)
        for u in self.options.cpp_undefines:
            cmd += ["-U", u]
        for d in self.options.cpp_defines:
            cmd += ["-D", d]
        
        cmd += [filename]
        self.cparser.handle_status(cmd)

        pp = subprocess.Popen(
            cmd,
            universal_newlines=False,  # binary
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        ppout_data, pperr_data = pp.communicate()

        try:
            ppout = ppout_data.decode("utf-8")
        except UnicodeError:
            if IS_MAC:
                ppout = ppout_data.decode("utf-8", errors="replace")
            else:
                raise UnicodeError
        pperr = pperr_data.decode("utf-8")

        if IS_WINDOWS:
            ppout = ppout.replace("\r\n", "\n")
            pperr = pperr.replace("\r\n", "\n")

        for line in pperr.split("\n"):
            if line:
                self.cparser.handle_pp_error(line)

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

            if (not hash_token) or hash_token == "pragma":
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

        if self.options.save_preprocessed_headers:
            self.cparser.handle_status(
                "Saving preprocessed headers to %s." % self.options.save_preprocessed_headers
            )
            try:
                with open(self.options.save_preprocessed_headers, "w") as f:
                    f.write(text)
            except IOError:
                self.cparser.handle_error("Couldn't save headers.")

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
