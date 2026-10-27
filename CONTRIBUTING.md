# Contributing to Vozena

Thanks for helping improve Vozena. The current project boundary is deliberately narrow: Fedora 44 x86_64, KDE Plasma, PipeWire 1.6.9, and the classic USB Blue Yeti. Reports from other systems are welcome as test evidence, but a successful report does not make that system supported by itself.

## Local setup

Install the Fedora prerequisites listed in [README.md](README.md), clone the repository, and prepare the native plugins:

```bash
sudo dnf install git
python3 scripts/prepare.py --plugins-only
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --require-hashes --only-binary=:all: -r requirements.lock
```

On a minimal headless Fedora 44 worker, Qt may additionally need `mesa-libGL`, `fontconfig`, `libxkbcommon`, `libxkbcommon-x11`, and `dbus-libs`. A normal Fedora 44 KDE desktop already provides these runtime libraries.

The repository's source archive and commits must not include `.deps/`, `.venv/`, downloaded wheels, extracted plugin binaries, personal logs, recordings, screenshots containing personal information, or files under `artifacts/`. `scripts/prepare.py` recreates native dependencies from the pinned upstream archives and verifies their hashes.

## Test

Run the default suite headlessly:

```bash
QT_QPA_PLATFORM=offscreen python3 -m unittest discover -s tests -v
```

This suite uses test doubles and synthetic data where possible. A passing default suite does not establish that real PipeWire, KDE, hardware, or a meeting app works on the test machine.

The PipeWire and KDE integration checks are opt-in because they inspect or change local desktop state. The PipeWire checks also use `pactl`, provided on Fedora by `pulseaudio-utils`:

```bash
sudo dnf install pulseaudio-utils
```

Before running them, pause any installed Vozena instance, disconnect from calls, connect the classic USB Blue Yeti where required, and review the tests you are enabling.

```bash
YETI_RUN_PIPEWIRE_TESTS=1 QT_QPA_PLATFORM=offscreen \
  python3 -m unittest tests.test_pipewire_integration -v

YETI_RUN_DESKTOP_TESTS=1 QT_QPA_PLATFORM=offscreen \
  python3 -m unittest tests.test_shortcuts -v
```

Physical-device integration uses PipeWire metadata and a passive capture graph with its level meter disabled. Synthetic audio is routed only through a test-owned null sink. Do not publish local audio artifacts or logs that contain usernames, paths, device metadata, meeting details, or other personal information.

To check the prepared plugins and this local Python runtime without installing or starting the app:

```bash
python3 scripts/prepare.py --check --venv-dir "$PWD/.venv"
```

To verify the clean source archive:

```bash
python3 scripts/build_release.py --output-dir dist
tar -tzf dist/vozena-0.5.1-source.tar.gz
```

Confirm that the archive contains source and public documentation and excludes `.deps`, `.venv`, `artifacts`, wheels, and native plugin binaries.

## Changes

- Keep audio processing local. Do not add telemetry, accounts, cloud processing, background recording, or network access to the running app.
- Preserve the explicit capture model: the app starts paused; voice comparison and calibration begin only after a user action; playback and applying calibration are separate explicit actions.
- Preserve the existing `yeti_voice` package, `~/.config/yeti-voice`, and `~/.local/share/yeti-voice` compatibility paths. Keep **Yeti Processado** as the virtual source name unless a migration is designed and tested.
- Do not claim support for hardware or platforms without reproducible validation. Include the OS, architecture, desktop, PipeWire version, microphone identity, exact steps, and observed result in compatibility reports.
- Keep dependency versions, archive URLs, hashes, extracted paths, and upstream license files coordinated across `requirements.lock`, `scripts/plugins.lock.json`, and the preparation tests.
- Add focused tests for behavior changes. Hardware and desktop tests must remain opt-in and must preserve the user's default microphone and unrelated PipeWire nodes.

Open a pull request with the problem, the resulting behavior, and the commands you ran. Use public issues for ordinary bugs and feature proposals. Follow [SECURITY.md](SECURITY.md) for vulnerabilities.
