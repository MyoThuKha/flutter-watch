"""Install a standalone flutter-watch copy without package-manager dependencies."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import sys
import tempfile


SOURCE = Path(__file__).resolve().parents[1] / 'flutter-watch'
MARKER = b'# Installed by flutter-watch installer; managed executable.\n'


def managed(path):
    if path.is_symlink() or not path.is_file():
        return False
    with path.open('rb') as stream:
        stream.readline()
        return stream.readline() == MARKER


def install(destination, force=False):
    if destination.resolve() == SOURCE.resolve():
        raise ValueError('Destination is the source executable; choose a different --bin-dir.')
    if destination.is_dir() and not destination.is_symlink():
        raise ValueError(f'Destination is a directory: {destination}')
    if os.path.lexists(destination) and not managed(destination) and not force:
        raise ValueError(f'Refusing to replace an unmanaged file or symlink: {destination}. '
                         'Inspect it first; use --force only if you intend to replace it.')
    source = SOURCE.read_bytes()
    shebang, separator, body = source.partition(b'\n')
    if not separator or not shebang.startswith(b'#!'):
        raise ValueError('Source executable is missing a shebang.')
    payload = shebang + separator + MARKER + body
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        # Stage in the same directory, then replace atomically. Never write
        # through a destination symlink into an unrelated file.
        with tempfile.NamedTemporaryFile(dir=destination.parent,
                                         prefix='.flutter-watch-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o755)
        os.replace(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def uninstall(destination):
    if destination.resolve() == SOURCE.resolve():
        raise ValueError('Refusing to remove the repository source executable.')
    if not os.path.lexists(destination):
        print(f'Nothing installed at {destination}')
        return
    if not managed(destination):
        raise ValueError(f'Refusing to remove an unmanaged file or symlink: {destination}')
    destination.unlink()
    print(f'Removed {destination}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', default=str(Path.home() / '.local/bin'),
                        help='installation directory (default: ~/.local/bin)')
    parser.add_argument('--force', action='store_true',
                        help='explicitly replace an existing unmanaged command/symlink')
    parser.add_argument('--uninstall', action='store_true',
                        help='remove only an installer-managed executable')
    args = parser.parse_args(argv)
    if os.name != 'posix' or sys.platform not in ('darwin', 'linux'):
        raise ValueError('The installer currently supports macOS and Linux only.')
    if sys.version_info < (3, 9):
        raise ValueError('Python 3.9+ is required.')
    if args.force and args.uninstall:
        raise ValueError('--force is for installation only; uninstall never removes unmanaged files.')
    directory = Path(args.bin_dir).expanduser().absolute()
    destination = directory / 'flutter-watch'
    if args.uninstall:
        uninstall(destination)
        return 0
    install(destination, args.force)
    print(f'Installed {destination}')
    print('Run flutter-watch inside a Flutter project. Re-run this installer to update.')

    path_dirs = {Path(p).expanduser().resolve() for p in os.environ.get('PATH', '').split(os.pathsep) if p}
    if directory.resolve() not in path_dirs:
        print(f'\nAdd this directory to your shell PATH (no profiles were changed):\n'
              f'  export PATH={shlex.quote(str(directory))}:"$PATH"')
    found = shutil.which('flutter-watch')
    if found and Path(found).resolve() != destination.resolve():
        print(f'Warning: another flutter-watch comes first on PATH: {found}')
    if not shutil.which('flutter'):
        print('Dependency missing: Flutter SDK. Install it and put flutter on PATH.')
    watcher = shutil.which('watchexec')
    if not watcher:
        print('Dependency missing: watchexec. macOS: brew install watchexec; '
              'Linux: use your package manager or official watchexec releases.')
    print('No dependencies were downloaded or installed automatically.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError) as error:
        print(f'flutter-watch installer: {error}', file=sys.stderr)
        sys.exit(1)
