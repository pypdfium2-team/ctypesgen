# ctypesgen (pypdfium2-team fork)

ctypesgen is a ctypes wrapper generator for Python.

This is a fork with the objective to better suit the needs of pypdfium2, and address some of the technical debt and (in our opinion) design issues that have accumulated due to highly conservative maintenance.

See also `--help` for usage, and upstream docs ([readme](https://github.com/ctypesgen/ctypesgen#readme), [wiki](https://github.com/ctypesgen/ctypesgen/wiki)), but note that this fork has diverged somewhat, so parts of it may not apply here anymore.

See https://github.com/pypdfium2-team/ctypesgen/issues/1 for a draft overview of changes in this fork. Further, here are some notes on our development intents:
* We do not mind API-breaking changes at this time.
* We endeavor to use plain ctypes as much as possible and keep the template lean. Contrast this to upstream ctypesgen, which clogs up the bindings with custom wrappers.
* For now, we only envisage to work with ctypesgen's higher-level parts (e.g. the printer). The parser backend may be out of our scope.

### System Dependencies

ctypesgen depends on the presence of an external C pre-processor.
We are only testing with GCC at this time, others may or may not work.

### Tips & Tricks

* If you encounter a broken macro, use `--exclude-symbols` or replace it manually. This can be necessary with C constructs like `#define NAN (0.0f / 0.0f)` that don't play well with python.
* To provide extra dependency headers that are not present in the system, you can set the `CPATH` or `C_INCLUDE_PATH` env vars for the C pre-processor. It may also be possible to use this for "cross-compilation" of bindings, or to spoof an optional foreign symbol using `typedef void* SYMBOL;` (`c_void_p`).
* If you have multiple libraries that are supposed to interoperate with shared symbols, first create bindings to any shared headers and then use the `-m / --link-modules` option on dependents. (Otherwise, you'd create duplicate symbols that are formally different types, with need to cast between them.)

### Known Limitations

* We only support the regular `cdecl` calling convention at this time. Restoring the windows-only `stdcall` convention is planned. Note that ctypes cannot handle other rare calling conventions, as of this writing.

### Bugs

Rapid, need-driven development can be prone to oversights or unintentional breakage. Please inform us if you think a change introduces logical issues.

### Fork rationale

Trying to get through changes upstream is tedious, with unclear outcome, and often not applicable due to mismatched intents (e.g. regarding backwards compatibility). Also consider that isolating commits in separate branches is not feasible anymore as merge conflicts arise (e.g. due to code cleanups and interfering changes).

Contrast this to a fork, which allows us to keep focused and effect improvements quickly, so as to invest pypdfium2 developer time rationally.
