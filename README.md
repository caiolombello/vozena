# Vozena

Native, local voice processing for the classic USB Blue Yeti on Linux calls.

![Vozena desktop app](site/assets/app.webp)

Vozena creates a PipeWire virtual microphone named **Yeti Processado**. It combines an 80 Hz high-pass filter, RNNoise suppression, gentle voice EQ, compression, software gain, and peak limiting. Choose that virtual microphone in your calling app and keep Vozena running while you talk.

Audio processing stays on your computer. Vozena has no network server, account, cloud processing, or telemetry. The optional voice comparison records one 10-second original/processed pair only after you click record, keeps it in RAM, never plays it automatically, and deletes it when you discard it or close the app.

[Português do Brasil](docs/README.pt-BR.md) · [Website](https://caiolombello.github.io/vozena/) · [Releases](https://github.com/caiolombello/vozena/releases)

## Current scope

Vozena v0.4.2 is a public preview. It has been validated on:

- Fedora 44 x86_64
- KDE Plasma with PipeWire 1.6.9
- the classic USB Blue Yeti (`USB b58e:9e84`)

Other Linux distributions, desktop environments, architectures, PipeWire versions, and microphones have not been validated. The pinned Fedora LSP build requires glibc 2.43, so the bootstrap is intentionally limited to Fedora 44 x86_64. Windows and macOS are not supported.

The native interface is currently in Brazilian Portuguese. This guide includes its exact labels where you need to find a control.

Vozena does not provide echo cancellation and cannot promise to remove every background sound. It does not control the microphone's hardware gain or pickup pattern; set those on the Blue Yeti itself. Compatibility with any particular meeting app is not guaranteed.

## Install from a release

The release is a clean source archive. It contains no vendored `.deps`, virtual environment, plugin binary, or Python wheel. Preparation therefore needs a network connection to download pinned files from GitHub, Fedora, and PyPI.

1. Install the Fedora prerequisites:

   ```bash
   sudo dnf install python3 python3-pip pipewire pipewire-utils rpm cpio systemd \
     libsndfile libatomic libstdc++ xcb-util-cursor
   ```

   A normal Fedora 44 KDE installation already supplies the remaining Qt display libraries used by the app.

2. In a browser, download `vozena-0.4.2-source.tar.gz` and `SHA256SUMS` from the [v0.4.2 release](https://github.com/caiolombello/vozena/releases/tag/v0.4.2). Put both files in the same directory, then verify the archive before extracting it:

   ```bash
   sha256sum --check SHA256SUMS
   tar -xzf vozena-0.4.2-source.tar.gz
   cd vozena-0.4.2
   ```

   Continue only if `sha256sum` reports `vozena-0.4.2-source.tar.gz: OK`.

3. Prepare and install for your user:

   ```bash
   python3 scripts/prepare.py
   ```

   The script checks the supported platform, downloads fixed upstream archives over HTTPS, verifies their SHA-256 hashes, extracts only the required plugins and license files, installs hash-pinned PySide6 packages in an isolated persistent environment under `~/.local/share/vozena/runtime/`, and installs the app. It never launches Vozena or captures audio.

4. Start Vozena from the desktop menu or run:

   ```bash
   ~/.local/bin/vozena
   ```

   If you want to type `vozena` without the full path, add `~/.local/bin` to your `PATH`. The former `~/.local/bin/yeti-voz` launcher remains available for compatibility.

To verify an existing preparation without downloading, installing, launching, or capturing audio, run:

```bash
python3 scripts/prepare.py --check
```

## Install from a Git checkout

Install the same Fedora prerequisites, then:

```bash
sudo dnf install git
git clone https://github.com/caiolombello/vozena.git
cd vozena
python3 scripts/prepare.py
~/.local/bin/vozena
```

Preparation options for development and CI are documented by `python3 scripts/prepare.py --help`. `--plugins-only` prepares only the pinned native plugins, `--root` selects another source checkout, and `--venv-dir` selects an absolute persistent runtime directory.

## Use

1. Connect the classic USB Blue Yeti and open Vozena. The app starts paused.
2. Adjust noise reduction (**Redução de ruído**), voice clarity (**Clareza da voz**), and software volume (**Volume da voz**), or choose a preset (**Perfil**).
3. Optionally open calibration (**Calibrar**) and run the guided 10-second capture: stay quiet for 3 seconds, speak normally for 7 seconds, review the suggestion, then click **Aplicar ajustes**. Calibration never applies a suggestion on its own.
4. Click **Ativar tratamento**.
5. Select **Yeti Processado** as the microphone in the calling app.

Vozena reconnects its owned PipeWire graph after the Yeti, PipeWire, or the computer returns. On KDE, `Meta+Shift+M` toggles mute when that shortcut is available. Closing the window keeps processing in the system tray when a tray is available; use the tray menu to quit.

Settings are stored at `~/.config/yeti-voice/settings.json`. The internal Python package and local data paths retain the `yeti_voice` and `yeti-voice` names so existing installations remain compatible.

## Uninstall

Close Vozena, preview the owned paths that would be removed, then uninstall:

```bash
python3 scripts/uninstall.py --dry-run
python3 scripts/uninstall.py
```

The uninstaller checks Vozena's ownership markers and refuses to continue while an app instance is open. It removes the managed app releases, desktop entry, and primary and compatibility launchers. It preserves `~/.config/yeti-voice/settings.json` and the reusable runtime under `~/.local/share/vozena/runtime/`.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for the local test commands and project boundaries. Please report security problems through [GitHub's private vulnerability form](https://github.com/caiolombello/vozena/security/advisories/new), not a public issue.

Vozena is licensed under [GPL-3.0-or-later](LICENSE). Downloaded dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Vozena is an independent open-source project and is not affiliated with or endorsed by Blue or Logitech. Blue Yeti and Logitech are trademarks of their respective owners.
