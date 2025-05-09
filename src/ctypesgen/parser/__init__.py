"""
This package parses C header files and generates lists of functions, typedefs,
variables, structs, unions, enums, macros, and constants. This package knows
nothing about the libraries themselves.

The public interface for this package is the function "parse". Use as follows:
>>> descriptions = parse(["inputfile1.h","inputfile2.h"], options)
where "options" is an argparse.Namespace object.

parse() returns a DescriptionCollection object. See ctypesgen.descriptions
for more information.

"""

__all__ = ["parse"]

from .datacollectingparser import DataCollectingParser

def parse(headers, options):
    parser = DataCollectingParser(headers, options)
    parser.parse()
    return parser.data()
