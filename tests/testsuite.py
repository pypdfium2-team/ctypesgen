"""
Simple test suite using unittest.
Aims to test for regressions. Where possible use stdlib to avoid the need to compile C code.

Originally written by clach04 (Chris Clark). Restructured by mara004 (geisserml).

Call:
    python3 -m unittest tests.testsuite
Call a specific test only:
    python3 -m unittest tests.testsuite.[TestCase class].[test name]
    e.g.: python3 -m unittest tests.testsuite.StdBoolTest.test_stdbool_type
or
    pytest -v --showlocals tests/testsuite.py
    pytest -v --showlocals tests/testsuite.py::StdBoolTest::test_stdbool_type

Could use any unitest compatible test runner (nose, etc.)

Note, you may set CLEANUP_OK=0 to retain generated data. This can be useful for inspection.
Further, the test session's C pre-processor may be configured via the CPP env var:
e.g. CPP="clang -E"

Some test cases currently require GCC.
"""

import io
import sys
import os
import ctypes
import math
import unittest
import subprocess
from contextlib import (
    redirect_stdout,
    redirect_stderr,
)

from ctypesgen import VERSION
import ctypesgen.__main__ as ctg_main
from ctypesgen.processor.operations import free_library
from .conftest import (
    cleanup_common,
    generate,
    generate_common,
    ctypesgen_wrapper,
    module_from_code,
    TMP_DIR,
    CTYPESGEN_DIR,
    CLEANUP_OK,
)
from . import json_expects


# ctypes docs say: "On Windows, find_library() searches along the system search path, and returns the full pathname, but since there is no predefined naming scheme a call like find_library("c") will fail and return None."
if sys.platform.startswith("win32"):
    # pick something from %windir%\system32\msvc*dll that includes stdlib
    STDLIB_NAME = "msvcrt"
else:
    STDLIB_NAME = "c"  # libc

if sys.platform.startswith("linux"):
    MATHLIB_NAME = "m"  # libm
else:
    MATHLIB_NAME = STDLIB_NAME


class TestCaseWithCleanup(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        del cls.module


def make_stdlib_test(autostrings):

    class StdlibTestImpl(TestCaseWithCleanup):
            
        @classmethod
        def setUpClass(cls):
            extra_args = []
            if autostrings:
                extra_args.append("--default-encoding")
            cls.module = generate(header=None, args=["--system-headers", "stdlib.h", "-l", STDLIB_NAME, "--symbol-rules", r"if_needed=__\w+", *extra_args])

        def test_getenv_returns_string(self):
            """ Test string return """
            
            if sys.platform == "win32":
                # Check a variable that is already set
                # USERNAME is always set (as is windir, ProgramFiles, USERPROFILE, etc.)
                # The reason for using an existing OS variable is that unless the
                # MSVCRT dll imported is the exact same one that Python was built
                # with you can't share structures, see
                # http://msdn.microsoft.com/en-us/library/ms235460.aspx
                # "Potential Errors Passing CRT Objects Across DLL Boundaries"
                env_var_name = "USERNAME"
                expect_result = os.environ[env_var_name]
                self.assertTrue(expect_result, "this should not be None or empty")
            else:
                env_var_name = "HELLO"
                os.environ[env_var_name] = "WORLD"  # This doesn't work under win32
                expect_result = "WORLD"
            
            if autostrings:
                result = self.module.getenv(env_var_name)
                self.assertIsInstance(result, self.module.ReturnString)
            else:
                result_ptr = self.module.getenv(env_var_name.encode("utf-8"))
                result = ctypes.cast(result_ptr, ctypes.c_char_p).value.decode("utf-8")
            
            self.assertEqual(result, expect_result)


        def test_getenv_returns_null(self):
            """Related to issue 8. Test getenv of unset variable."""
            
            env_var_name = "NOT SET"
            
            try:
                # ensure variable is not set, ignoring not set errors
                del os.environ[env_var_name]
            except KeyError:
                pass
            
            if autostrings:
                result = self.module.getenv(env_var_name)
                self.assertIsInstance(result, self.module.ReturnString)
                self.assertIs(result.raw, None)
            else:
                result_ptr = self.module.getenv(env_var_name.encode("utf-8"))
                result = ctypes.cast(result_ptr, ctypes.c_char_p).value
            
            self.assertEqual(result, None)
    
    return StdlibTestImpl

StdlibTest = make_stdlib_test(False)
StdlibTestAutostrings = make_stdlib_test(True)


class VariadicFunctionTest(TestCaseWithCleanup):
    """ This tests calling variadic functions. """
    
    @classmethod
    def setUpClass(cls):
        cls.module = generate(header=None, args=["--system-headers", "stdio.h", "-l", STDLIB_NAME, "--symbol-rules", r"if_needed=__\w+"])
    
    def test_type_error_catch(self):
        with self.assertRaises(ctypes.ArgumentError):
            # in case this slipped through as binary data, you would see chr(33) = '!' at the end
            self.module.printf(33)
    
    def test_call(self):
        tmp = TMP_DIR/f"out_{type(self).__name__}.txt"
        tmp.touch()
        try:
            c_file = self.module.fopen(str(tmp).encode(), b"w")
            self.module.fprintf(c_file, b"Test variadic function: %s %d", b"Hello", 123)
            self.module.fclose(c_file)
            self.assertEqual(tmp.read_bytes(), b"Test variadic function: Hello 123")
        finally:
            if CLEANUP_OK: tmp.unlink()


class MathTest(TestCaseWithCleanup):

    @classmethod
    def setUpClass(cls):
        header_str = """
#include <math.h>
#define sin_plus_y(x,y) (sin(x) + (y))
"""
        # math.h contains a macro NAN = (0.0 / 0.0) which triggers a ZeroDivisionError on module import, so exclude the symbol.
        # TODO consider adding option like --replace-symbol NAN=float("nan")
        cls.module = generate(header_str, ["-l", MATHLIB_NAME, "--all-headers", "--symbol-rules", "never=NAN", r"if_needed=__\w+"])

    def test_sin(self):
        self.assertEqual(self.module.sin(2), math.sin(2))

    def test_sqrt(self):
        self.assertEqual(self.module.sqrt(4), 2)

    def test_bad_args_string_not_number(self):
        with self.assertRaises(ctypes.ArgumentError):
            self.module.sin("foobar")

    def test_subcall_sin(self):
        """Test math with sin(x) in a macro"""
        self.assertEqual(self.module.sin_plus_y(2, 1), math.sin(2) + 1)


class CommonHeaderTest(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        generate_common()

    @classmethod
    def tearDownClass(cls):
        cleanup_common()
    
    # NOTE `common` is a meta-module hosted by the test class, and {a,b}_{shared,unshared} are the actual python files in question
    
    def test_unshared(self):
        from .common import a_unshared as a
        from .common import b_unshared as b
        
        try:
            self.assertFalse(a.mystruct is b.mystruct)
            m = b.mystruct()
            b.bar(m)
            with self.assertRaises(ctypes.ArgumentError):
                a.foo(m)
        finally:
            # on behalf of windows, we have to free libraries explicitly so the backing file may be deleted afterwards
            free_library(a._libs["common"]._handle)
            free_library(b._libs["common"]._handle)
    
    def test_shared_interop(self):
        from .common import common
        from .common import a_shared as a
        from .common import b_shared as b
        from .common import _ctg_loader as common_loader
        
        try:
            self.assertTrue(common.mystruct is a.mystruct is b.mystruct)
            m = b.mystruct()
            b.bar(m)
            a.foo(m)
        finally:
            # on behalf of windows, we have to free libraries explicitly so the backing file may be deleted afterwards
            free_library(common_loader._libs["common"]._handle)


class StdBoolTest(TestCaseWithCleanup):
    """Test correct parsing and generation of bool type"""

    @classmethod
    def setUpClass(cls):
        header_str = """
#include <stdbool.h>

struct foo {
    bool is_bar;
    int a;
};
"""
        cls.module = generate(header_str)  # ["--all-headers"]

    def test_stdbool_type(self):
        """Test if bool is parsed correctly"""
        struct_foo = self.module.struct_foo
        self.assertEqual(struct_foo._fields_, [("is_bar", ctypes.c_bool), ("a", ctypes.c_int)])


class IntTypesTest(TestCaseWithCleanup):
    """Test correct parsing and generation of different integer types"""

    @classmethod
    def setUpClass(cls):
        header_str = """
struct int_types {
    short t_short;
    short int t_short_int;
    unsigned short t_ushort;
    unsigned short int t_ushort_int;
    int t_int;
    long t_long;
    long int t_long_int;
    long long t_long_long;
    long long int t_long_long_int;
    unsigned long long int t_u_long_long_int;
    long int unsigned long t_long_int_u_long;
};
"""
        cls.module = generate(header_str)

    def test_int_types(self):
        """Test if different integer types are parsed correctly"""
        struct_int_types = self.module.struct_int_types
        self.assertEqual(
            struct_int_types._fields_,
            [
                ("t_short", ctypes.c_short),
                ("t_short_int", ctypes.c_short),
                ("t_ushort", ctypes.c_ushort),
                ("t_ushort_int", ctypes.c_ushort),
                ("t_int", ctypes.c_int),
                ("t_long", ctypes.c_long),
                ("t_long_int", ctypes.c_long),
                ("t_long_long", ctypes.c_longlong),
                ("t_long_long_int", ctypes.c_longlong),
                ("t_u_long_long_int", ctypes.c_ulonglong),
                ("t_long_int_u_long", ctypes.c_ulonglong),
            ],
        )


class SimpleMacrosTest(TestCaseWithCleanup):

    @classmethod
    def setUpClass(cls):
        header_str = """
#define A 1
#define B(x,y) x+y
#define C(a,b,c) a?b:c
#define funny(x) "funny" #x
#define multipler_macro(x,y) x*y
#define minus_macro(x,y) x-y
#define divide_macro(x,y) x/y
#define mod_macro(x,y) x%y
#define subcall_macro_simple(x) (A)
#define subcall_macro_simple_plus(x) (A) + (x)
#define subcall_macro_minus(x,y) minus_macro(x,y)
#define subcall_macro_minus_plus(x,y,z) (minus_macro(x,y)) + (z)
"""
        cls.module = generate(header_str)
        cls.json, _ = generate(header_str, lang="json")

    def _json(self, name):
        for i in SimpleMacrosTest.json:
            if i["name"] == name:
                return i
        raise KeyError("Could not find JSON entry")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        del cls.json

    def test_macro_constant_int(self):
        self.assertEqual(self.module.A, 1)
        self.assertEqual(self._json("A"), {"name": "A", "type": "macro", "value": "1"})

    def test_macro_addition_json(self):
        self.assertEqual(
            self._json("B"),
            {"args": ["x", "y"], "body": "(x + y)", "name": "B", "type": "macro_function"},
        )

    def test_macro_addition(self):
        self.assertEqual(self.module.B(2, 2), 4)

    def test_macro_ternary_json(self):
        self.assertEqual(
            self._json("C"),
            {
                "args": ["a", "b", "c"],
                "body": "a and b or c",
                "name": "C",
                "type": "macro_function",
            },
        )

    def test_macro_ternary_true(self):
        self.assertEqual(self.module.C(True, 1, 2), 1)

    def test_macro_ternary_false(self):
        self.assertEqual(self.module.C(False, 1, 2), 2)

    def test_macro_ternary_true_complex(self):
        """Test ?: with true, using values that can not be confused between True and 1"""
        self.assertEqual(self.module.C(True, 99, 100), 99)

    def test_macro_ternary_false_complex(self):
        """Test ?: with false, using values that can not be confused between True and 1"""
        self.assertEqual(self.module.C(False, 99, 100), 100)

    def test_macro_string_compose(self):
        self.assertEqual(self.module.funny("bunny"), "funnybunny")

    def test_macro_string_compose_json(self):
        self.assertEqual(
            self._json("funny"),
            {"args": ["x"], "body": "('funny' + x)", "name": "funny", "type": "macro_function"},
        )

    def test_macro_math_multipler(self):
        x, y = 2, 5
        self.assertEqual(self.module.multipler_macro(x, y), x * y)

    def test_macro_math_multiplier_json(self):
        self.assertEqual(
            self._json("multipler_macro"),
            {
                "args": ["x", "y"],
                "body": "(x * y)",
                "name": "multipler_macro",
                "type": "macro_function",
            },
        )

    def test_macro_math_minus(self):
        x, y = 2, 5
        self.assertEqual(self.module.minus_macro(x, y), x - y)

    def test_macro_math_minus_json(self):
        self.assertEqual(
            self._json("minus_macro"),
            {
                "args": ["x", "y"],
                "body": "(x - y)",
                "name": "minus_macro",
                "type": "macro_function",
            },
        )

    def test_macro_math_divide(self):
        x, y = 2, 5
        self.assertEqual(self.module.divide_macro(x, y), x / y)

    def test_macro_math_divide_json(self):
        self.assertEqual(
            self._json("divide_macro"),
            {
                "args": ["x", "y"],
                "body": "(x / y)",
                "name": "divide_macro",
                "type": "macro_function",
            },
        )

    def test_macro_math_mod(self):
        x, y = 2, 5
        self.assertEqual(self.module.mod_macro(x, y), x % y)

    def test_macro_math_mod_json(self):
        self.assertEqual(
            self._json("mod_macro"),
            {"args": ["x", "y"], "body": "(x % y)", "name": "mod_macro", "type": "macro_function"},
        )

    def test_macro_subcall_simple(self):
        """Test use of a constant valued macro within a macro"""
        self.assertEqual(self.module.subcall_macro_simple(2), 1)

    def test_macro_subcall_simple_json(self):
        self.assertEqual(
            self._json("subcall_macro_simple"),
            {"args": ["x"], "body": "A", "name": "subcall_macro_simple", "type": "macro_function"},
        )

    def test_macro_subcall_simple_plus(self):
        """Test math with constant valued macro within a macro"""
        self.assertEqual(self.module.subcall_macro_simple_plus(2), 1 + 2)

    def test_macro_subcall_simple_plus_json(self):
        self.assertEqual(
            self._json("subcall_macro_simple_plus"),
            {
                "args": ["x"],
                "body": "(A + x)",
                "name": "subcall_macro_simple_plus",
                "type": "macro_function",
            },
        )

    def test_macro_subcall_minus(self):
        """Test use of macro function within a macro"""
        x, y = 2, 5
        self.assertEqual(self.module.subcall_macro_minus(x, y), x - y)

    def test_macro_subcall_minus_json(self):
        self.assertEqual(
            self._json("subcall_macro_minus"),
            {
                "args": ["x", "y"],
                "body": "minus_macro(x, y)",
                "name": "subcall_macro_minus",
                "type": "macro_function",
            },
        )

    def test_macro_subcall_minus_plus(self):
        """Test math with a macro function within a macro"""
        x, y, z = 2, 5, 1
        self.assertEqual(self.module.subcall_macro_minus_plus(x, y, z), (x - y) + z)

    def test_macro_subcall_minus_plus_json(self):
        self.assertEqual(
            self._json("subcall_macro_minus_plus"),
            {
                "args": ["x", "y", "z"],
                "body": "(minus_macro(x, y) + z)",
                "name": "subcall_macro_minus_plus",
                "type": "macro_function",
            },
        )


def compute_packed(modulo, fields):
    packs = [
        (
            modulo * int(ctypes.sizeof(f) / modulo)
            + modulo * (1 if (ctypes.sizeof(f) % modulo) else 0)
        )
        for f in fields
    ]
    return sum(packs)


class StructuresTest(TestCaseWithCleanup):

    @classmethod
    def setUpClass(cls):
        header_str = """
struct foo {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
};

struct __attribute__((packed)) packed_foo {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
};

typedef struct {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
} foo_t;

typedef struct __attribute__((packed)) {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
} packed_foo_t;

#pragma pack(push, 4)
typedef struct {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
} pragma_packed_foo_t;
#pragma pack(pop)

#pragma pack(push, thing1, 2)
#pragma pack(push, thing2, 4)
#pragma pack(pop)
#pragma pack(push, thing3, 8)
#pragma pack(push, thing4, 16)
#pragma pack(pop, thing3)
struct pragma_packed_foo2 {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
};
#pragma pack(pop, thing1)

struct foo3 {
    int a;
    char b;
    int c;
    int d : 15;
    int   : 17;
};

typedef int Int;

typedef struct {
    int Int;
} id_struct_t;

typedef struct {
    int a;
    char b;
} BAR0, *PBAR0;
"""
        cls.module = generate(header_str)
        cls.json, cls.tmp_header_path = generate(header_str, lang="json")

    def test_struct_json(self):
        json_ans = json_expects.get_ans_struct(self.tmp_header_path)
        json_expects.compare_json(self, StructuresTest.json, json_ans, True)

    def test_fields(self):
        """Test whether fields are built correctly."""
        struct_foo = StructuresTest.module.struct_foo
        self.assertEqual(
            struct_foo._fields_,
            [
                ("a", ctypes.c_int),
                ("b", ctypes.c_char),
                ("c", ctypes.c_int),
                ("d", ctypes.c_int, 15),
                ("unnamed_1", ctypes.c_int, 17),
            ],
        )

    def test_pack(self):
        """Test whether gcc __attribute__((packed)) is interpreted correctly."""
        module = StructuresTest.module
        unpacked_size = compute_packed(4, [ctypes.c_int] * 3 + [ctypes.c_char])
        packed_size = compute_packed(1, [ctypes.c_int] * 3 + [ctypes.c_char])

        struct_foo = module.struct_foo
        struct_packed_foo = module.struct_packed_foo
        foo_t = module.foo_t
        packed_foo_t = module.packed_foo_t
        self.assertEqual(getattr(struct_foo, "_pack_", 0), 0)
        self.assertEqual(getattr(struct_packed_foo, "_pack_", 0), 1)
        self.assertEqual(getattr(foo_t, "_pack_", 0), 0)
        self.assertEqual(getattr(packed_foo_t, "_pack_", -1), 1)
        self.assertEqual(ctypes.sizeof(struct_foo), unpacked_size)
        self.assertEqual(ctypes.sizeof(foo_t), unpacked_size)
        self.assertEqual(ctypes.sizeof(struct_packed_foo), packed_size)
        self.assertEqual(ctypes.sizeof(packed_foo_t), packed_size)

    def test_pragma_pack(self):
        """Test whether #pragma pack(...) is interpreted correctly."""
        module = StructuresTest.module
        packed4_size = compute_packed(4, [ctypes.c_int] * 3 + [ctypes.c_char])
        packed2_size = compute_packed(2, [ctypes.c_int] * 3 + [ctypes.c_char])
        unpacked_size = compute_packed(4, [ctypes.c_int] * 3 + [ctypes.c_char])

        pragma_packed_foo_t = module.pragma_packed_foo_t
        struct_pragma_packed_foo2 = module.struct_pragma_packed_foo2
        struct_foo3 = module.struct_foo3

        self.assertEqual(getattr(pragma_packed_foo_t, "_pack_", 0), 4)
        self.assertEqual(getattr(struct_pragma_packed_foo2, "_pack_", 0), 2)
        self.assertEqual(getattr(struct_foo3, "_pack_", 0), 0)

        self.assertEqual(ctypes.sizeof(pragma_packed_foo_t), packed4_size)
        self.assertEqual(ctypes.sizeof(struct_pragma_packed_foo2), packed2_size)
        self.assertEqual(ctypes.sizeof(struct_foo3), unpacked_size)

    def test_typedef_vs_field_id(self):
        """Test whether local field identifier names can override external
        typedef names.
        """
        module = StructuresTest.module
        Int = module.Int
        id_struct_t = module.id_struct_t
        self.assertEqual(Int, ctypes.c_int)
        self.assertEqual(id_struct_t._fields_, [("Int", ctypes.c_int)])

    def test_anonymous_tag_uniformity(self):
        """Test whether anonymous structs with multiple declarations all resolve
        to the same type.
        """
        module = StructuresTest.module
        BAR0 = module.BAR0
        PBAR0 = module.PBAR0
        self.assertEqual(PBAR0._type_, BAR0)


class EnumTest(TestCaseWithCleanup):
    @classmethod
    def setUpClass(cls):
        header_str = """
typedef enum {
    TEST_1 = 0,
    TEST_2
} test_status_t;
"""
        cls.module = generate(header_str)
        cls.json, cls.tmp_header_path = generate(header_str, lang="json")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        del cls.json

    def test_enum(self):
        self.assertEqual(EnumTest.module.TEST_1, 0)
        self.assertEqual(EnumTest.module.TEST_2, 1)

    def test_enum_json(self):
        json_ans = json_expects.get_ans_enum(self.tmp_header_path)
        json_expects.compare_json(self, EnumTest.json, json_ans, True)


class ParsePrototypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        header_str = """
int bar2(int a);
int bar(int);
void foo(void);
void foo2(void) __attribute__((stdcall));
void * __attribute__((stdcall)) foo3(void);
void * __attribute__((stdcall)) * foo4(void);
void foo5(void) __attribute__((__stdcall__));
"""
        cls.json, _ = generate(header_str, lang="json")

    @classmethod
    def tearDownClass(cls):
        del cls.json

    def test_function_prototypes_json(self):
        json_ans = json_expects.get_ans_function_prototypes()
        json_expects.compare_json(self, self.json, json_ans, True)


class CallPrototypesTest(TestCaseWithCleanup):
    """Test usability of function prototypes."""
    
    @classmethod
    def setUpClass(cls):
        header_str = """
typedef int (*FP_Primitive)(void* my_value);

typedef struct {
    int a;
} MyStruct;
typedef int (*FP_CustomArgtype)(MyStruct* my_struct);
typedef MyStruct* (*FP_CustomRestype)(MyStruct* my_struct);
"""
        cls.module = generate(header_str)

    def test_primitive(self):
        """Test passthrough of primitive value."""
        F = self.module.FP_Primitive(lambda x: x)
        self.assertEqual(F.argtypes, (ctypes.c_void_p,))
        # make sure the UNCHECKED template did not affect the primitive type
        self.assertEqual(F.restype, ctypes.c_int)
        # ctypes autoconverts int -> c_void_p and c_int -> int
        self.assertEqual(F(100), 100)
    
    def test_custom_argtype(self):
        """Test non-primitive argtype (struct pointer)."""
        F = self.module.FP_CustomArgtype(lambda s: s.contents.a)
        self.assertEqual(F.argtypes, (ctypes.POINTER(self.module.MyStruct),))
        self.assertEqual(F.restype, ctypes.c_int)
        struct = self.module.MyStruct(a=10)
        self.assertEqual(F(struct), 10)
    
    def test_custom_restype(self):
        """ Test custom pointer result type (UNCHECKED() template). """
        mod = self.module
        F = mod.FP_CustomRestype(lambda x: ctypes.addressof(x.contents))
        self.assertEqual(F.argtypes, (ctypes.POINTER(mod.MyStruct),))
        # The custom type is transfomred into a primitive type (c_void_p) by ctypesgen, because ctypes does not support custom pointer return types on callbacks
        self.assertEqual(F.restype, ctypes.c_void_p)
        struct = mod.MyStruct(a=10)
        struct_back = mod.MyStruct.from_address( F(struct) )
        self.assertEqual(struct.a, struct_back.a)



class LongDoubleTest(TestCaseWithCleanup):
    """Test correct parsing and generation of 'long double' type"""

    @classmethod
    def setUpClass(cls):
        header_str = """
struct foo {
    long double is_bar;
    int a;
};
"""
        cls.module = generate(header_str)  # ["--all-headers"]

    def test_longdouble_type(self):
        """Test if long double is parsed correctly"""
        module = LongDoubleTest.module
        struct_foo = module.struct_foo
        self.assertEqual(
            struct_foo._fields_, [("is_bar", ctypes.c_longdouble), ("a", ctypes.c_int)]
        )


class CommandParserTest(unittest.TestCase):
    """
    Test the CLI parser by calling into ctypesgen's main entrypoint, through the python API.
    
    Note, this does not actually test ctypesgen features, just the entrypoint and parser.
    "Real" ctypesgen calls are emitted through the generate() function in other test cases.
    """
    
    @staticmethod
    def _run(args):
        out, err, rc = io.StringIO(), io.StringIO(), None
        with redirect_stdout(out), redirect_stderr(err):
            try:
                ctypesgen_wrapper(args, echo=False)
            except SystemExit as e:
                rc = e.code
        return out.getvalue(), err.getvalue(), rc
    
    def test_version(self):
        """Test version string reported by CLI"""
        out, err, rc = self._run(["--version"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.strip(), VERSION)
        self.assertEqual(err, "")

    def test_help(self):
        """Test showing help"""
        out, err, rc = self._run(["--help"])
        # print(f"{rc}:\n{out}\n{err}")
        self.assertEqual(rc, 0)
        self.assertTrue(out.splitlines()[0].startswith("usage: ctypesgen"))
        self.assertGreater(len(out), 3000)  # it's long, so it'll be the generated help
        self.assertEqual(err, "")


class ConstantsTest(TestCaseWithCleanup):
    """Test correct parsing and generation of NULL"""

    @classmethod
    def setUpClass(cls):
        header_str = """
#define I_CONST_HEX 0xAFAFAFu
#define I_CONST_DEC 15455u
#define I_CONST_OCT 0433u
#define I_CONST_BIN 0b0101L
#define I_ZERO 0
#define I_ONE 1
#define I_ZERO_SUF 0L

#define F_CONST_1 155e+0L
#define F_CONST_2 35.2e+0f
#define F_CONST_3 35.e+0f
#define F_CONST_4 0xAFp012l
#define F_CONST_5 0x1.FFFFFEp+127f
#define F_CONST_6 0xAFAF.p35f

struct foo {
    int a;
    char b;
    int c: 0b10;
    int d : 0xf;
    int : 17;
};

#define CHAR_CONST u'🍌'
"""
        cls.module = generate(header_str)

    def test_integer_constants(self):
        """Test if integer constants are parsed correctly"""
        self.assertEqual(ConstantsTest.module.I_CONST_HEX, 0xAFAFAF)
        self.assertEqual(ConstantsTest.module.I_CONST_DEC, int(15455))
        self.assertEqual(ConstantsTest.module.I_CONST_OCT, 0o433)
        self.assertEqual(ConstantsTest.module.I_CONST_BIN, 0b0101)
        self.assertEqual(ConstantsTest.module.I_CONST_BIN, 5)
        self.assertEqual(ConstantsTest.module.I_ZERO, int(0))
        self.assertEqual(ConstantsTest.module.I_ONE, int(1))
        self.assertEqual(ConstantsTest.module.I_ZERO_SUF, int(0))

    def test_floating_constants(self):
        """Test if floating constants are parsed correctly"""
        self.assertEqual(ConstantsTest.module.F_CONST_1, 155e0)
        self.assertEqual(ConstantsTest.module.F_CONST_2, 35.2e0)
        self.assertEqual(ConstantsTest.module.F_CONST_3, 35.0e0)
        self.assertEqual(ConstantsTest.module.F_CONST_4, float.fromhex("0xAFp012"))
        self.assertEqual(ConstantsTest.module.F_CONST_5, float.fromhex("0x1.fffffep+127"))
        self.assertEqual(ConstantsTest.module.F_CONST_6, float.fromhex("0xAFAF.p35"))

    def test_struct_fields(self):
        """Test whether fields are built correctly."""
        struct_foo = ConstantsTest.module.struct_foo
        self.assertEqual(
            struct_foo._fields_,
            [
                ("a", ctypes.c_int),
                ("b", ctypes.c_char),
                ("c", ctypes.c_int, 2),
                ("d", ctypes.c_int, 15),
                ("unnamed_1", ctypes.c_int, 17),
            ],
        )

    def test_character_constants(self):
        """Test char constants"""
        self.assertEqual(ConstantsTest.module.CHAR_CONST, "🍌")


class NULLTest(TestCaseWithCleanup):
    "Test correct parsing and generation of NULL"

    @classmethod
    def setUpClass(cls):
        header_str = "#define A_NULL_MACRO NULL\n"
        cls.module = generate(header_str)  # ["--all-headers"]

    def test_null_type(self):
        """Test if NULL is parsed correctly"""
        self.assertEqual(self.module.A_NULL_MACRO, None)


@unittest.skipUnless(sys.platform == "darwin", "requires Mac")
class MacromanEncodeTest(TestCaseWithCleanup):
    """Test if source file with mac_roman encoding is parsed correctly.

    This test is skipped on non-mac platforms.
    """

    @classmethod
    def setUpClass(cls):
        cls.mac_roman_file = TMP_DIR/"mac_roman.h"
        mac_header_str = b"""
        #define kICHelper                       "\xa9\\pHelper\xa5"

        """

        with open(cls.mac_roman_file, "wb") as mac_file:
            mac_file.write(mac_header_str)

        header_str = f"""
        #include "{cls.mac_roman_file}"

        #define MYSTRING kICHelper

        """

        cls.module = generate(header_str)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if CLEANUP_OK: cls.mac_roman_file.unlink()

    def test_macroman_encoding_source(self):
        module = MacromanEncodeTest.module
        expected = b"\xef\xbf\xbd\\pHelper\xef\xbf\xbd".decode("utf-8")
        self.assertEqual(module.MYSTRING, expected)


class EmptyHeaderTest(unittest.TestCase):
    """ Test how ctypesgen behaves when no members were found. """
    
    @classmethod
    def setUpClass(cls):
        cls.infile = TMP_DIR/"empty_header.h"
        cls.outfile = TMP_DIR/"empty_output.py"
        cls.infile.write_text("// this is an empty header\n")
    
    @classmethod
    def tearDownClass(cls):
        if CLEANUP_OK: cls.infile.unlink()
    
    def test_empty_header(self):
        with self.assertRaises(RuntimeError, msg="No target members found."):
            ctypesgen_wrapper(["-i", self.infile, "-o", self.outfile])
        self.assertFalse(self.outfile.exists())


class FAMTest(unittest.TestCase):
    """
    Test that flexible array members (FAMs) are handled as zero-sized arrays
    rather than as pointer types.
    See GH issue #219. Thanks to @Natanel-Shitrit.
    """
    
    @classmethod
    def setUpClass(cls):
        header_str = """
#include <stdint.h>

// Header struct with flexible array member
struct msg_header {
    uint32_t size;        // Total size of the message
    uint8_t type;         // Type of the message
    uint8_t payload[];    // Flexible array member
};

// First message type
// Note that nesting a struct with FAM may not conform with the C standard,
// but there are real-world headers in the wild which do this, and compilers
// seem to tolerate it, so it's still good to handle FAMs properly as
// zero-sized arrays to avoid wrong offsets in these cases.
struct msg_type1 {
    struct msg_header header;
    uint32_t value1;
    uint32_t value2;
    uint8_t extra[];      // Flexible array member for additional data
};

// Second message type
struct msg_type2 {
    struct msg_header header;
    uint64_t timestamp;
    uint8_t extra[];      // Flexible array member for additional data
};

// Union to access either just the header or the complete message
union message {
    struct msg_header header;
    struct msg_type1 type1;
    struct msg_type2 type2;
};

// A function declaration with empty array syntax, which should be handled
// as pointer (not as zero-sized array) here
void arraytest(int a[]);
"""
        
        # this is some extra work, but build an actual dummy library so we can test the function
        c_str = """\
#include "test_fam.h"\n
void arraytest(int a[]) { };
"""
        cls.h_path = TMP_DIR/"test_fam.h"
        cls.c_path = TMP_DIR/"test_fam.c"
        cls.h_path.write_text(header_str)
        cls.c_path.write_text(c_str)
        libname = "famtest.dll" if sys.platform == "win32" else "libfamtest.so"
        cls.libpath = TMP_DIR/libname
        subprocess.run(["gcc", "-shared", "-o", str(cls.libpath), str(cls.c_path)], check=True)
        cls.module = generate(None, ["-i", cls.h_path, "-l", "famtest", "--compile-libdirs", str(TMP_DIR), "--runtime-libdirs", "."], spoof_dir=TMP_DIR)
    
    @classmethod
    def tearDownClass(cls):
        if not CLEANUP_OK: return
        cls.h_path.unlink()
        cls.c_path.unlink()
        cls.libpath.unlink()
    
    def test_types(self):
        # make sure the FAM fields are zero-sized arrays
        m = self.module
        msg_header_f = dict(m.msg_header._fields_)
        msg_type1_f = dict(m.msg_type1._fields_)
        msg_type2_f = dict(m.msg_type2._fields_)
        self.assertEqual(msg_header_f["payload"], ctypes.c_uint8 * 0)
        self.assertEqual(msg_type1_f["extra"], ctypes.c_uint8 * 0)
        self.assertEqual(msg_type2_f["extra"], ctypes.c_uint8 * 0)
        self.assertEqual(m.arraytest.argtypes, [ctypes.POINTER(ctypes.c_int)])
    
    def test_object(self):
        payload = "0123456789".encode("ascii")
        size = len(payload)
        typeval = 1
        
        test_data = bytearray(ctypes.c_uint32(size)) + bytearray(ctypes.c_uint8(typeval)) + bytearray(payload)
        
        obj = self.module.msg_header.from_buffer(test_data)
        self.assertEqual(obj.size, size)
        self.assertEqual(obj.type, typeval)
        
        # alternatively:
        # payload_back = ctypes.cast(obj.payload, ctypes.POINTER(ctypes.c_uint8 * size)).contents
        payload_back = (ctypes.c_uint8 * size).from_address(ctypes.addressof(obj.payload))
        self.assertEqual(payload, bytes(payload_back))


class DefUndefTest(unittest.TestCase):
    """
    Test handling of defines/undefines passed to ctypesgen.
    Checks order, defaults, and overrides of defaults.
    """
    
    def test_ordered_passthrough(self):
        m = generate("", [*"-D A=1 B=2 C=3 -U B -D B=0 -U C".split(" "), "--symbol-rules", "yes=A|B|C"])
        self.assertEqual(m.A, 1)
        self.assertEqual(m.B, 0)
        self.assertFalse(hasattr(m, "C"))
    
    def test_default_undef(self):
        # this actually works because the def/undef are taken over into the output, so we won't get a "no target members" exception.
        m = generate("", ["--symbol-rules", "yes=__GNUC__"], cpp=f"gcc -E", allow_gnuc=False)
        self.assertFalse(hasattr(m, "__GNUC__"))
    
    def test_override_default_undef(self):
        m = generate("", ["--symbol-rules", "yes=__GNUC__"], cpp=f"gcc -E", allow_gnuc=True)
        self.assertIsInstance(m.__GNUC__, int)  # this will be the GCC major version
    
    def test_default_def(self):
        m = generate("", ["--symbol-rules", "yes=CTYPESGEN"])
        self.assertEqual(m.CTYPESGEN, 1)
    
    def test_override_default_def(self):
        # here we have to define a placeholder to bypass the "no target members" exception
        m = generate("#define PLACEHOLDER 1", ["-X", "CTYPESGEN", "--symbol-rules", "yes=CTYPESGEN"])
        self.assertFalse(hasattr(m, "CTYPESGEN"))


class APITest(unittest.TestCase):
    """ Test that calling ctypesgen through the api_main() entrypoint works """
    
    @classmethod
    def setUpClass(cls):
        cls.outpath = TMP_DIR/"apimain_stdio.py"
        ctg_main.api_main({
            "system_headers": ["stdio.h"],
            "library": STDLIB_NAME,
            "symbol_rules": [r"if_needed=__\w+"],
            "output": cls.outpath,
        })
        cls.module = module_from_code("tmp_module", cls.outpath.read_text())
    
    @classmethod
    def tearDownClass(cls):
        if not CLEANUP_OK: return
        cls.outpath.unlink()
    
    def test_content(self):
        # FIXME the double backslash is actually wrong
        exp_docstring = R"""
Auto-generated by:
ctypesgen.api_main(
{'library': '%s',
 'output': %s,
 'symbol_rules': ['if_needed=__\\w+'],
 'system_headers': ['stdio.h']}
)
""" % (STDLIB_NAME, repr(self.outpath).replace(str(CTYPESGEN_DIR), "."), )
        self.assertEqual(self.module.__doc__, exp_docstring)
        self.assertTrue(hasattr(self.module, "printf"))
