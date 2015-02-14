Welcome to the Platter Documentation
====================================

Platter is a utility for Python that simplifies deployments on Unix
servers.  It's a thin wrapper around pip, virtualenv and wheel and aids in
creating packages that can install without compiling or downloading on
servers.

You can get the tool directly from PyPI::

    pip install platter

Or if you have `pipsi <https://github.com/mitsuhiko/pipsi>`_ you can
install it that way as well::

    pipsi install platter

To create a platter distribution all you need is this::

    platter build /path/to/your/python/package

And you're good to go.

Contents:

.. toctree::
   :maxdepth: 2

   why
