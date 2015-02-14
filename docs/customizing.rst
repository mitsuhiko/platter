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

    $ platter build --virtualenv-version VER ./package
    $ platter build --wheel-version VER ./package

Specifying The Python Interpreter
---------------------------------

By default the interpreter that is used in the virtualenv of platter is
used.  If you want to build for a different version (for example Python 3)
you can provide it explicitly::

    $ platter build -p python3.4 ./package

Passing pip Options
-------------------

By default pip will execute without any extra arguments when building
wheels.  There are two ways to pass extra arguments to pip.  The first is
to set environment variables.  These will also be used by the pip process
that platter launches.  The second option is to pass them on the command
line.  For instance if you want to change the pip cache you can use this
command::

    $ platter build --pip-option='--cache-dir=.cache' ./package

Extra Requirements
------------------

By default the dependencies are pulled from the ``setup.py`` file.  In
some circumstances it is a good idea to define extra dependencies in a
requirements file.  This is useful for instance if you have optional
dependencies like database drivers that only apply for the production
deployment but are not a strict requirement for the package itself.

In that case the ``--requirements`` (or ``-r``) flag comes in useful.  It
can point to a requirements file::

    $ platter build -r requirements.txt ./package

Custom Post-Build Scripts
-------------------------

While platter is perfectly capable of creating Python distributions, it
might encounter problems if you also want to ship other things with your
application that are not native to the Python ecosystem.  A good example
for this is your application also wants to install some node-js modules
into the virtualenv for instance.

In this case you can provide a custom post-build script that is executed
after the regular build and before packaging up.  It can add additional
data to the archive and also emit commands that end up in the install
script.

The script needs to be executable and is invoked with some environment
variables.  The following environment variables exist:

=================== ===================================================
Variable            Description
=================== ===================================================
``HERE``            The path of the root folder in the archive.  This
                    is the folder where the install script ends up in
                    and the parent folder of the data directory.  This
                    is where you can place additional metadata for
                    instance.  This is also guarnateed to be the
                    working directory of the script.
``DATA_DIR``        The path of the bundled ``data`` folder in the
                    archive.  This is useful when you want to add more
                    data into the data directory.
``SOURCE_DIR``      The path of the source directory.  This is the
                    directory of the Python package (the parent folder
                    of the ``setup.py`` file).
``SCRATCHPAD``      A temporary folder provided for the script which
                    is deleted after the execution.  This is useful
                    when you need to temporarily create files.
``INSTALL_SCRIPT``  The path to a auxilary installation script.  You
                    can echo install commands to this path and they
                    are added to ``install.sh`` automatically.
``VIRTUAL_ENV``     The path to the virtual env that has been used for
                    building the package.  This can come in useful
                    when you need to start a python interpreter or
                    launch an executable in the venv.  Note that the
                    virtualenv is also guarnateed to be active.
=================== ===================================================

The variables ``HERE``, ``DATA_DIR`` and ``VIRTUAL_ENV`` are also
available in the install script.

The build script can be provided to the build command with the
``--postbuild-script`` parameter::

    $ platter build --postbuild-script=build.sh ./package

An example build script that ships a ``npm`` module in the virtualenv can
look like this:

.. sourcecode:: bash

    #!/bin/bash
    set -eu

    (cd "$DATA_DIR"; npm install --production uglify-js)

    cat << "EOF" >> "$INSTALL_SCRIPT"
    cp -R "$DATA_DIR/node_modules" "$VIRTUAL_ENV"
    ln -s "../node_modules/.bin/uglifyjs" "$VIRTUAL_ENV/bin"
    EOF

This will install a node executable into the virtualenv and then link the
executable into the virtualenv's bin folder.  What's piped into the
``$INSTALL_SCRIPT`` is added as commands to the ``install.sh`` script.
Note that the double quoting of ``EOF`` (``"EOF"``) disables the
interpolation so the variables are expanded at installation time, not at
build time!

Enabling Wheel Caches
---------------------

The default behavior of platter is to not cache wheels.  The main reason
for this is that wheels do not carry enough information so that they can
be distinguished in all cases.  This does not cause a problem for most
users, but it can for some.  For instance UC2 and UC4 builds of the same
Python version are incompatible.

However wheel caching can be enabled.  In that case, after the second time
you create a platter distribution of the same dependency, platter will not
recompile a wheel it has already seen before.

To enable this feature, you can pass ``--wheel-cache`` to the build
command::

    $ platter build --wheel-cache=/tmp/wheelhouse ./package
