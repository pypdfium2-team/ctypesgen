_**Important:** This repository's actual main branch is `pypdfium2`, whereas `master` is the old upstream codebase. So if you want to use this fork, make sure you are on `pypdfium2`, or a branch derived thereof. This layout has historical reasons, and makes it easier to sync the fork._

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

See also [`docs/pcpp.md`](docs/pcpp.md) for an experimental pure-python option.


### Tips & Tricks

* If you have multiple libraries that are supposed to interoperate with shared symbols, first create bindings to any shared headers and then use the `-m / --link-modules` option on dependants. (Otherwise, you'd create duplicate symbols that are formally different types, with need to cast between them.)
  If the module is not installed separately, you may prefix the module name with `.` for a relative import, and share boilerplate code using `--no-embed-templates`. Relative modules will be expected to be present in the output directory at compile time.
  Note, this strategy can also be used to bind to same-library headers separately; however, you'll need to resolve the dependency tree on your own.
* Extra include search paths can be provided using the `-I` option or by setting `$CPATH`/`$C_INCLUDE_PATH`.
  You could use this to add a header spoofing an external symbol via `typedef void* SYMBOL;` (`c_void_p`) that may be provided by a third-party binding at runtime.
* If building with `--no-macro-guards` and you encounter broken macros, you may use `--symbol-rules` (see below) or replace them manually. This can be necessary on C constructs like `#define NAN (0.0f / 0.0f)` that don't play well with python. In particular, you are likely to run into this with `--all-headers`.

Also, check out [`docs/demo/`](docs/demo/) for a minimalistic example of using ctypesgen,
and [`docs/python_api.md`](docs/python_api.md) on how to produce bindings for Python's C API.


#### Symbol inclusion

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
* ctypes does not support custom pointer result types in callbacks. Therefore, we use a template to remap these to `c_void_p`.

*pypdfium2-ctypesgen*
* The DLL class is assumed to be `CDLL`, otherwise it needs to be given by the caller. We do not currently support mixed calling conventions, because it does not match the API layer of ctypes.
* We do not support binding to multiple binaries in the same output file. Instead, you'll want to create separate output files sharing the loader template, and possibly use module linking, as described above.

*ctypesgen*
* ctypesgen's parser was originally written for C99. Support for later standards (C11 etc.) is probably incomplete.
* The conflicting names resolver is largely untested, in particular the handling of dependants. Please report success or failure.
* Linked modules are naively prioritized in dependency resolver and conflicting names handler, i.e. intentional overrides are ignored. The position of includes is not honored; ctypesgen always imports linked modules at top level.


### History and Friends

- ctypesgen has its roots in [`wraptypes`](https://github.com/pyglet/pyglet/tree/master/tools/wraptypes) from pyglet, which was originally written by Alex Holkner for C99, and is still around today.
  Some documentation can be found [here](https://docs.pyglet.org/en/development/internal/wraptypes.html). This may still be a valuable source of information even for today's ctypesgen.

- ctypesgen is also used by the GRASS project, which has its own copy of ctypesgen [here](https://github.com/OSGeo/grass/tree/main/python/libgrass_interface_generator).

- [`ctypeslib2`](https://github.com/trolldbois/ctypeslib) is an independent alternative to ctypesgen.
It has its own parser backend using Clang API. This may be more reliable in a way, at the cost of being impure and tied to a specific compiler.
  `ctypeslib2` has some fancy features ctypesgen currently does not, such as taking over Doxygen comments.

- The original `ctypeslib` (by former ctypes maintainer Thomas Heller) used GCC's XML output, but the author is not aware of a maintained version of this codebase. `ctypeslib2` is derived from ctypeslib, but its backend has been thoroughly changed for Clang.


### Issues / Patches

Oversights or unintentional breakage can happen at times. If you think a change introduces logical issues, feel free to file a bug report or submit a patch.

Note though, the response/contributions policy is [basically the same as for pypdfium2](https://github.com/pypdfium2-team/pypdfium2/?tab=readme-ov-file#response-policy).


### Code Style

The pypdfium2-ctypesgen codebase *intentionally* does not hard wrap long lines.
You'll want to configure your editor to soft wrap e.g. at 100 columns.

We also intentionally maintain indentation levels. This allows pasting code excerpts into the Python console (REPL), and makes editing more convenient.

Future maintainers, please keep it this way. Also, please do NOT run formatters like Black on this codebase ever again.
Take care of code style yourself while editing, this tends to yield much smarter results.


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
You might also want to ignore whitespace changes, probably by adding `-Xignore-all-space` or something.

For those parts of ctypesgen that we have barely modified (e.g. the parser core), it should be largely possible to pull in changes as-is.
Otherwise, you'll have to manually look through the changes and pick what you consider worthwhile on a case by case basis.

Note, it is important to verify the resulting merge commit for correctness - automatic merge strategies might produce mistakes!
