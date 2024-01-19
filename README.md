# ctypesgen (pypdfium2-team fork)

ctypesgen is a ctypes wrapper generator for Python.

This is a fork with the objective to better suit the needs of pypdfium2, and address some of the technical debt and (in our opinion) design issues that have accumulated due to highly conservative maintenance.

Here are some notes on our development intents:
* We do not mind API-breaking changes at this time.
* We endeavor to use plain ctypes as much as possible and keep the template lean.
* For now, we only envisage to work with ctypesgen's higher-level parts. The parser backend may be out of our scope.


### System Dependencies

ctypesgen depends on the presence of an external C pre-processor, by default `gcc` or `clang`, as available.
Alternatively, you may specify a custom pre-processor command using the `--cpp` option (e.g. `--cpp "clang -E"` to always use clang).


### Key differences in usage

* CLI
  - Headers have been converted from positional to flag `-i`/`--headers`, to avoid confusion with options that take a variadic number of params.
  - Beware: Historically, `--include` did something different and is now called `--system-headers` here.
  - `--symbol-rules` replaces `--include-symbols` (yes) / `--exclude-symbols` (never).
  - More flags changed or renamed.
  - `--allow-gnu-c` replaced by `-X __GNUC__`.
* The library loader does not implicitly search in the module's relative directory anymore. Add relevant libdirs explicitly.
* All strings interfacing with the C extension have to be encoded as bytes. We do not do implicit UTF-8 encoding/decoding. (A new, opt-in string helper might be added in the future.)
* We declare `c_void_p` as restype directly, which ctypes auto-converts to int/None. Previously, ctypesgen would use `POINTER(c_ubyte)` and cast to `c_void_p` via errcheck to bypass the auto-conversion. However, a `c_void_p` programatically is just that: an integer or null pointer, so the behavior of ctypes seems fine. Note that we can seamlessly `ctypes.cast()` an int to a pointer type. The API difference is that there is no `.value` property anymore. Instead, the object itself is the value, removing a layer of indirection.

See also `--help` for usage details.
Further, upstream docs may provide some information of interest ([readme](https://github.com/ctypesgen/ctypesgen#readme), [wiki](https://github.com/ctypesgen/ctypesgen/wiki)), but note that parts may not match this fork anymore.


### New features and improvements (selection)

* Implemented relative imports with `--link-modules`, and library handle sharing with `--no-embed-preamble`. Removed incorrect `POINTER` override that breaks the type system.
* Prevent assignment of invalid struct fields.
* Slimmed up template by removing many avoidable wrappers.
* Rewrote library loader. Resolve `.` to the module directory, not the caller's CWD. Don't add compile libdirs to runtime.
* Better control over symbol inclusion via `--symbol-rules` (exposes `if_needed` strategy, allows free order of actions).
* Symbol regex matching uses `fullmatch()` rather than `match()` (more explicit).
* Eagerly include direct members with `--system-headers`. This helps lower the need for `--all-headers` (which generally includes a lot more than necessary).
* Auto-detect default pre-processor.
* `-X`: Ability to override arbitrary pre-processor default flags added by ctypesgen.
* Pass through `-D/-U` in given order, i.e. honor undefines overriding defines, and vice versa.

See https://github.com/pypdfium2-team/ctypesgen/issues/1 for more.


### Tips & Tricks

* If you have multiple libraries that are supposed to interoperate with shared symbols, first create bindings to any shared headers and then use the `-m / --link-modules` option on dependants. (Otherwise, you'd create duplicate symbols that are formally different types, with need to cast between them.)
  If the module is not installed separately, you may prefix the module name with `.` for a relative import, and share the template using `--no-embed-preamble`. Relative modules will be expected to be present in the output directory at compile time.
  Note, this strategy can also be used to bind to same-library headers separately; however, you'll need to resolve the dependency tree on your own.
* To provide extra dependency headers that are not present in the system, you can set the `CPATH` or `C_INCLUDE_PATH` env vars for the C pre-processor. It may also be possible to use this for "cross-compilation" of bindings, or to spoof a foreign symbol using `typedef void* SYMBOL;` (`c_void_p`).
* If building with `--no-macro-guards` and you encounter broken macros, you may use `--symbol-rules` (see below) or replace them manually. This can be necessary on C constructs like `#define NAN (0.0f / 0.0f)` that don't play well with python. In particular, you are likely to run into this with `--all-headers`.

#### Notes on symbol inclusion

* ctypesgen works with the following symbol rules:
  - `yes`: The symbol is eagerly included.
  - `if_needed`: The symbol is included if other included symbols depend on it (e.g. a type used in a function signature).
  - `never`: The symbol is always excluded, and implicitly all its dependants.
* Roughly speaking, symbols from caller-given headers get assigned the include rule `yes`, and any others `if_needed`. When building with `--all-headers`, all symbols default to `yes` regardless of their origin.
* `--no-macros` sets the include rule of all macro objects to `never`.
* Finally, the `--symbol-rules` option is applied, which can be used to assign symbol rules by regex fullmatch expressions, providing callers with powerful means of control over symbol inclusion.
* To filter out excess symbols, you'll usually want to use `if_needed` rather than `never` to avoid accidental exclusion of dependants. Use `never` only where this side effect is actually wanted, e.g. to exclude a broken symbol.


### Known Limitations

*ctypes*
* Rare calling conventions other than `cdecl` or `stdcall` are not supported.
* Non-primitive return types in callbacks are not supported. An affected prototype wouldn't allow for the creation of a function instance, but not break the output as a whole.

*pypdfium2-ctypesgen*
* The DLL class is assumed to be `CDLL`, otherwise it needs to be given by the caller. We do not support mixed calling conventions, because it does not match the API layer of ctypes.
* We do not support binding to multiple binaries in the same output file. Instead, you'll want to create separate output files sharing the preamble, and possibly use module linking, as described above.

*ctypesgen*
* The conflicting names resolver is largely untested, in particular the handling of dependants. Please report success or failure.
* Linked modules are naively prioritized in dependency resolver and conflicting names handler, i.e. intentional overrides are ignored. The position of includes is not honored; ctypesgen always imports linked modules at top level.


### Fork rationale

Trying to get through changes upstream is tedious, with unclear outcome, and often not applicable due to mismatched intents (e.g. regarding backwards compatibility). Also consider that isolating commits in separate branches is not feasible anymore as merge conflicts arise (e.g. due to code cleanups and interfering changes).

Contrast this to a fork, which allows us to keep focused and effect improvements quickly, so as to invest developer time rationally.

However, we would be glad if our work could eventually be merged back upstream once the change set has matured, if upstream can arrange themselves with the radical changes.
See https://github.com/ctypesgen/ctypesgen/issues/195 for discussion.


### Syncing with upstream

- First, sync the fork's master branch using GitHub's web interface.
- View changes on [GitHub's compare page](https://github.com/pypdfium2-team/ctypesgen/compare/pypdfium2...master).
- Pull and merge locally, then push the result.

Last time we had to do this, `git merge origin/master -Xours` did a good job.
Changes to files we haven't really modified can usually just be pulled in as-is.
Otherwise, you'll have to manually look through the changes and pick what you consider worthwhile on a case by case basis.

Note, it is important to verify the resulting merge commit for correctness - automatic merge strategies might produce mistakes!


### Bugs

Oversights or unintentional breakage can happen at times. Feel free to file a bug report if you think a change introduces logical issues.
