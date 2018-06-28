import io
from setuptools import setup

with io.open('README', 'rt', encoding='utf8') as f:
    readme = f.read()

setup(
    name='platter',
    version='1.1',
    url='https://github.com/mitsuhiko/platter/',
    license='BSD',
    author='Armin Ronacher',
    author_email='armin.ronacher@active-4.com',
    description='A deployment helper for Python.',
    long_description=readme,
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
