from pathlib import Path
from ctypesgen.includes import *
import rich

headers_dir = Path("~/projects/pypdfium2/data/bindings/headers/").expanduser()
filepaths = list(headers_dir.glob("*.h"))

all_includes = gather_includes(filepaths, headers_dir)
rich.print(all_includes)
rel_includes = filter_relative_includes(all_includes)
rich.print(rel_includes)
order = resolve_header_linkage(rel_includes)
rich.print(order)
