/* Trivial ctypesgen demo library - Implementation

Build with:
    gcc -fPIC -shared demolib.c -o libdemo.so
Or:
    gcc -fPIC -c demolib.c
    gcc -shared libdemo.o -o libdemo.so
*/

#include "demolib.h"

int trivial_add(int a, int b)
{
    return a + b;
}
