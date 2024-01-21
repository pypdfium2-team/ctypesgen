from pathlib import Path
from ctypesgen.includes import gather_indirect_includes
import rich

headers_dir = Path("~/projects/pypdfium2/data/bindings/headers/").expanduser()
filepaths = list(headers_dir.glob("*.h"))

includes = gather_indirect_includes(filepaths)
rich.print(includes)
