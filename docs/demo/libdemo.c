/* Trivial ctypesgen demo library - Implementation

Build with:
    gcc -fPIC -shared libdemo.c -o libdemo.so
Or:
    gcc -fPIC -c libdemo.c
    gcc -shared libdemo.o -o libdemo.so
*/

#include "libdemo.h"

int trivial_add(int a, int b)
{
    return a + b;
}
