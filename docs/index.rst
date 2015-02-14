Platter
====================================

Platter is a utility for Python that simplifies deployments on Unix
servers.  It's a thin wrapper around pip, virtualenv and wheel and aids in
creating packages that can install without compiling or downloading on
servers.

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
    $ ln -sf /srv/yourpackage/versions/VERSION /srv/yourpackage/versions/current

Documentation Contents
----------------------

.. toctree::
   :maxdepth: 2

   why
