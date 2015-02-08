import os
import sys
import json
import click
import shutil
import tarfile
import zipfile
import tempfile
import sysconfig
import subprocess


FORMATS = ['tar.gz', 'tar.bz2', 'tar', 'zip', 'dir']
PACKAGE_JSON_URL = 'https://pypi.python.org/pypi/%s/json'
SUPPORTED_ARCHIVES = ('.tar.gz', '.tar', '.zip')
INSTALLER = '''\
#!/bin/sh
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
VIRTUAL_ENV="$1"

# Ensure Python exists
command -v "$py" &> /dev/null || error "Given python interpreter not found ($py)"

echo 'Setting up virtualenv'
"$py" "$DATA_DIR/virtualenv.py" "$VIRTUAL_ENV"
echo "Installing %(name)s"
"$VIRTUAL_ENV/bin/pip" install --pre --no-index \
  --find-links "$DATA_DIR" wheel "%(pkg)s" | grep -v '^$'

# Potential post installation
cd "$HERE"
%(postinstall)s

echo "Done."
'''


def make_spec(pkg, version=None):
    if version is None:
        return pkg
    if version[:1] in '>=':
        return pkg + version
    return '%s==%s' % (pkg, version)


def log(category, message, *args, **kwargs):
    click.echo('%s: %s' % (
        click.style(category.rjust(10), fg='cyan'),
        message.replace('{}', click.style('{}', fg='yellow')).format(
            *args, **kwargs),
    ))


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


class Builder(object):

    def __init__(self, path, output, python=None, virtualenv_version=None,
                 wheel_version=None, pip_options=None):
        self.path = os.path.abspath(path)
        self.output = output
        if python is None:
            python = sys.executable
        self.python = python
        self.virtualenv_version = virtualenv_version
        self.wheel_version = wheel_version
        self.pip_options = list(pip_options or ())
        self.scratchpads = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def make_scratchpad(self, name='generic'):
        sp = tempfile.mkdtemp(suffix='-' + name)
        self.scratchpads.append(sp)
        log('builder', 'Created scratchpad in {}', sp)
        return sp

    def execute(self, cmd, args=None, capture=False):
        cmdline = [cmd]
        cmdline.extend(args or ())
        kwargs = {}
        if capture:
            kwargs['stdout'] = subprocess.PIPE
        cl = subprocess.Popen(cmdline, cwd=self.path, **kwargs)
        rv = cl.communicate()[0]
        if cl.wait() != 0:
            raise click.UsageError('Failed to execute command "%s"' % cmd)
        return rv

    def close(self):
        for sp in reversed(self.scratchpads):
            try:
                log('builder', 'Cleaning up scratchpad in {}', sp)
                shutil.rmtree(sp)
            except (OSError, IOError):
                pass

    def describe_package(self, python):
        # Do dummy invoke first to trigger setup requires.
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

    def install_venv_deps(self, venv_path, data_dir):
        log('builder', 'Installing virtualenv dependencies')
        self.copy_file(os.path.join(venv_path, 'virtualenv.py'),
                       data_dir)

        support_path = os.path.join(venv_path, 'virtualenv_support')

        for filename in os.listdir(support_path):
            if filename.endswith('.whl'):
                self.copy_file(os.path.join(support_path, filename), data_dir)

    def build_wheels(self, venv_path, data_dir):
        log('builder', 'Building wheels')
        pip = os.path.join(venv_path, 'bin', 'pip')

        self.execute(pip, ['install', '--download', data_dir] + self.pip_options
                     + [make_spec('wheel', self.wheel_version)])
        self.execute(os.path.join(venv_path, 'bin', 'pip'),
                     ['wheel', '--wheel-dir=' + data_dir]
                     + self.pip_options + [self.path])

    def setup_build_venv(self, virtualenv):
        scratchpad = self.make_scratchpad('venv')
        log('venv', 'Initializing build virtualenv in {}', scratchpad)
        self.execute(self.python, [os.path.join(virtualenv, 'virtualenv.py'),
                                   scratchpad])
        self.execute(os.path.join(scratchpad, 'bin', 'pip'),
                     ['install'] + self.pip_options +
                     [make_spec('wheel', self.wheel_version)])
        return scratchpad

    def put_installer(self, scratchpad, pkginfo, install_script_path):
        fn = os.path.join(scratchpad, 'install.sh')

        with open(install_script_path) as f:
            postinstall = f.read().rstrip().decode('utf-8')

        with open(fn, 'w') as f:
            f.write((INSTALLER % dict(
                name=pkginfo['ident'],
                pkg=pkginfo['name'],
                python=os.path.basename(self.python),
                postinstall=postinstall,
            )).encode('utf-8'))
        os.chmod(fn, 0100755)

    def put_meta_info(self, scratchpad, pkginfo):
        log('meta', 'Placing meta information')
        with open(os.path.join(scratchpad, 'info.json'), 'w') as f:
            json.dump(pkginfo, f, indent=2)
            f.write('\n')
        with open(os.path.join(scratchpad, 'VERSION'), 'w') as f:
            f.write(pkginfo['version'].encode('utf-8') + '\n')
        with open(os.path.join(scratchpad, 'PLATFORM'), 'w') as f:
            f.write(pkginfo['platform'].encode('utf-8') + '\n')
        with open(os.path.join(scratchpad, 'PACKAGE'), 'w') as f:
            f.write(pkginfo['name'].encode('utf-8') + '\n')

    def create_archive(self, scratchpad, pkginfo, format):
        base = pkginfo['ident'] + '-' + pkginfo['platform']
        try:
            os.makedirs(self.output)
        except OSError:
            pass

        if format == 'dir':
            rv_fn = os.path.join(self.output, base)
            log('archiver', 'Saving artifact as directory {}', rv_fn)
            os.rename(scratchpad, rv_fn)
            return

        archive_name = base + '.' + format
        rv_fn = os.path.join(self.output, archive_name)
        tmp_fn = os.path.join(self.output, '.' + archive_name)

        log('archiver', 'Creating distribution archive {}', rv_fn)

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

    def extract_virtualenv(self):
        scratchpad = self.make_scratchpad('venv-tmp')
        self.execute('pip', ['install', '--download', scratchpad] +
                     self.pip_options +
                     [make_spec('virtualenv', self.virtualenv_version)])

        artifact = os.path.join(scratchpad, os.listdir(scratchpad)[0])
        if artifact.endswith(('.zip', '.whl')):
            f = zipfile.ZipFile(artifact)
        else:
            f = tarfile.open(artifact)
        f.extractall(scratchpad)
        f.close()
        os.remove(artifact)

        # We need to detect if we contain a single artifact that is a
        # folder in which case we need to use that.  Wheels for instance
        # do not contain a wrapping folder.
        artifacts = os.listdir(scratchpad)
        if len(artifacts) == 1:
            rv = os.path.join(scratchpad, artifacts[0])
            if os.path.isdir(rv):
                return rv

        return scratchpad

    def run_postbuild_script(self, scratchpad, venv_path,
                             postbuild_script, install_script_path):
        log('postbuild', 'Invoking build script {}', postbuild_script)

        script = '''
        . "%(venv)s/bin/activate"
        export HERE="%(here)s"
        export DATA_DIR="%(here)s/data"
        %(script)s "%(path)s"
        ''' % {
            'venv': venv_path,
            'script': os.path.abspath(postbuild_script),
            'path': self.path,
            'here': scratchpad,
        }
        c = subprocess.Popen(['sh'], stdin=subprocess.PIPE, cwd=scratchpad,
                             env={'INSTALL_SCRIPT': install_script_path})
        c.communicate(script)
        if c.wait() != 0:
            raise click.UsageError('Build script failed :(')

    def build(self, format, postbuild_script=None):
        if not os.path.isdir(self.path):
            raise click.UsageError('The project path (%s) does not exist'
                                   % self.path)

        venv_src = self.extract_virtualenv()

        venv_path = self.setup_build_venv(venv_src)
        local_python = os.path.join(venv_path, 'bin', 'python')

        log('builder', 'Analyzing package')
        pkginfo = self.describe_package(local_python)
        log('pkg', 'name={} version={}', pkginfo['name'], pkginfo['version'])

        scratchpad = self.make_scratchpad('buildbase')
        data_dir = os.path.join(scratchpad, 'data')
        os.makedirs(data_dir)

        self.install_venv_deps(venv_src, data_dir)
        self.build_wheels(venv_path, data_dir)
        self.put_meta_info(scratchpad, pkginfo)

        install_script_path = os.path.join(venv_path, 'install_script')
        open(install_script_path, 'a').close()
        if postbuild_script is not None:
            self.run_postbuild_script(scratchpad, venv_path, postbuild_script,
                                  install_script_path)

        self.put_installer(scratchpad, pkginfo,
                           install_script_path)
        self.create_archive(scratchpad, pkginfo, format)


@click.group()
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
@click.option('--postbuild-script', type=click.Path(),
              help='Path to an optional build script that is invoked in '
              'the build folder as last step with the path to the source '
              'path as first argument.  This can be used to inject '
              'additional data into the archive.')
def build_cmd(path, output, python, virtualenv_version, wheel_version,
              format, pip_option, postbuild_script):
    """Builds a platter package.  The argument is the path to the package.
    If not given it discovers the closest setup.py.

    Generally this works by building the provided package into a wheel file
    and a wheel for each of the dependencies.  The resulting artifacts are
    augmented with a virtualenv bootstrapper and an install script and then
    archived.  Optionally a post build script can be provided that can place
    more files in the archive and also provide more install steps.
    """
    if path is None:
        path = find_closest_package()
    log('builder', 'Using package from {}', path)

    with Builder(path, output, python=python,
                 virtualenv_version=virtualenv_version,
                 wheel_version=wheel_version,
                 pip_options=list(pip_option)) as builder:
        builder.build(format, postbuild_script=postbuild_script)


@cli.command('cleanup')
@click.option('--output', type=click.Path(), default='dist',
              help='The output folder', show_default=True)
@click.option('-C', '--retain-count', default=0,
              help='The number of builds to keep.  Defaults to 0.')
def cleanup_cmd(output, retain_count):
    """Cleans up old build artifacts in the output folder."""
    log('rm', 'Cleaning up old artifacts in {}', output)
    try:
        files = os.listdir(output)
    except OSError:
        return

    infos = []
    for filename in files:
        if filename[:1] == '.':
            continue
        try:
            infos.append((filename,
                          os.stat(os.path.join(output, filename)).st_mtime))
        except OSError:
            pass

    infos.sort(key=lambda x: (x[1], x[0]))
    if retain_count > 0:
        infos = infos[:-retain_count]

    anything_removed = False
    for filename, mtime in infos:
        log('rm', 'Deleting old artifact {}', filename)
        try:
            os.remove(os.path.join(output, filename))
        except OSError:
            try:
                shutil.rmtree(os.path.join(output, filename))
            except OSError:
                pass
        anything_removed = True

    if not anything_removed:
        log('rm', 'Nothing to remove.')
    else:
        log('rm', 'Done.')
