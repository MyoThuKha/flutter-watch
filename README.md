# flutter-watch

`flutter-watch` launches normal interactive Flutter and automatically hot reloads
when saved Dart **contents** change. Identical saves/atomic rewrites do nothing.
It uses native watchexec notifications (no filesystem polling), an in-memory
SHA-256 baseline, and a 200 ms debounce. There are two persistent helper processes:
the Python wrapper and watchexec; no service or per-save shell processes.

## Install

Requires macOS/Linux, Python 3.9+, Flutter, and a recent watchexec CLI supporting
`--only-emit-events`. From your local checkout:

```sh
brew install watchexec
./install.sh
```

On Linux, install watchexec through your package manager or its official releases.
Install Python/Flutter separately if needed. Nothing is fetched automatically.

The installer copies the executable into `~/.local/bin`, so moving/deleting the
checkout won't break the installed command. No sudo, background service, Python
packages, or shell-profile edits. If the directory isn't on PATH, it prints the
line to add to your shell configuration. A fresh terminal may be needed afterward.

```sh
./install.sh                           # install or update a managed copy
./install.sh --bin-dir "$HOME/bin"      # choose another destination
./install.sh --uninstall               # remove the installed copy only
```

Use the same `--bin-dir` for custom-directory updates/uninstalls. Existing
unmanaged commands and symlinks (including old development symlinks) are protected.
Inspect them first; `./install.sh --force` explicitly replaces one without writing
through its symlink target. Uninstall never removes an unmanaged file or symlink.
Updates replace the managed executable atomically. Keep custom edits in the
checkout, not in the installed copy, which updates replace.

On another device, clone/copy this repository, install the prerequisites, and run
`./install.sh`. No Git remote or hosted download endpoint is assumed.

## Run

From a Flutter project:

```sh
flutter-watch
flutter-watch -d macos
flutter-watch --list
flutter-watch --config Development
flutter-watch --dry-run
```

Run the command inside the target Flutter project or a subdirectory. It discovers
the nearest `pubspec.yaml` from your current directory, never from the tool's
installation location. The pubspec must declare the Flutter SDK in `dependencies`
using conventional block YAML or `flutter: {sdk: flutter}` syntax. Plain Dart
packages and non-project folders are rejected with:

```text
Not a Flutter repository. Run flutter-watch inside a Flutter repository.
```

"Repository" means Flutter project; the app does not need to use Git.
The command reads `.vscode/launch.json` as
JSONC (comments/trailing commas supported), selects the sole Dart launch config
automatically, or presents a picker. Use `--config NAME` in noninteractive shells.
Without configurations, it falls back to normal `flutter run` defaults.

Supported config fields: `program`, `cwd`, `env` (including null to unset),
`deviceId`, `flutterMode` (debug only), `toolArgs`, and `args`. Application `args`
map to `--dart-entrypoint-args` (Flutter currently supports these on desktop only).
`${workspaceFolder}`, `${workspaceFolderBasename}`, and `${env:NAME}` are resolved.
Presentation/console settings are ignored: this always uses the current terminal.
Other fields, including `preLaunchTask`, `envFile`, `dartCode`, and custom SDK
paths, fail clearly rather than being silently skipped. VS Code tasks are never
executed. Attach/compound configurations are not supported.

Extra CLI arguments are appended after configuration arguments (Flutter decides
duplicate-option semantics; repeatable options accumulate). Use `--` to forward
conflicting wrapper flags, e.g. `flutter-watch -- --help`.

```sh
flutter-watch --watch lib --watch packages/shared/lib --debounce 250
```

Watch directories are relative to the selected config's `cwd`; default is `lib`.
Every watch path and configuration `cwd` must stay inside the discovered project
root. Absolute paths/`..` that escape it are rejected. Symlink watch roots and
symlink path components are rejected; nested symlinks are not traversed, and
external event paths are ignored. Other apps and the tool's source directory
cannot trigger this session's reload. The scope stays fixed for that run.
New/deleted files and moved directories are tracked. Only `.dart` content counts;
assets, pubspec changes, and native code are not automatically reloaded. Symlinks
are not followed. Default watchexec editor-temp ignores remain enabled; project
ignore files are not consulted, so generated Dart sources can trigger reloads.

Flutter keeps its normal output and `r`, `R`, `q` controls. Reload signals are sent
only after Flutter creates its private session PID file, and only to our live
child process. Startup edits are retained until then. Exiting Flutter, Ctrl+C,
or terminating the wrapper cleans up both helpers and the session file. Signals
don't acknowledge reload completion: rapid later saves can request another reload
while Flutter is busy. Use manual `r` to retry a rejected reload; hot restart `R`
is still required for changes that hot reload cannot apply.

Tests (no Flutter device or watchexec installation needed):

```sh
python3 -m unittest discover -s tool -p 'test_*.py'
```
