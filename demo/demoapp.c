/* C consumer of trivial ctypesgen demo library

Build static:
    cc demoapp.c demolib.c demolib.h -o demoapp
*/

#include <stdlib.h>
#include <stdio.h>

#include "demolib.h"

int main(int argc, char **argv)
{
    int a = 1;
    int b = 2;
    int result = 0;

    result = trivial_add(a, b);
    printf("a %d\n", a);
    printf("b %d\n", b);
    printf("result %d\n", result);
}
