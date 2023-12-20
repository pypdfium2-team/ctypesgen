# ctypesgen (pypdfium2-team fork)

ctypesgen is a ctypes wrapper generator for Python.

This is a fork with the objective to better suit the needs of pypdfium2, and address some of the technical debt and (in our opinion) design issues that have accumulated due to highly conservative maintenance.

See also `--help` for usage, and upstream docs ([readme](https://github.com/ctypesgen/ctypesgen#readme), [wiki](https://github.com/ctypesgen/ctypesgen/wiki)), but note that this fork has diverged somewhat, so parts of it may not apply here anymore.

See https://github.com/pypdfium2-team/ctypesgen/issues/1 for a draft overview of changes in this fork. Further, here are some notes on our development intents:
* We do not mind API-breaking changes at this time.
* We endeavor to use plain ctypes as much as possible and keep the template lean. Contrast this to upstream ctypesgen, which clogs up the bindings with custom wrappers.
* For now, we only envisage to work with ctypesgen's higher-level parts (e.g. the printer). The parser backend may be out of our scope.

### System Dependencies

ctypesgen depends on the presence of an external C pre-processor, by default `gcc` or `clang`, as available.
Alternatively, you may specify a custom pre-processor command using the `--cpp` option (e.g. `--cpp "clang -E"` to always use clang).

### Tips & Tricks

* If you have multiple libraries that are supposed to interoperate with shared symbols, first create bindings to any shared headers and then use the `-m / --link-modules` option on dependants. (Otherwise, you'd create duplicate symbols that are formally different types, with need to cast between them.)
  If the module is not installed separately, you may prefix the module name with `.` for a relative import, and share the template using `--no-embed-preamble`. Relative modules will be expected to be present in the output directory at compile time.
  Note, this strategy can also be used to bind to same-library headers separately; however, you'll need to resolve the dependency tree on your own.
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
* To filter out undesired symbols, you'll usually want to use `if_needed` rather than `never` to avoid accidental exclusion of dependants. Use `never` only where this side effect is actually wanted, e.g. to exclude a broken symbol.

### Known Limitations

*ctypes*
* Rare calling conventions other than `cdecl` or `stdcall` are not supported.
* Non-primitive return types in callbacks are not supported. An affected prototype wouldn't allow for the creation of a function instance, but not break the output as a whole.

*This fork (somewhat intentional)*
* The DLL class is assumed to be `CDLL`, otherwise it needs to be given by the caller. We do not support mixed calling conventions, because it does not match the API layer of ctypes.
* We do not support binding to multiple binaries in the same output file. Instead, you'll want to create separate output files sharing the preamble, and possibly use module linking, as described above.

*Inherited from upstream - real concerns, but likely difficult to fix*
* Conflicting names are detected, but not actually resolved recursively: any dependent symbols would currently get excluded from the output.
  However, the scope of this issue should be somewhat limited, for structs and enums are prefixed as such and then aliased to their C name, and functions try to use the direct (prefixed) definition.
  E.g. if you have a struct called `class`, the direct definition would be `struct_class`, and a function `foo(class* obj)` should be translated to `foo.argtypes = [POINTER(struct_class)]`.

### Fork rationale

Trying to get through changes upstream is tedious, with unclear outcome, and often not applicable due to mismatched intents (e.g. regarding backwards compatibility). Also consider that isolating commits in separate branches is not feasible anymore as merge conflicts arise (e.g. due to code cleanups and interfering changes).

Contrast this to a fork, which allows us to keep focused and effect improvements quickly, so as to invest pypdfium2 developer time rationally.

### Bugs

Oversights or unintentional breakage can happen at times. Feel free to file an bug report if you think a change introduces logical issues.
