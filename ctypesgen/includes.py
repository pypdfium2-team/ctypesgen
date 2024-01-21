import re
import mmap


INCLUDE_RE = re.compile(rb'^\s*\#include\s+(["<][^">]+[">])', re.MULTILINE)

def gather_indirect_includes(filepaths):
    includes = {}
    for fp in filepaths:
        includes[fp] = []
        with open(fp, "rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            includes[fp] += INCLUDE_RE.findall(mm)
    return includes


def resolve_header_deptree():
    pass
