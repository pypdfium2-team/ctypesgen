import re
import mmap
from pathlib import Path


INCLUDE_RE = re.compile(rb'^\s*\#include\s+(["<][^">]+[">])', re.MULTILINE)

def gather_indirect_includes(filepaths, anchor):
    includes = {}
    for fp in filepaths:
        key = Path(fp).relative_to(anchor)
        includes[key] = []
        with open(fp, "rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            includes[key] += INCLUDE_RE.findall(mm)
    return includes


def filter_relative_includes(includes):
    includes = includes.copy()
    for key, file_includes in includes.items():
        includes[key] = [m.group(1) for i in file_includes if (m := re.match(rb'"(.+)"', i))]
    return includes


def resolve_header_linkage(includes):
    # TODO start with files that have empty lists, then pop these from all others, and recurse until we have resolved everything
    pass
