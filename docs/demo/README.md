## Small demonstration of ctypesgen

This example shows how to quickly generate bindings for a simple C library using ctypesgen and access them in a Python script.


### Steps

1. Compile the shared C library
   ```bash
   gcc -fPIC -shared demolib.c -o demolib.so
   ```

2. (Re-)Generate the bindings (or you can just try the pre-generated bindings already present in this directory)
   ```bash
   ctypesgen -i demolib.h -l demolib -L './{name}.{suffix}' -o pydemolib.py
   ```

3. Run the app that uses these generated bindings
   ```bash
   python demoapp.py
   ```
   
   The call should yield the following output:
   ```
   a 1
   b 2
   result 3
   ```

4. You can also try calling the same code from a C executable
   
   - Compile test code:
     ```
     gcc demoapp.c demolib.c demolib.h -o demoapp
     ```
   
   - Run `./demoapp`
   
   - Observe the same results as before:
     ```
     a 1
     b 2
     result 3
     ```


### Credits

This demo was originally written by Chris Clark (clach04), when ctypesgen was still residing on `code.google.com`.
