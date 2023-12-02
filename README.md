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

### Fork rationale

Trying to get through changes upstream is tedious, with unclear outcome, and often not applicable due to mismatched intents (e.g. regarding backwards compatibility). Also consider that isolating commits in separate branches is not feasible anymore as merge conflicts arise (e.g. due to code cleanups and interfering changes).

Contrast this to a fork, which allows us to keep focused and effect improvements quickly, so as to invest pypdfium2 developer time rationally.

### Bugs

Rapid, need-driven development can be prone to oversights or unintentional breakage. Please inform us if you think a change introduces logical issues.
