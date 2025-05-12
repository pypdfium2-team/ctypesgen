# Changelog


## Unreleased (v2)

- Large-scale rewrite of ctypesgen by `@mara004`, aiming to unbloat, simplify and modernize the codebase.
- Many issues fixed. See https://github.com/pypdfium2-team/ctypesgen/issues/1 and https://github.com/ctypesgen/ctypesgen/issues/195 and below for an overview.

### Usage differences (selection)

* CLI
  - Headers have been converted from positional to flag `-i`/`--headers`, to avoid confusion with options that take a variadic number of params.
  - Beware: Historically, `--include` did something different and is now called `--system-headers` here.
  - `--symbol-rules` replaces `--include-symbols` (yes) / `--exclude-symbols` (never).
  - `--no-embed-preamble` renamed to `--no-embed-templates`.
  - `--allow-gnu-c` replaced by `-X __GNUC__`.
  - More flags changed or renamed.
* The library loader does not implicitly search in the module's relative directory anymore. Add relevant libdirs explicitly.
* The bloated string wrappers have been removed. By default, no implicit string encoding/decoding is being done anymore, because `char*` is not necessarily a UTF-8 string or even NUL-terminated. However, the `--string-template` option allows callers to plug in their own string helpers (e.g. `c_char_p` in the easiest case, or a custom wrapper).
* We declare `c_void_p` as restype directly, which ctypes auto-converts to int/None. Previously, ctypesgen would use `POINTER(c_ubyte)` and cast to `c_void_p` via errcheck to bypass the auto-conversion. However, a `c_void_p` programatically is just that: an integer or null pointer, so the behavior of ctypes seems fine. Note that we can seamlessly `ctypes.cast()` an int to a pointer type. The API difference is that there is no `.value` property anymore. Instead, the object itself is the value, removing a layer of indirection.

See also `--help` for usage details.

### New features and improvements (selection)

* Implemented relative imports with `--link-modules`, and library handle sharing with `--no-embed-templates`. Removed incorrect `POINTER` override that breaks the type system.
* Prevent assignment of invalid struct fields by setting slots *in the class body*.
* Slimmed up template by removing many avoidable wrappers.
* Rewrote library loader. Resolve `.` to the module directory, not the caller's CWD. Don't add compile libdirs to runtime. Handle iOS (PEP 730).
* Better control over symbol inclusion via `--symbol-rules` (exposes `if_needed` strategy, allows free order of actions).
* Symbol regex matching uses `fullmatch()` rather than `match()` (more explicit).
* Eagerly include direct members with `--system-headers`. This helps lower the need for `--all-headers` (which generally includes a lot more than necessary).
* Auto-detect default pre-processor.
* Handle FAMs (Flexible Array members) as zero-sized arrays. See https://github.com/ctypesgen/ctypesgen/issues/219.
* Tightened `UNCHECKED()` template to only remap pointer types, and pass through anything else as-is. This avoids erroneously changing non-pointer types or `None` to `c_void_p`.
* `-X`: Ability to override arbitrary pre-processor default flags added by ctypesgen.
* Pass through `-D/-U` in given order.


## Historical

### v1.1.1

- Fixed inconsistency in version output in released packages

### v1.1.0

This release has a number of bug fixes in addition to a few new features.
Following a complete transition to Python 3, with dropped Python 2 support,
major work was made towards code modernization and quality.

- The code is now Black formatted and Flake8 tested
- Greatly improved unittest framework
- Embedded PLY version updated to 3.11
- New option: `--no-embed-preamble` create separate files for preamble and
  loader instead of embedding in each output file
- New option: `--allow-gnu-c` do not undefine `__GNUC__`
- Fixed library loader search path on macOS
- Fixed rare bug, processing (legacy) header files with MacRoman encoding
  on macOS
- Added full support for floating and integer constants
- Added support for sized integer types on Windows
- Added support to handle `restrict` and `_Noreturn` keywords
- Added name formats to posix library loader
- Fixed mapping of 'short int' to c_short
- Git tags are now using `x.y.z` format

### v1.0.2

Many issues fixed. Parse gcc attributes more

Implements automatic calling convention selection based on gcc attributes for
stdcall/cdecl.

- Simplify and unify library loader for various platforms. Improve library path
  searches on Linux (parsed ld.so.conf includes now).
- First implementaion of #pragma pack
- First implemenation of #undef
- Adds several command line options:
  `-D` `--define`
  `-U` `--undefine`
  `--no-undefs`
  `-P` `--strip-prefix`
  `--debug-level`

### v1.0.1

Fix handling of function prototypes

Other minor improvments included.

### v1.0.0

Py2/Py3 support

Various development branches merged back

In addition to the various developments from the different branches, this
tag also represents a code state that:

- ties in with Travis CI to watch code developments
- improves testsuite, including moving all JSON tests to testsuite
- includes a decent Debian package build configuration
- automatically creates a man page to be included in the Debian package
