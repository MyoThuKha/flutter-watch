"""Isolated installer tests; never modify the user's real installation."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.bin = self.home / '.local/bin'
        self.destination = self.bin / 'flutter-watch'
        self.env = dict(os.environ, HOME=str(self.home))

    def installer(self, *args, root=ROOT):
        return subprocess.run(['sh', str(root / 'install.sh'), *args],
                              cwd=self.home, env=self.env,
                              capture_output=True, text=True)

    def test_default_install_update_uninstall(self):
        result = self.installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.destination.is_file())
        self.assertFalse(self.destination.is_symlink())
        self.assertTrue(os.access(self.destination, os.X_OK))
        self.assertIn('export PATH=', result.stdout)
        before = self.destination.read_bytes()
        result = self.installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.destination.read_bytes(), before)
        result = subprocess.run([str(self.destination), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.installer('--uninstall').returncode, 0)
        self.assertFalse(self.destination.exists())
        self.assertEqual(self.installer('--uninstall').returncode, 0)

    def test_custom_directory_with_spaces(self):
        directory = self.home / 'my commands'
        result = self.installer('--bin-dir', str(directory))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((directory / 'flutter-watch').is_file())
        self.assertIn("'" + str(directory) + "'", result.stdout)
        self.assertFalse(self.destination.exists())

    def test_existing_file_protected_until_explicit_force(self):
        self.bin.mkdir(parents=True)
        self.destination.write_text('unrelated command')
        self.assertNotEqual(self.installer().returncode, 0)
        self.assertEqual(self.destination.read_text(), 'unrelated command')
        self.assertNotEqual(self.installer('--uninstall').returncode, 0)
        self.assertEqual(self.destination.read_text(), 'unrelated command')
        self.assertEqual(self.installer('--force').returncode, 0)
        self.assertNotEqual(self.destination.read_text(), 'unrelated command')

    def test_symlink_is_not_followed(self):
        self.bin.mkdir(parents=True)
        target = self.home / 'unrelated'
        target.write_text('do not change')
        self.destination.symlink_to(target)
        self.assertNotEqual(self.installer().returncode, 0)
        self.assertNotEqual(self.installer('--uninstall').returncode, 0)
        self.assertEqual(self.installer('--force').returncode, 0)
        self.assertEqual(target.read_text(), 'do not change')
        self.assertFalse(self.destination.is_symlink())

    def test_broken_symlink_is_protected(self):
        self.bin.mkdir(parents=True)
        self.destination.symlink_to(self.home / 'missing')
        self.assertNotEqual(self.installer().returncode, 0)
        self.assertTrue(self.destination.is_symlink())
        self.assertEqual(self.installer('--force').returncode, 0)
        self.assertFalse(self.destination.is_symlink())

    def test_installed_command_survives_source_repo_move(self):
        clone = self.home / 'source checkout'
        (clone / 'tool').mkdir(parents=True)
        for name in ('install.sh', 'flutter-watch', 'tool/install.py'):
            shutil.copy2(ROOT / name, clone / name)
        result = self.installer(root=clone)
        self.assertEqual(result.returncode, 0, result.stderr)
        clone.rename(self.home / 'moved checkout')
        result = subprocess.run([str(self.destination), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_source_and_directories_are_protected(self):
        result = self.installer('--bin-dir', str(ROOT), '--force')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('source executable', result.stderr)
        result = self.installer('--bin-dir', str(ROOT), '--uninstall')
        self.assertNotEqual(result.returncode, 0)
        self.destination.mkdir(parents=True)
        self.assertNotEqual(self.installer('--force').returncode, 0)
        self.assertTrue(self.destination.is_dir())


if __name__ == '__main__':
    unittest.main()
