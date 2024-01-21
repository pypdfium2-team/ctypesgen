import re
import mmap


INCLUDE_RE = re.compile(rb'^\s*\#include\s+(["<][^">]+[">])', re.MULTILINE)

def _get_path(name, dirs):
    for d in dirs:
        path = (d/name).resolve()
        if path.exists(): return path
    assert False, f'Could not resolve #include "{name}" to full path'

def gather_includes(filepaths, search_dirs=[]):
    raw, sys, rel = {}, {}, {}
    for p in filepaths:
        raw[p], sys[p], rel[p] = [], [], []
        with p.open("rb") as fh:
            data = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            for include in INCLUDE_RE.finditer(data):
                include = include.group(1).decode()
                raw[p].append(include)
                if m := re.fullmatch(r'<(.+)>', include):
                    sys[p].append( m.group(1) )
                elif m := re.fullmatch(r'"(.+)"', include):
                    rel[p].append( _get_path(m.group(1), [p.parent, *search_dirs]) )
                else:
                    assert False
    return raw, sys, rel


def resolve_header_order(orig_includes):
    order = []
    includes = orig_includes.copy()
    while includes:
        satisfied = [p for p, deps in includes.items() if not deps]
        if not satisfied:
            raise RuntimeError(f"Unsatisfiable dependencies at resolution state {includes}")
        for s in satisfied:
            order.append(s)
            includes.pop(s)
        for key, deps in includes.items():
            includes[key] = [d for d in deps if d not in satisfied]
    assert len(order) == len(orig_includes)
    return order
