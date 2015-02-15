Platter
=======

Platter is a tool for Python that simplifies deployments on Unix servers.
It's a thin wrapper around pip, virtualenv and wheel and aids in creating
packages that can install without compiling or downloading on servers.

Why would you want to use it?

*   fastest way to build and distribute Python packages in an ecosystem
    you control.  With the built-in caching we have seen build time
    improvements from 400 seconds down to 20 seconds for releases with no
    version changes on dependencies.
*   no need to compile or download anything on the destination servers you
    distribute your packages too.  Everything (with the exception of the
    interpreter itself) comes perfectly bundled up.
*   100% control over your dependencies.  No accidental version mismatches
    on your servers (this includes system dependencies like setuptools,
    pip and virtualenv).

You can get the tool directly from PyPI::

    $ pip install platter

To create a platter distribution all you need is this::

    $ platter build /path/to/your/python/package

Once this finishes, it will have created a tarball of the fully built
Python package together will all dependencies and an installation script.
You can then take this package and push it to as many servers as you want
and install it::

    $ tar -xzf package-VERSION-linux-x86_64.tar.gz
    $ cd package-VERSION-linux-x86_64
    $ ./install.sh /srv/yourpackage/versions/VERSION
    $ ln -sf VERSION /srv/yourpackage/versions/current

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2

   why
   quickstart
   customizing
   automation

Miscellaneous Pages
-------------------

.. toctree::
   :maxdepth: 2

   changelog
   license
