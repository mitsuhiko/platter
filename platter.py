import os
import sys
import json
import click
import shutil
import urllib
import socket
import hashlib
import tarfile
import zipfile
import tempfile
import sysconfig
import posixpath
import subprocess


FORMATS = ['tar.gz', 'tar.bz2', 'tar', 'zip', 'dir']
PACKAGE_JSON_URL = 'https://pypi.python.org/pypi/%s/json'
SUPPORTED_ARCHIVES = ('.tar.gz', '.tar', '.zip')
INSTALLER = '''\
#!/bin/sh
# This script installs the bundled wheel distribution of {name} into
# a provided path where it will end up in a new virtualenv.

if [ "$1" == "" ]; then
  echo "usage: ./install.sh [dst]"
  exit 1
fi

here="$(cd "$(dirname "$0")"; pwd)"
data_dir="$here/data"
venv="$1"

# Bootstrap virtualenv
"{python}" "$data_dir/virtualenv.py" "$venv"
"$venv/bin/pip" install --no-index --find-links "$data_dir" --upgrade wheel

# Install distribution
"$venv/bin/pip" install --pre --no-index --find-links "$data_dir" "{package}"

# All done
echo "Done."
'''


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


def get_config_folder():
    return os.path.expanduser('~/.platter')


def ensure_package(name, version=None, as_wheel=False):
    def _get_target_filename(version):
        return os.path.join(get_config_folder(), '%s-cache' % name, version)

    def _complete_path(path):
        if not as_wheel:
            return path
        return os.path.join(path, next(x for x in os.listdir(path)
                                       if x[:1] != '.'))

    # If we already have this version of virtualenv and a specific version
    # is requested, we can just use this.
    if version is not None:
        path = _get_target_filename(version)
        if os.path.isdir(path):
            return _complete_path(path)
        log('dl', 'Downloading requested version of {} ({})', name,
            version)
    else:
        log('dl', 'Discovering latest version of {}', name)

    if as_wheel:
        pkg_type = 'bdist_wheel'
        unpack = False
        supported_archives = ('.whl',)
    else:
        pkg_type = 'sdist'
        unpack = True
        supported_archives = ('.tar.gz', '.tar', '.zip')

    try:
        meta = json.load(urllib.urlopen(PACKAGE_JSON_URL % name))
    except (IOError, socket.error):
        raise click.UsageError('Failed to download information about '
                               '%s from PyPI.' % name)

    try:
        if version is None:
            version = meta['info']['version']
            path = _get_target_filename(version)
            if os.path.isdir(path):
                return _complete_path(path)
        latest_url, md5 = next((x['url'], x['md5_digest'])
                               for x in meta['releases'].get(version, ())
                               if x['packagetype'] == pkg_type and
                               x['url'].endswith(supported_archives))
    except StopIteration:
        raise click.UsageError('The requested version of %s could '
                               'not be found (%s)' %
                               (name, version or 'latest'))

    log('dl', 'Downloading {}', name + '-' + version)
    h = hashlib.md5()
    with tempfile.NamedTemporaryFile() as of:
        filename = posixpath.basename(latest_url)
        f = urllib.urlopen(latest_url)
        while 1:
            chunk = f.read(16384)
            if not chunk:
                break
            h.update(chunk)
            of.write(chunk)
        f.close()
        of.flush()

        if h.hexdigest() != md5.lower():
            raise click.UsageError('Failed to download a valid %s '
                                   'package.' % name)

        if not unpack:
            try:
                os.makedirs(path)
            except OSError:
                pass
            shutil.copy(of.name, os.path.join(path, filename))
        else:
            log('dl', 'Extracting package', version)
            if latest_url.endswith('.zip'):
                f = zipfile.ZipFile(of.name)
            else:
                f = tarfile.open(of.name)

            tmp_folder = path + '___'
            try:
                try:
                    os.makedirs(tmp_folder)
                except OSError:
                    pass
                f.extractall(tmp_folder)
                os.rename(os.path.join(tmp_folder, os.listdir(tmp_folder)[0]),
                          path)
            finally:
                shutil.rmtree(tmp_folder)

        return _complete_path(path)


class Builder(object):

    def __init__(self, path, output, python=None, virtualenv_version=None,
                 wheel_version=None):
        self.path = path
        self.output = output
        if python is None:
            python = sys.executable
        self.python = python
        self.virtualenv_version = virtualenv_version
        self.wheel_version = wheel_version
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
        return cl.communicate()[0]

    def close(self):
        for sp in reversed(self.scratchpads):
            try:
                log('builder', 'Cleaning up scratchpad in {}', sp)
                shutil.rmtree(sp)
            except (OSError, IOError):
                pass

    def describe_package(self, python):
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

    def install_venv_deps(self, venv_path, wheel_path, data_dir):
        log('builder', 'Installing virtualenv dependencies')
        self.copy_file(os.path.join(venv_path, 'virtualenv.py'),
                       data_dir)
        self.copy_file(os.path.join(wheel_path), data_dir)

        support_path = os.path.join(venv_path, 'virtualenv_support')

        for filename in os.listdir(support_path):
            if filename.endswith('.whl'):
                self.copy_file(os.path.join(support_path, filename), data_dir)

    def build_wheels(self, venv_path, data_dir):
        log('builder', 'Building wheels')
        self.execute(os.path.join(venv_path, 'bin', 'pip'),
                     ['wheel', self.path, '--wheel-dir=' + data_dir])

    def setup_build_venv(self, virtualenv):
        scratchpad = self.make_scratchpad('venv')
        log('venv', 'Initializing build virtualenv in {}', scratchpad)
        self.execute(self.python, [os.path.join(virtualenv, 'virtualenv.py'),
                                   scratchpad])
        # XXX: install from local
        self.execute(os.path.join(scratchpad, 'bin', 'pip'),
                     ['install', 'wheel'])
        return scratchpad

    def put_installer(self, scratchpad, pkginfo):
        fn = os.path.join(scratchpad, 'install.sh')
        with open(fn, 'w') as f:
            f.write(INSTALLER.format(
                name=pkginfo['ident'],
                package=pkginfo['name'],
                python=os.path.basename(self.python),
            ).encode('utf-8'))
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

    def build(self, format):
        venv_src = ensure_package('virtualenv', self.virtualenv_version)
        wheel_src = ensure_package('wheel', self.wheel_version, as_wheel=True)

        venv_path = self.setup_build_venv(venv_src)
        local_python = os.path.join(venv_path, 'bin', 'python')

        log('builder', 'Analyzing package')
        pkginfo = self.describe_package(local_python)
        log('pkg', 'name={} version={}', pkginfo['name'], pkginfo['version'])

        scratchpad = self.make_scratchpad('buildbase')
        data_dir = os.path.join(scratchpad, 'data')
        os.makedirs(data_dir)

        self.install_venv_deps(venv_src, wheel_src, data_dir)
        self.build_wheels(venv_path, data_dir)
        self.put_installer(scratchpad, pkginfo)
        self.put_meta_info(scratchpad, pkginfo)

        self.create_archive(scratchpad, pkginfo, format)


@click.group()
def cli():
    """Platter packages up a Python package into a tarball that can install
    into a local virtualenv through a bundled install script.  The only
    requirement on the destination host is a compatible Python installation.
    """


@cli.command('build')
@click.argument('path', required=False)
@click.option('--output', type=click.Path(), default='dist',
              help='The output folder', show_default=True)
@click.option('-p', '--python', help='The python interpreter to use for '
              'building')
@click.option('--virtualenv-version', help='The version of virtualenv to use. '
              'The default is to use the latest stable version from PyPI.')
@click.option('--wheel-version', help='The version of the wheel package '
              'that should be used.  Defaults to latest stable from PyPI.')
@click.option('--format', default='tar.gz', type=click.Choice(FORMATS),
              help='The format of the resulting build artifact',
              show_default=True)
def build_cmd(path, output, python, virtualenv_version, wheel_version,
              format):
    """Builds a platter package.  The argument is the path to the package.
    If not given it discovers the closest setup.py.
    """
    if path is None:
        path = find_closest_package()
    log('builder', 'Using package from {}', path)

    with Builder(path, output, python=python,
                 virtualenv_version=virtualenv_version,
                 wheel_version=wheel_version) as builder:
        builder.build(format)


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
