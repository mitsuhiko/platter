Frequently Asked Questions
==========================

These are some questions that came up about the library.

Can I use it on a Plane?
------------------------

Platter will automatically use two levels of caching.  The first level of
caching is done by pip which will automatically cache downloaded packages
in its local download cache.  This allows pip to not download source
archives if it has already downloaded them.  This still needs internet
access however.  The second level of caching is the caching of entire
pre-compiled wheels.  Platter by default will place wheels in a wheel
cache.  It will still contact the internet to check for updates according
to the version specification but you can disable this behavior by passing
``--no-download`` to the build command.

Where are Wheels Cached?
------------------------

This depends on your operating system:

=================== ===================================================
Operating System    Path
=================== ===================================================
Linux               ~/.cache/platter
OS X                ~/Library/Caches/platter
Windows             %LOCALAPPDATA%/platter/Cache
=================== ===================================================

How Can I Clean the Cache?
--------------------------

Either delete that folder yourself or run ``platter clean-cache``.

Is the Cache Safe?
------------------

The cache is not particularly safe if you use multiple different Python
versions next to each other in some circumstances.  Normally you should
not run into any issues except if you run different Pythons compiled
against different libc's or unicode versions.

In that case it's recommended to use different cache paths for different
incompatible interpreters.  You can override the cache path by passing
``--wheel-cache=/path/to/the/cache`` to the build command.
