Why Platter?
============

Platter is not the first software of it's kind that tries to help you with
Python deployments.  The main difference between platter and alternative
solutions is that platter tries to diverge as little from common
deployment scenarios and by providing the highest amount of stability and
speed possible.  Changes to the Python packaging infrastructure will not
affect platter based deployments.

See also the the :ref:`why-not` headline for some differences with
alternatives.

Platter also places a lot of emphasis on automation.  Both the build and
the installation process provides a lot of helpers for automatic usage
through assisting tools.

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

Why Not …?
----------

Platter is hardly the first package that tries to help with deployments.
And it's also not the last one that there will be.  In fact, there is a
good chance Platter might not be the tool for you.

Pex
```

A popular deployment tool for Python is Twitter's `pex
<https://pex.readthedocs.org/en/latest/>`_.  Platter and pex have very
little in common other than that they are both intended for deploying
things.  Pex can be compared to jar files in Java.  They contain an
application in its entirety together with a virtualenv and provide various
ways to interact with the contained application.

Pex is perfect for things such as command line applications that are
written in Python, but also for various deployment scenarios that go above
that.

Platter on the other hand isn't anywhere this fancy.  Platter has two
primary goals: be fast and be simple.  Platter acknowledges that there are
more things in an application than Python code and things that can execute
from zipfiles.  As such upon installation it just places a virtualenv on
the file system and anything contained within works as normally.  This is
very useful when an application also needs to ship other files (such as
config files, static media files, node.js modules etc.).  Everything just
ends up on the filesystem and is within an arm's reach.

venv-update
```````````

An alternative approach to fast deployment's is Yelp's `venv-update
<https://github.com/Yelp/venv-update>`_.  It tries to make things fast by
figuring out the least amount of changes necessary to a virtualenv.
This approach works reasonably well but causes problems if you want to move
a virtualenv around.  For instance it's not ideal if you want to have a
version specific installation for quick rollbacks.

Some testing also does not reveal a noticable performance improvement of
`venv-update` over platter.

Docker
``````

Platter and Docker are good friends, but one does not replace the other.
It makes a lot of sense to install a platter distribution into a docker
container but it's probably not the best idea to use Docker alone.  The
reason for this is that Platter allows you to isolate the process of
building and deploying, keeping the final server clean of unnecessary
development dependencies (compilers etc.).  It also means that you can
disconnect your final deployment container entirely from the internet for
security reasons.  From the start.
