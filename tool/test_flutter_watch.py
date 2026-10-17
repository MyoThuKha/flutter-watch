"""Run with: python3 -m unittest discover -s tool -p 'test_*.py'."""

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / 'flutter-watch'
loader = importlib.machinery.SourceFileLoader('flutter_watch', str(SCRIPT))
spec = importlib.util.spec_from_loader(loader.name, loader)
watch = importlib.util.module_from_spec(spec)
loader.exec_module(watch)


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'pubspec.yaml').write_text('name: example\ndependencies:\n  flutter:\n    sdk: flutter\n')
        self.lib = self.root / 'lib'
        self.lib.mkdir()
        self.source = self.lib / 'main.dart'
        self.source.write_text('original')

    def test_jsonc_preserves_strings(self):
        data = watch.jsonc('''{
          // comment
          "url": "https://example.com/*not a comment*/",
          "escaped": "a\\\"//b", /* comment */
          "items": ["comma,}",],
        }''')
        self.assertEqual(data['items'], ['comma,}'])
        self.assertEqual(data['escaped'], 'a"//b')
        self.assertTrue(data['url'].startswith('https://'))

    def test_workspace_is_flutter_not_plain_dart(self):
        self.assertEqual(watch.workspace(self.lib), self.root)
        (self.root / 'pubspec.yaml').write_text('name: plain_dart\n')
        with self.assertRaisesRegex(watch.WatchError, 'Not a Flutter repository'):
            watch.workspace(self.lib)
        (self.root / 'pubspec.yaml').write_text('name: commented\n# dependencies:\n#   flutter:\n#     sdk: flutter\n')
        self.assertFalse(watch.is_flutter_project(self.root))
        (self.root / 'pubspec.yaml').write_text('dependencies:\n  flutter: {sdk: flutter}\n')
        self.assertEqual(watch.workspace(self.root), self.root)

    def test_nearest_plain_dart_package_blocks_parent_discovery(self):
        (self.lib / 'pubspec.yaml').write_text('name: dart_package\n')
        with self.assertRaises(watch.WatchError):
            watch.workspace(self.lib)

    def test_watch_paths_cannot_escape_repository(self):
        self.assertEqual(watch.watch_roots(self.root, ['lib'], self.root), [self.lib])
        for value in ('..', str(self.root.parent), '../sibling/lib'):
            with self.assertRaisesRegex(watch.WatchError, 'inside the current Flutter repository'):
                watch.watch_roots(self.root, [value], self.root)
        link = self.root / 'alias'
        link.symlink_to(self.lib, target_is_directory=True)
        with self.assertRaises(watch.WatchError):
            watch.watch_roots(self.root, ['alias'], self.root)

    def test_external_symlink_directory_events_do_not_reload(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external).resolve()
            (outside / 'external.dart').write_text('outside')
            alias = self.lib / 'linked'
            alias.symlink_to(outside, target_is_directory=True)
            cache = watch.Contents([self.lib])
            self.assertNotIn(alias / 'external.dart', cache.hashes)
            self.assertFalse(cache.update([outside / 'external.dart', alias,
                                           alias / 'external.dart']))
            self.assertFalse(cache.update([self.lib]))

    def test_external_cwd_rejected(self):
        with tempfile.TemporaryDirectory() as external:
            with self.assertRaisesRegex(watch.WatchError, 'cwd must stay inside'):
                watch.launch_options({'cwd': external}, self.root, [])

    def test_command_runs_from_another_flutter_project(self):
        result = subprocess.run([sys.executable, str(SCRIPT), '--dry-run'],
                                cwd=self.lib, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['cwd'], str(self.root))
        self.assertEqual(data['watch'], [str(self.lib)])

    def test_non_flutter_command_has_clear_message(self):
        (self.root / 'pubspec.yaml').unlink()
        result = subprocess.run([sys.executable, str(SCRIPT), '--dry-run'],
                                cwd=self.root, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Not a Flutter repository', result.stderr)

    def test_content_changes_and_identical_atomic_save(self):
        cache = watch.Contents([self.lib])
        self.assertFalse(cache.update([self.source]))
        self.source.touch()
        self.assertFalse(cache.update([self.source]))
        replacement = self.lib / 'save.tmp'
        replacement.write_text('original')
        replacement.replace(self.source)
        self.assertFalse(cache.update([self.source]))
        self.source.write_text('edited')
        self.assertTrue(cache.update([self.source]))
        self.assertFalse(cache.update([self.source]))
        self.source.write_text('original')
        self.assertTrue(cache.update([self.source]))

    def test_new_deleted_and_renamed_directories(self):
        cache = watch.Contents([self.lib])
        folder = self.lib / 'new'
        folder.mkdir()
        (folder / 'new.dart').write_text('new')
        self.assertTrue(cache.update([folder]))
        moved = self.lib / 'moved'
        folder.rename(moved)
        self.assertTrue(cache.update([folder, moved]))
        self.assertFalse(cache.update([folder, moved]))
        (moved / 'new.dart').unlink()
        moved.rmdir()
        self.assertTrue(cache.update([moved]))

    def test_only_dart_inside_roots(self):
        cache = watch.Contents([self.lib])
        other = self.root / 'outside.dart'
        other.write_text('outside')
        text = self.lib / 'notes.txt'
        text.write_text('notes')
        link = self.lib / 'link.dart'
        link.symlink_to(other)
        self.assertFalse(cache.update([other, text, link]))

    def test_launch_configuration(self):
        config = {'program': '${workspaceFolder}/lib/main.dart',
                  'cwd': '${workspaceFolder}', 'deviceId': 'macos',
                  'env': {'FLAVOR': 'dev'},
                  'toolArgs': ['--flavor', 'dev'], 'args': ['hello world']}
        cwd, env, args = watch.launch_options(config, self.root, ['--dart-define=X=1'])
        self.assertEqual(cwd, self.root)
        self.assertEqual(env['FLAVOR'], 'dev')
        self.assertIn('--dart-entrypoint-args=hello world', args)
        self.assertEqual(args[-1], '--dart-define=X=1')

    def test_unsupported_config_and_unsafe_flags_fail(self):
        for config in ({'preLaunchTask': 'build'}, {'envFile': '.env'},
                       {'flutterMode': 'release'}, {'toolArgs': 'not a list'},
                       {'program': '${command:unsafe}'}):
            with self.assertRaises(watch.WatchError):
                watch.launch_options(config, self.root, [])
        for arg in ('--pid-file=/tmp/other', '--release', '--machine', '--no-hot'):
            with self.assertRaises(watch.WatchError):
                watch.launch_options({}, self.root, [arg])

    def test_selection_and_events(self):
        configs = [{'name': 'Dev'}, {'name': 'Prod'}]
        self.assertEqual(watch.select_config(configs, 'Dev'), configs[0])
        with self.assertRaises(watch.WatchError):
            watch.select_config(configs, 'missing')
        event = {'tags': [{'kind': 'path', 'absolute': str(self.source)}]}
        self.assertEqual(watch.event_paths(json.dumps(event)), {self.source})
        self.assertEqual(watch.event_paths(json.dumps([event])), {self.source})

    def test_lifecycle_with_fake_flutter_and_watcher(self):
        # Real subprocesses/signals, no device or installed watchexec required.
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        flutter = bin_dir / 'flutter'
        flutter.write_text(f'''#!{sys.executable}
import os, pathlib, signal, sys, time
root = pathlib.Path.cwd()
def reload(*_):
    with (root / 'reloads').open('a') as f: f.write('reload\\n')
signal.signal(signal.SIGUSR1, reload)
pid = pathlib.Path(sys.argv[sys.argv.index('--pid-file') + 1])
time.sleep(0.3)
pid.write_text(str(os.getpid()))
(root / 'ready').touch()
while not (root / 'quit').exists(): time.sleep(0.02)
pid.unlink()
''')
        watcher = bin_dir / 'watchexec'
        watcher.write_text(f'''#!{sys.executable}
import json, pathlib, sys, time
root = pathlib.Path.cwd()
(root / 'watcher-pid').write_text(str(__import__('os').getpid()))
with (root / 'events').open('w+') as f:
    while True:
        line = f.readline()
        if line: print(line, end='', flush=True)
        else: time.sleep(0.01)
''')
        flutter.chmod(0o755)
        watcher.chmod(0o755)
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
        process = subprocess.Popen([sys.executable, str(SCRIPT), '--debounce', '40'],
                                   cwd=self.root, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True)
        self.addCleanup(watch.stop, process)

        def until(predicate):
            deadline = time.monotonic() + 5
            while not predicate():
                if time.monotonic() > deadline:
                    self.fail('Timed out waiting for subprocess')
                time.sleep(0.02)

        until(lambda: (self.root / 'events').exists())

        def emit(content):
            self.source.write_text(content)
            with (self.root / 'events').open('a') as stream:
                stream.write(json.dumps({'tags': [{'kind': 'path',
                              'absolute': str(self.source)}]}) + '\n')

        # A first save during startup must be retained until signal readiness.
        emit('first change')
        reloads = self.root / 'reloads'
        until(lambda: reloads.exists() and len(reloads.read_text().splitlines()) == 1)
        emit('first change')
        time.sleep(0.2)
        self.assertEqual(len(reloads.read_text().splitlines()), 1)
        emit('second change')
        until(lambda: len(reloads.read_text().splitlines()) == 2)
        watcher_pid = int((self.root / 'watcher-pid').read_text())
        (self.root / 'quit').touch()
        stdout, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        with self.assertRaises(ProcessLookupError):
            os.kill(watcher_pid, 0)


if __name__ == '__main__':
    unittest.main()
