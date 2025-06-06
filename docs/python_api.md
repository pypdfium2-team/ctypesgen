### Binding against the Python C API

ctypesgen can also produce bindings for Python's C API, with some tricks:

```bash
cat > "overrides.py" <<END
import ctypes

class PyTypeObject (ctypes.Structure): pass
class PyObject (ctypes.Structure): pass

def POINTER(obj):
    if obj is PyObject: return ctypes.py_object
    return ctypes.POINTER(obj)
END

PY_VERSION=$(python3 -c "import sys; v = sys.version_info; print(f'{v.major}.{v.minor}')")
ctypesgen -l python --dllclass pythonapi --system-headers python$PY_VERSION/Python.h --all-headers -m .overrides --linkage-anchor . -o ctypes_python.py
```

Small test:
```python
# (run this in a python console to avoid possible GC interference with the example below)
import sys
from ctypes import *
from ctypes_python import *

# Get a string from a Python C API function
v = Py_GetVersion()
v = cast(v, c_char_p).value.decode("utf-8")
print(v)
print(v == sys.version)  # True

# Convert back and forth between Native vs. C view of an object
class Test:
    def __init__(self, a):
        self.a = a

t = Test(a=123)
tc_ptr = cast(id(t), POINTER(PyObject_))
tc = tc_ptr.contents
print(tc.ob_refcnt)  # 1
Py_IncRef(t)
print(tc.ob_refcnt)  # 2 (incremented)
Py_DecRef(t)
print(tc.ob_refcnt)  # 1 (decremented)
t_back = cast(tc_ptr, py_object).value
print(t_back.a)
print(tc.ob_refcnt)  # 2 (new reference from t_back)
```

It should yield something like
```
3.11.6 (main, Oct  3 2023, 00:00:00) [GCC 12.3.1 20230508 (Red Hat 12.3.1-1)]
True
1
2
1
123
2
```
