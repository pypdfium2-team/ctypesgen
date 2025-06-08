### Future Research: pcpp (Pure-python C pre-processor)

Making ctypesgen truly pure-python by use of a pure-python C pre-processor is a future area of research.

[pcpp](https://github.com/ned14/pcpp) is a pretty good candidate, and can theoretically be used with ctypesgen already, but it is currently inconvenient to do so, and some issues remain.
In particular, due to its pure-python nature, `pcpp` does not automatically add the platform-specific include paths and default defines as real compilers do, which causes trouble when system headers come into play.

To try ctypesgen with pcpp anyway, you could do e.g. (on RedHat Linux):
```bash
SYSTEM_INCLUDES="-I /usr/lib/gcc/x86_64-redhat-linux/12/include -I /usr/local/include -I /usr/include"
ctypesgen --cpp "pcpp --line-directive '#' --passthru-defines -I . $SYSTEM_INCLUDES" ...
```
Pass `--preproc-savepath ../preproc_out.h` to ctypesgen to save pcpp's output for inspection.

To determine the include paths on your system, consult a compiler:
```bash
COMPILER="gcc"  # or clang
echo | $COMPILER -xc -E -v -
# The paths should now be shown between
# "#include <...> search starts here:" and "End of search list."
```

You may also want to export the default defines from a compiler:
```bash
echo | $COMPILER -dM -E - > ../default_defs.h
```
Then add `../default_defs.h` as positional argument to the pcpp command.

On the other hand, as pcpp maintainer Niall Douglas points out, "if you have to bother doing that, you might as well have it \[gcc\] do the preprocessing too" ([source](https://github.com/ned14/pcpp/issues/85#issuecomment-1860619214)).

<!-- As of June 2025 -->

Also note that `pcpp` does not seem to expand paths in the source directive, which are used for ctypesgen's symbol inclusion logic (so that only symbols from direct input headers are included by default).
As of this writing, the matching rules are loose, i.e. using just names rather than full paths, but if this ever changes and you get an empty output, pass `--all-headers` to ctypesgen to forego symbol filtering.

Another issue is that pcpp may pass through `# include_next` directives, which causes ctypesgen's lexer to fail (any members below an `# include_next` will be missing in the output).
There is currently an open PR upstream that will fix this. To install pcpp with this patch already, you can do:
```bash
git clone --recurse-submodules https://github.com/ned14/pcpp
cd pcpp/
gh pr checkout 98
python3 -m pip install --no-build-isolation -v -e .
```


#### Testing from a real-world project

You can test ctypesgen + pcpp e.g. from within pypdfium2.
Check out its repository and run `just emplace` to get the initial headers.
Then `cd data/bindings/headers/` and do as documented above:

```bash
COMPILER="gcc"  # or clang
echo | $COMPILER -dM -E - > ../default_defs.h
# sample include paths - adapt these to your own system
SYSTEM_INCLUDES="-I /usr/lib/gcc/x86_64-redhat-linux/12/include -I /usr/local/include -I /usr/include"
ctypesgen --cpp "pcpp --line-directive '#' --passthru-defines -I . $SYSTEM_INCLUDES ../default_defs.h" --preproc-savepath ../preproc_out.h -i *.h -o ../bindings.py -l pdfium --compile-libdirs ../../linux_x64/ --runtime-libdirs . --no-symbol-guards --no-macro-guards
```

You can also test with ghostscript (`cd ..` if you are still working from pypdfium2, else repeat the steps to get default defs and includes):
```bash
ctypesgen --cpp "pcpp --line-directive '#' --passthru-defines -I . $SYSTEM_INCLUDES ./default_defs.h" --preproc-savepath ./preproc_out.h -i /usr/include/ghostscript/*.h -o libgs.py -l gs --no-symbol-guards --no-macro-guards
```
