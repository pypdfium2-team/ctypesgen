## Small Demonstration of Ctypesgen

This example shows how bindings for a very simple c-library and associated header can be quickly generated using ctypesgen and accessed by a Python program.

Most of the instructions are included in the top of the various files, but a summary is given here.


### Steps

1. Compile the shared c-library
   ```bash
   gcc -fPIC -shared demolib.c -o demolib.so
   ```

2. (Re)Generate the bindings (or you can just try the bindings that were already generated and saved in this directory)
   ```bash
   ctypesgen -i demolib.h -l demolib -L . -o pydemolib.py
   ```

3. Run the app that uses these newly generated bindings
   ```bash
   python demoapp.py
   ```
   
   The results of this execution should give
   ```
   a 1
   b 2
   result 3
   ```

4. You can also try executing the same code completely from a c-program
   
   - Compile test code:
     ```
     gcc demoapp.c demolib.c demolib.h -o demoapp
     ```
   
   - Execute: `./demoapp`
   
   - Observe the same results as before:
     ```
     a 1
     b 2
     result 3
     ```


### Credits

This demo was originally written by Chris Clark (clach04), when ctypesgen was still residing on `code.google.com`.
