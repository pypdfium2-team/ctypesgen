from pathlib import Path
from ctypesgen.includes import *
import rich

headers_dir = Path("~/projects/pypdfium2/data/bindings/headers/").expanduser()
filepaths = list(headers_dir.glob("*.h"))

all_includes = gather_indirect_includes(filepaths, headers_dir)
rel_includes = filter_relative_includes(all_includes)
rich.print(rel_includes)
