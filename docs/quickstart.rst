Quickstart
==========

To create platter packages you need an installation of Python 2.7.  Note
that platter does support the creation of Python 3 packages but itself is
running on 2.x only.

Platter can be installed into a virtual environment with ``pip``::

    $ virtualenv venv
    $ ./venv/bin/pip install platter

It's recommended to install platter into it's own virtualenv as it has
it's own dependencies that might otherwise interfere with your system.
However all packages build with platter are themselves created in a
separate virtualenv.

Building Platter Packages
-------------------------

In order to create a platter package you need a setuptools based
distribution.  This means you need to have a ``setup.py`` file for your
package.  If you do not have one, consult the `setuptools documentation
<https://pythonhosted.org/setuptools/>`__ for more information.

To then create a distribution all you need to do is to invoke ``platter
build`` with the path to your package::

    $ platter build /path/to/yourpackage

This will download all dependencies, compile all extension modules and
pack them up.  The resulting artifact will be created in a folder called
`dist` in the current directory.

Alternatively you can also instruct platter to not create a final tarball
and to instead just create a folder with all files::

    $ platter build --format=dir /path/to/yourpackage

Installing Platter Packages
---------------------------

Once you have created such a platter package you can distribute it to
different servers and install it there.  Inside the tarball there is an
install script ``install.sh`` which will install the platter package into
a fresh and isolated virtualenv.  Note that virtualenv itself is packaged
up together in the platter tarball and the system version will *not* be
used.

To install the package you can do something like this::

    $ tar -xzf package-VERSION-linux-x86_64.tar.gz
    $ cd package-VERSION-linux-x86_64
    $ ./install.sh /srv/yourpackage/versions/VERSION
    $ ln -sf VERSION /srv/yourpackage/versions/current

Note that platter tarballs have a lot of support for automatic
deployments.  For more information see :ref:`automation`.
