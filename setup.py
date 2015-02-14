from setuptools import setup


setup(
    name='platter',
    version='1.0-dev',
    url='http://github.com/mitsuhiko/platter/',
    license='BSD',
    author='Armin Ronacher',
    author_email='armin.ronacher@active-4.com',
    description='A deployment helper for Python.',
    long_description=__doc__,
    py_modules=['platter'],
    platforms='any',
    install_requires=[
        'click>=2.0',
    ],
    entry_points='''
        [console_scripts]
        platter=platter:cli
    '''
)
