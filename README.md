# ctypesgen (pypdfium2-team fork)

ctypesgen is a ctypes wrapper generator for Python.

This is a fork with the objective to better suit the needs of pypdfium2, and address some of the technical debt and (in our opinion) design issues that have accumulated due to highly conservative maintenance.

See https://github.com/pypdfium2-team/ctypesgen/issues/1 for a draft overview of changes in this fork.

See also `--help` for usage, and upstream docs ([readme](https://github.com/ctypesgen/ctypesgen#readme), [wiki](https://github.com/ctypesgen/ctypesgen/wiki)), but note that this fork has diverged somewhat, so parts of it may not apply here anymore.

### System Dependencies

ctypesgen depends on the presence of an external C pre-processor.
We are using GCC at this time, others may or may not work.
