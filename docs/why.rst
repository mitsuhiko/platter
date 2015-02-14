Why Platter?
============

Platter is not the first software of it's kind that tries to help you with
Python deployments.  The main difference between platter and alternative
solutions is that platter tries to diverage as little from common
deployment scenarios and by providing the highest amount of stability
possible.  Changes to the Python packaging infrastructure will not affect
platter based deployments.

Platter Operation
-----------------

Platter distributions are based on Python wheels.  It creates wheels for
all dependencies of a Python package (including the package itself) and
bundles it together with a installation script.  That script then can
create a brand new virtualenv and installs all dependencies into it.

This ensures that both the version of the system dependencies (setuptools,
pip and wheel) as well as the versions of your own packages are 100%
predictable.  It never uses any packages that naturally come with the
target operating system.

For as long as the platter distribution is installed on a compatible
version of Unix it will install correctly without having to download or
compile any Packages.

Supporting Automated Deployments
--------------------------------

Platter supports the creation of automated deployments.  You can use
platter to create a python distribution on your build server, then
download the tarball and distribute it across all target machines.

You only need to ensure that you use the same major version of Python on
all machines (for instance 2.7.x or 3.4.x).
