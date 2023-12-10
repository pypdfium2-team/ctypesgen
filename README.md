# ctypesgen (pypdfium2-team fork)

ctypesgen is a ctypes wrapper generator for Python.

This is a fork with the objective to better suit the needs of pypdfium2, and address some of the technical debt and (in our opinion) design issues that have accumulated due to highly conservative maintenance.

See also `--help` for usage, and upstream docs ([readme](https://github.com/ctypesgen/ctypesgen#readme), [wiki](https://github.com/ctypesgen/ctypesgen/wiki)), but note that this fork has diverged somewhat, so parts of it may not apply here anymore.

See https://github.com/pypdfium2-team/ctypesgen/issues/1 for a draft overview of changes in this fork. Further, here are some notes on our development intents:
* We do not mind API-breaking changes at this time.
* We endeavor to use plain ctypes as much as possible and keep the template lean. Contrast this to upstream ctypesgen, which clogs up the bindings with custom wrappers.
* For now, we only envisage to work with ctypesgen's higher-level parts (e.g. the printer). The parser backend may be out of our scope.

### System Dependencies

ctypesgen depends on the presence of an external C pre-processor, by default GCC.
You may specify an alternative pre-processor command using the `--cpp` option.
However, we are only testing with GCC at this time – others may or may not work.

### Tips & Tricks

* If you have multiple libraries that are supposed to interoperate with shared symbols, first create bindings to any shared headers and then use the `-m / --link-modules` option on dependants. (Otherwise, you'd create duplicate symbols that are formally different types, with need to cast between them.)
  If the module is not installed separately, you may prefix the module name with `.` for a relative import, and share the template using `--no-embed-preamble`. Relative modules will be expected to be present in the output directory at compile time.
* To provide extra dependency headers that are not present in the system, you can set the `CPATH` or `C_INCLUDE_PATH` env vars for the C pre-processor. It may also be possible to use this for "cross-compilation" of bindings, or to spoof an optional foreign symbol using `typedef void* SYMBOL;` (`c_void_p`).
* If building with `--no-macro-guards` and you encounter broken macros, you may use `--symbol-rules` (see below) or replace them manually. This can be necessary on C constructs like `#define NAN (0.0f / 0.0f)` that don't play well with python. In particular, you are likely to run into this with `--all-headers`.

#### Notes on symbol inclusion
* ctypesgen works with the following symbol rules:
  - `yes`: The symbol is eagerly included.
  - `if_needed`: The symbol is included if other included symbols depend on it (e.g. a type used in a function signature).
  - `never`: The symbol is always excluded, and implicitly all its dependants.
* Roughly speaking, symbols from caller-given headers get assigned the include rule `yes`, and any others `if_needed`. When building with `--all-headers`, all symbols default to `yes` regardless of their origin.
* `--no-macros` sets the include rule of all macro objects to `never`.
* Finally, the `--symbol-rules` option is applied, which can be used to assign symbol rules by regex fullmatch expressions, providing callers with powerful means of control over symbol inclusion.
* Note that you should be very careful with `never` because of the potential for accidental exclusion of dependants. As a rule of thumb, you'll usually want to use `if_needed` rather than `never`.

### Known Limitations

* The DLL class is assumed to be `CDLL`, otherwise it needs to be given by the caller. We do not support mixed calling conventions, and none other than `cdecl` or `stdcall`, because ctypes itself does not.

### Bugs

Rapid, need-driven development can be prone to oversights or unintentional breakage. Please inform us if you think a change introduces logical issues.

### Fork rationale

Trying to get through changes upstream is tedious, with unclear outcome, and often not applicable due to mismatched intents (e.g. regarding backwards compatibility). Also consider that isolating commits in separate branches is not feasible anymore as merge conflicts arise (e.g. due to code cleanups and interfering changes).

Contrast this to a fork, which allows us to keep focused and effect improvements quickly, so as to invest pypdfium2 developer time rationally.
