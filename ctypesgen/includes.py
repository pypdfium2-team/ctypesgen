import re
import mmap
from pathlib import Path


INCLUDE_RE = re.compile(rb'^\s*\#include\s+(["<][^">]+[">])', re.MULTILINE)

def gather_includes(filepaths, anchor):
    includes = {}
    for fp in filepaths:
        key = str(Path(fp).relative_to(anchor))
        includes[key] = []
        with open(fp, "rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            includes[key] += INCLUDE_RE.findall(mm)
    return includes


def filter_relative_includes(includes):
    includes = includes.copy()
    for key, file_includes in includes.items():
        includes[key] = [m.group(1).decode() for i in file_includes if (m := re.match(rb'"(.+)"', i))]
    return includes


def resolve_header_linkage(orig_includes):
    order = []
    includes = orig_includes.copy()
    while True:
        satisfied = [p for p, deps in includes.items() if not deps]
        if not satisfied:
            if includes:
                raise RuntimeError(f"Some dependencies could not be satisfied: {includes}")
            break
        for s in satisfied:
            order.append(s)
            includes.pop(s)
        for key, deps in includes.items():
            includes[key] = [d for d in deps if d not in satisfied]
    assert len(order) == len(orig_includes)
    return order
