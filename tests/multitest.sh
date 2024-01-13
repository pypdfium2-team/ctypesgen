#!/usr/bin/env bash

# run the test suite multiple times with different configs

SCRIPTDIR=$(dirname -- "$(readlink -f -- "$BASH_SOURCE")")

for cppname in "gcc -E" "cpp" "clang -E";
  do
    echo "$cppname"
    CPP="$cppname" CLEANUP_OK=1 python -m pytest $SCRIPTDIR/testsuite.py -sv
    printf "\n\n\n"
  done

CLEANUP_OK=0 python -m pytest $SCRIPTDIR/testsuite.py -sv
