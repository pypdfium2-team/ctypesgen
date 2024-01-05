/* Trivial ctypesgen demo library

Build with:
    gcc -fPIC -shared demolib.c -o demolib.so
Or:
    gcc -fPIC -c demolib.c
    gcc -shared demolib.o -o demolib.so
*/

#include "demolib.h"

int trivial_add(int a, int b)
{
    return a + b;
}
