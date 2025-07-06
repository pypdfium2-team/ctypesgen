#!/usr/bin/env python3
"""
Python consumer of trivial ctypesgen demo library

pydemolib can be generated via:
    ctypesgen -i demolib.h -l demolib -L . -o pydemolib.py
"""

import sys
import pydemolib  # generated from demolib.h by ctypesgen


def do_demo():
    a = 1
    b = 2
    result = pydemolib.trivial_add(a, b)
    print("a", a)
    print("b", b)
    print("result", result)


def main():
    do_demo()
    return 0


if __name__ == "__main__":
    sys.exit(main())
