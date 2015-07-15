import os
import sys
import json
import time
import click
import errno
import codecs
import shutil
import select
import tarfile
import zipfile
import hashlib
import tempfile
import sysconfig
import subprocess
from contextlib import contextmanager


WIN = sys.platform.startswith('win')
FORMATS = ['tar.gz', 'tar.bz2', 'tar', 'zip', 'dir']
INSTALLER = '''\
#!/bin/bash
# This script installs the bundled wheel distribution of %(name)s into
# a provided path where it will end up in a new virtualenv.

set -e

show_usage() {
echo "Usage: ./install.sh [OPTIONS] DST"
}

show_help() {
  show_usage
cat << EOF

  Installs %(name)s into a new virtualenv that is provided as the DST
  parameter.  The interpreter to use for this virtualenv can be
  overridden by the "-p" parameter.

Options:
  --help              display this help and exit.
  -p --python PYTHON  use an alternative Python interpreter
EOF
  exit 0
}

param_error() {
  show_usage
  echo
  echo "Error: $1"
  exit 1
}

py="%(python)s"

while [ "$#" -gt 0 ]; do
  case $1 in
    --help)         show_help ;;
    -p|--python)
      if [ "$#" -gt 1 ]; then
        py="$2"
        shift
      else
        param_error "$1 option requires an argument"
      fi
      ;;
    --python=?*)    py=${1#*=} ;;
    --)             shift; break ;;
    -?*)            param_error "no such option: $1" ;;
    *)              break
  esac
  shift
done

if [ "$1" == "" ]; then
  param_error "destination argument is required"
fi

HERE="$(cd "$(dirname "$0")"; pwd)"
DATA_DIR="$HERE/data"

# Ensure Python exists
command -v "$py" &> /dev/null || error "Given python interpreter not found ($py)"

echo 'Setting up virtualenv'
"$py" "$DATA_DIR/virtualenv.py" "$1"
VIRTUAL_ENV="$(cd "$1"; pwd)"

INSTALL_ARGS=''
if [ -f "$DATA_DIR/requirements.txt" ]; then
  INSTALL_ARGS="$INSTALL_ARGS"\ -r\ "$DATA_DIR/requirements.txt"
fi

echo "Installing %(name)s"
"$VIRTUAL_ENV/bin/pip" install --pre --no-index \
  --find-links "$DATA_DIR" wheel $INSTALL_ARGS %(pkg)s | grep -v '^$'

# Potential post installation
cd "$HERE"
. "$VIRTUAL_ENV/bin/activate"
%(postinstall)s

echo "Done."
'''


def utf8open(fn, mode='r'):
    """Shorthand for opening a file in utf-8 mode"""
    return codecs.open(fn, mode, encoding='utf-8')


class Log(object):

    def __init__(self):
        self.indentation = 0

    def indent(self):
        self.indentation += 1

    def outdent(self):
        self.indentation -= 1

    def echo(self, s):
        prefix = '  ' * self.indentation
        click.echo(prefix + s)

    def info(self, fmt, *args, **kwargs):
        self.echo(fmt.format(*args, **kwargs))

    def error(self, fmt, *args, **kwargs):
        return self.info('Error: ' + click.style(fmt, fg='red'),
                         *args, **kwargs)

    def process_stream_output(self, process):
        fds = set([process.stdout, process.stderr])
        while fds:
            for f in select.select(fds, [], [])[0]:
                try:
                    line = f.readline()
                    if not line:
                        fds.discard(f)
                        continue
                except OSError as e:
                    if e.errno != errno.EINTR:
                        raise
                else:
                    line = line.decode('utf-8')
                    color = f == process.stdout and 'cyan' or 'yellow'
                    self.echo(click.style(line.rstrip(), fg=color))

    @contextmanager
    def indented(self):
        self.indent()
        try:
            yield
        finally:
            self.outdent()


def autoquote(arg):
    if arg.strip() not in (arg, '') or arg.split()[0] != arg or '"' in arg:
        arg = '"%s"' % arg.replace('\\', '\\\\').replace('"', '\\"')
    return arg


def find_exe(name):
    """Finds an executable first in the virtualenv if available, otherwise
    falls back to the global name.
    """
    if hasattr(sys, 'real_prefix'):
        path = os.path.join(sys.prefix, 'bin', name)
        if os.path.isfile(path):
            return path
    return name


def make_spec(pkg, version=None):
    if version is None:
        return pkg
    if version[:1] in '>=':
        return pkg + version
    return '%s==%s' % (pkg, version)


def find_closest_package():
    node = os.getcwd()
    while 1:
        if os.path.isfile(os.path.join(node, 'setup.py')):
            return node
        parent = os.path.dirname(node)
        if node == parent:
            break
        node = parent
    raise click.UsageError('Cannot discover package, you need to be explicit.')


def get_cache_dir(app_name):
    if WIN:
        folder = os.environ.get('LOCALAPPDATA')
        if folder is None:
            folder = os.path.expanduser('~')
            app_name = '.' + app_name
        return os.path.join(folder, app_name, 'Cache')
    if sys.platform == 'darwin':
        return os.path.join(os.path.expanduser(
            '~/Library/Caches'), app_name)
    return os.path.join(
        os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.cache')),
        app_name)


def get_default_wheel_cache():
    return get_cache_dir('platter')


class Builder(object):

    def __init__(self, log, path, output, python=None,
                 virtualenv_version=None, wheel_version=None,
                 pip_options=None, no_download=None, wheel_cache=None,
                 requirements=None):
        self.log = log
        self.path = os.path.abspath(path)
        self.output = output
        if python is None:
            python = sys.executable
        self.python = python
        self.virtualenv_version = virtualenv_version
        self.wheel_version = wheel_version
        if wheel_cache is not None:
            wheel_cache = os.path.abspath(wheel_cache)
        self.wheel_cache = wheel_cache
        if requirements is not None:
            requirements = os.path.abspath(requirements)
        self.requirements = requirements
        self.no_download = no_download
        self.pip_options = list(pip_options or ())
        self.scratchpads = []

    def get_pip_options(self):
        rv = self.pip_options
        if self.wheel_cache and os.path.isdir(self.wheel_cache):
            rv = rv + ['-f', self.wheel_cache]
        if self.no_download:
            rv = rv + ['--no-index']
        return rv

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.cleanup()

    def make_scratchpad(self, name='generic'):
        sp = tempfile.mkdtemp(suffix='-' + name)
        self.scratchpads.append(sp)
        self.log.info('Created scratchpad in {}', sp)
        return sp

    def execute(self, cmd, args=None, capture=False):
        cmdline = [cmd]
        cmdline.extend(args or ())
        self.log.info('Executing {}', ' '.join(map(autoquote, cmdline)))
        with self.log.indented():
            cl = subprocess.Popen(cmdline, cwd=self.path,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
            if capture:
                rv = cl.communicate()[0]
            else:
                rv = None
                self.log.process_stream_output(cl)

            if cl.wait() != 0:
                self.log.error('Failed to execute command "%s"' % cmd)
                raise click.Abort()
            if rv is not None:
                return rv.decode('utf-8')

    def cleanup(self):
        while self.scratchpads:
            sp = self.scratchpads.pop()
            try:
                self.log.info('Cleaning up scratchpad in {}', sp)
                shutil.rmtree(sp)
            except (OSError, IOError):
                pass

    def describe_package(self, python):
        # Do dummy invoke first to trigger setup requires.
        self.log.info('Invoking dummy setup to trigger requirements.')
        self.execute(python, ['setup.py', '--version'], capture=True)

        rv = self.execute(python, [
            'setup.py', '--name', '--version', '--fullname'],
            capture=True).strip().splitlines()
        platform = sysconfig.get_platform()
        return {
            'name': rv[0],
            'version': rv[1],
            'platform': platform,
            'ident': rv[2],
        }

    def copy_file(self, filename, target):
        if os.path.isdir(target):
            target = os.path.join(target, os.path.basename(filename))
        shutil.copy2(filename, target)

    def place_venv_deps(self, venv_path, data_dir):
        self.log.info('Placing virtualenv dependencies')
        self.copy_file(os.path.join(venv_path, 'virtualenv.py'),
                       data_dir)

        support_path = os.path.join(venv_path, 'virtualenv_support')

        for filename in os.listdir(support_path):
            if filename.endswith('.whl'):
                self.copy_file(os.path.join(support_path, filename), data_dir)

    def build_wheels(self, venv_path, data_dir):
        self.log.info('Building wheels')
        pip = os.path.join(venv_path, 'bin', 'pip')

        with self.log.indented():
            self.execute(pip, ['install', '--download', data_dir] +
                         self.get_pip_options() +
                         [make_spec('wheel', self.wheel_version)])

            cmdline = ['wheel', '--wheel-dir=' + data_dir]
            cmdline.extend(self.get_pip_options())

            if self.requirements is not None:
                cmdline.extend(('-r', self.requirements))
                shutil.copy2(self.requirements,
                             os.path.join(data_dir, 'requirements.txt'))

            cmdline.append(self.path)

            self.execute(os.path.join(venv_path, 'bin', 'pip'), cmdline)

    def setup_build_venv(self, virtualenv):
        scratchpad = self.make_scratchpad('venv')
        self.log.info('Initializing build virtualenv in {}', scratchpad)
        with self.log.indented():
            self.execute(self.python,
                         [os.path.join(virtualenv, 'virtualenv.py'),
                          scratchpad])
            self.execute(os.path.join(scratchpad, 'bin', 'pip'),
                         ['install'] + self.get_pip_options() +
                         [make_spec('wheel', self.wheel_version)])
        return scratchpad

    def put_installer(self, scratchpad, pkginfo, install_script_path):
        fn = os.path.join(scratchpad, 'install.sh')

        with utf8open(install_script_path) as f:
            postinstall = f.read().rstrip()

        with utf8open(fn, 'w') as f:
            f.write((INSTALLER % dict(
                name=pkginfo['ident'],
                pkg=pkginfo['name'],
                python=os.path.basename(self.python),
                postinstall=postinstall,
            )))
        os.chmod(fn, 0o100755)

    def put_meta_info(self, scratchpad, pkginfo):
        self.log.info('Placing meta information')
        with utf8open(os.path.join(scratchpad, 'info.json'), 'w') as f:
            json.dump(pkginfo, f, indent=2)
            f.write('\n')
        with utf8open(os.path.join(scratchpad, 'VERSION'), 'w') as f:
            f.write(pkginfo['version'] + '\n')
        with utf8open(os.path.join(scratchpad, 'PLATFORM'), 'w') as f:
            f.write(pkginfo['platform'] + '\n')
        with utf8open(os.path.join(scratchpad, 'PACKAGE'), 'w') as f:
            f.write(pkginfo['name'] + '\n')

    def create_archive(self, scratchpad, pkginfo, format):
        base = pkginfo['ident'] + '-' + pkginfo['platform']
        try:
            os.makedirs(self.output)
        except OSError:
            pass

        if format == 'dir':
            rv_fn = os.path.join(self.output, base)
            self.log.info('Saving artifact as directory {}', rv_fn)
            os.rename(scratchpad, rv_fn)
            return rv_fn

        archive_name = base + '.' + format
        rv_fn = os.path.join(self.output, archive_name)
        tmp_fn = os.path.join(self.output, '.' + archive_name)

        self.log.info('Creating distribution archive {}', rv_fn)

        f = None
        try:
            if format in ('tar.gz', 'tar.bz2', 'tar'):
                if '.' in format:
                    mode = 'w:' + format.split('.')[1]
                else:
                    mode = 'w'
                f = tarfile.open(tmp_fn, mode)
                f.add(scratchpad, base)
                f.close()
            elif format == 'zip':
                f = zipfile.ZipFile(tmp_fn, 'w')
                for dirpath, dirnames, files in os.walk(scratchpad):
                    for file in files:
                        f.write(os.path.join(dirpath, file),
                                os.path.join(base, dirpath[
                                    len(scratchpad) + 1:], file),
                                zipfile.ZIP_DEFLATED)
                f.close()
            os.rename(tmp_fn, rv_fn)
        finally:
            if f is not None:
                f.close()
            try:
                os.remove(tmp_fn)
            except OSError:
                pass

        return rv_fn

    def extract_virtualenv(self):
        self.log.info('Downloading and extracting virtualenv bootstrapper')
        with self.log.indented():
            scratchpad = self.make_scratchpad('venv-tmp')
            self.execute(find_exe('pip'), ['install', '--download', scratchpad] +
                         self.get_pip_options() +
                         [make_spec('virtualenv', self.virtualenv_version)])

            artifact = os.path.join(scratchpad, os.listdir(scratchpad)[0])
            if artifact.endswith(('.zip', '.whl')):
                f = zipfile.ZipFile(artifact)
            else:
                f = tarfile.open(artifact)
            f.extractall(scratchpad)
            f.close()

        # We need to detect if we contain a single artifact that is a
        # folder in which case we need to use that.  Wheels for instance
        # do not contain a wrapping folder.
        artifacts = os.listdir(scratchpad)
        if len(artifacts) == 1:
            rv = os.path.join(scratchpad, artifacts[0])
            if os.path.isdir(rv):
                return rv, artifact

        return scratchpad, artifact

    def run_build_script(self, scratchpad, venv_path,
                         build_script, install_script_path):
        self.log.info('Invoking build script {}', build_script)
        with self.log.indented():
            script = '''
            . "%(venv)s/bin/activate"
            export HERE="%(here)s"
            export DATA_DIR="%(here)s/data"
            export SOURCE_DIR="%(path)s"
            export SCRATCHPAD="%(scratchpad)s"
            %(script)s
            ''' % {
                'venv': venv_path,
                'script': os.path.abspath(build_script),
                'path': self.path,
                'here': scratchpad,
                'scratchpad': self.make_scratchpad('postbuild'),
            }
            env = dict(os.environ)
            env['INSTALL_SCRIPT'] = install_script_path
            c = subprocess.Popen(['sh'], env=env, stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,
                                 cwd=scratchpad)
            c.stdin.write(script)
            c.stdin.flush()
            c.stdin.close()
            self.log.process_stream_output(c)
            if c.wait() != 0:
                self.log.error('Build script failed :(')
                raise click.Abort()

    def update_wheel_cache(self, wheelhouse, venv_artifact):
        self.log.info('Updating wheel cache')

        def _place(filename):
            basename = os.path.basename(filename)
            if os.path.isfile(os.path.join(self.wheel_cache, basename)):
                return
            self.log.info('Caching {} for future use', basename)
            shutil.copy2(filename, os.path.join(self.wheel_cache, basename))

        with self.log.indented():
            try:
                os.makedirs(self.wheel_cache)
            except OSError:
                pass

            for filename in os.listdir(wheelhouse):
                if filename[:1] == '.' or not filename.endswith('.whl'):
                    continue
                _place(os.path.join(wheelhouse, filename))
            _place(venv_artifact)

    def finalize(self, artifact, time):
        self.log.info('Done.')
        self.log.info('Total time elapsed: %.2fs' % time)
        self.log.info('Build artifact successfully created.')
        with self.log.indented():
            self.log.info('Artifact: {}', artifact)
            if not os.path.isfile(artifact):
                return

            sha1 = hashlib.sha1()
            md5 = hashlib.md5()
            with open(artifact, 'rb') as f:
                while 1:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    sha1.update(chunk)
                    md5.update(chunk)
            self.log.info('MD5: {}', md5.hexdigest())
            self.log.info('SHA1: {}', sha1.hexdigest())

    def build(self, format, prebuild_script=None, postbuild_script=None):
        if not os.path.isdir(self.path):
            raise click.UsageError('The project path (%s) does not exist'
                                   % self.path)

        now = time.time()
        venv_src, venv_artifact = self.extract_virtualenv()

        venv_path = self.setup_build_venv(venv_src)
        local_python = os.path.join(venv_path, 'bin', 'python')

        self.log.info('Analyzing package')
        pkginfo = self.describe_package(local_python)
        with self.log.indented():
            self.log.info('Name: {}', pkginfo['name'])
            self.log.info('Version: {}', pkginfo['version'])

        scratchpad = self.make_scratchpad('buildbase')
        data_dir = os.path.join(scratchpad, 'data')
        os.makedirs(data_dir)

        install_script_path = os.path.join(venv_path, 'install_script')

        self.place_venv_deps(venv_src, data_dir)
        if prebuild_script is not None:
            self.run_build_script(scratchpad, venv_path, prebuild_script,
                                  install_script_path)

        self.build_wheels(venv_path, data_dir)
        self.put_meta_info(scratchpad, pkginfo)
        utf8open(install_script_path, 'a').close()
        if postbuild_script is not None:
            self.run_build_script(scratchpad, venv_path, postbuild_script,
                                  install_script_path)

        if self.wheel_cache:
            self.update_wheel_cache(data_dir, venv_artifact)

        self.put_installer(scratchpad, pkginfo,
                           install_script_path)
        artifact = self.create_archive(scratchpad, pkginfo, format)

        self.cleanup()
        self.finalize(artifact, time.time() - now)


@click.group(context_settings={
    'auto_envvar_prefix': 'PLATTER'
})
@click.version_option()
def cli():
    """Platter packages up a Python package into a tarball that can install
    into a local virtualenv through a bundled install script.  The only
    requirement on the destination host is a compatible Python installation.

    To build a package with platter use run `platter build`:

        $ platter build

    This will look for the closest Python package.  You can also be explicit
    and provide the path to it:

        $ platter build /path/to/the/project
    """


@cli.command('build')
@click.argument('path', required=False, type=click.Path())
@click.option('--output', type=click.Path(), default='dist',
              help='The output folder', show_default=True)
@click.option('-p', '--python', type=click.Path(),
              help='The python interpreter to use for building.  This '
              'interpreter is both used for compiling the packages and also '
              'used as default in the generated install script.')
@click.option('--virtualenv-version', help='The version of virtualenv to use. '
              'The default is to use the latest stable version from PyPI.',
              metavar='SPEC')
@click.option('--pip-option', multiple=True, help='Adds an option to pip.  To '
              'add multiple options, use this parameter multiple times.  '
              'Example:  --pip-option="--isolated"',
              type=click.Path(), metavar='OPT')
@click.option('--wheel-version', help='The version of the wheel package '
              'that should be used.  Defaults to latest stable from PyPI.',
              metavar='SPEC')
@click.option('--format', default='tar.gz', type=click.Choice(FORMATS),
              help='The format of the resulting build artifact as file '
              'extension.  Supported formats: ' + ', '.join(FORMATS),
              show_default=True, metavar='EXTENSION')
@click.option('--prebuild-script', type=click.Path(),
              help='Path to an optional build script that is invoked in '
              'the build folder as first step.  This can be used to install '
              'build dependencies such as Cython.')
@click.option('--postbuild-script', type=click.Path(),
              help='Path to an optional build script that is invoked in '
              'the build folder as last step.  This can be used to inject '
              'additional data into the archive.')
@click.option('--wheel-cache', type=click.Path(),
              help='An optional folder where platter should cache wheels '
              'instead of the system default.  If you do not want to use '
              'a wheel cache you can pass the --no-wheel-cache flag.')
@click.option('--no-wheel-cache', is_flag=True,
              help='Disables the wheel cache entirely.')
@click.option('--no-download', is_flag=True,
              help='Disables the downloading of all dependencies entirely. '
              'This will only work if all dependencies have been previously '
              'cached.  This is primarily useful when you are temporarily '
              'disconnected from the internet because it will disable useless '
              'network roundtrips.')
@click.option('-r', '--requirements', type=click.Path(),
              help='Optionally the path to a requirements file which contains '
              'additional packages that should be installed in addition to '
              'the main one.  This can be useful when you need to pull in '
              'optional dependencies.')
def build_cmd(path, output, python, virtualenv_version, wheel_version,
              format, pip_option, prebuild_script, postbuild_script,
              wheel_cache, no_wheel_cache, no_download, requirements):
    """Builds a platter package.  The argument is the path to the package.
    If not given it discovers the closest setup.py.

    Generally this works by building the provided package into a wheel file
    and a wheel for each of the dependencies.  The resulting artifacts are
    augmented with a virtualenv bootstrapper and an install script and then
    archived.  Optionally a post build script can be provided that can place
    more files in the archive and also provide more install steps.
    """
    log = Log()
    if path is None:
        path = find_closest_package()
    log.info('Using package from {}', path)

    if no_wheel_cache:
        if no_download:
            raise click.UsageError('--no-download and --no-cache cannot '
                                   'be used together.')
        wheel_cache = None
    elif wheel_cache is None:
        wheel_cache = get_default_wheel_cache()
    if wheel_cache is not None:
        log.info('Using wheel cache in {}', wheel_cache)

    with Builder(log, path, output, python=python,
                 virtualenv_version=virtualenv_version,
                 wheel_version=wheel_version,
                 pip_options=list(pip_option),
                 no_download=no_download,
                 wheel_cache=wheel_cache,
                 requirements=requirements) as builder:
        builder.build(format, prebuild_script=prebuild_script,
                      postbuild_script=postbuild_script)


@cli.command('clean-cache')
def clean_cache_cmd():
    """This command cleans the wheel cache.

    This is useful when the cache got polluted with bad wheels due to a
    bug or if the cache grew too large.  Note that this only cleans the
    wheel cache, it does not clean the download cache of pip.
    """
    log = Log()
    wheel_cache = get_default_wheel_cache()
    log.info('Cleaning cache in {}', wheel_cache)
    with log.indented():
        if os.path.isdir(wheel_cache):
            for fn in os.listdir(wheel_cache):
                if os.path.isfile(os.path.join(wheel_cache, fn)):
                    try:
                        log.info('Removing', fn)
                        os.remove(os.path.join(wheel_cache, fn))
                    except OSError:
                        pass
    log.info('Done')
