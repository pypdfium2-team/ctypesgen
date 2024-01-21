from pathlib import Path
from ctypesgen.includes import *
import rich

headers_dir = Path("~/projects/pypdfium2/data/bindings/headers/").expanduser()
filepaths = list(headers_dir.glob("**/*.h"))

all, sys, rel = gather_includes(filepaths, search_dirs=[headers_dir])
rich.print(all, sys, rel)
order = resolve_header_order(rel)
rich.print(order)
