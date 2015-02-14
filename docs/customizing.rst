Customizing Builds
==================

The default behavior of platter is to create a package that contains the
following structure::

    yourapp-<VERSION>-<PLATFORM>/
        PACKAGE
        VERSION
        PLATFORM
        info.json
        install.sh
        data/
            yourapp-<VERSION>-<PLATFORM>.whl
            yourdependency-<VERSION>-<PLATFORM>.whl
            virtualenv.py
            ...

For your package and all of the dependencies a wheel is created and placed
in the data folder.  Next to the data folder there are some useful files
that contain meta information that is useful for automation (see
:ref:`automation`).

The package is build out of the `setup.py` file that you created for your
project.

Virtualenv and Wheel Pinning
----------------------------

The version of virtualenv, setuptools and wheel that is used for building
this is automatically discovered by default.  It can however be explicitly
provided on the command line in case you encounter a bug with the current
version or the upgrade is incompatible with what you expect::

    $ platter build --virtualenv-version VER --wheel-version VER ./package

Specifying Python Interpreter
-----------------------------

By default the interpreter that is used in the virtualenv of platter is
used.  If you want to build for a different version (for example Python 3)
you can provide it explicitly::

    $ platter build -p python3.4 ./package
