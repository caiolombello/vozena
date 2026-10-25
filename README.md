<div align="center">

# Vozena

**Real-time voice processing for Linux.**  
Built for clean speech, reliable virtual audio devices, and clear local control.

[![CI](https://github.com/caiolombello/vozena/actions/workflows/ci.yml/badge.svg)](https://github.com/caiolombello/vozena/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)

</div>

---

Vozena v0.5.0 is a public preview. It has been validated on:

- Fedora 44 x86_64 with KDE Plasma, PipeWire 1.6, and the classic USB Blue Yeti (`USB b58e:9e84`)
- Ubuntu and Kubuntu 26.04/26.10 x86_64: automated tests and PipeWire checks with a virtual microphone

Other Linux distributions, desktop environments, architectures, and microphones have not been validated. Windows and macOS are not supported. The global shortcut and its on-screen indicator are KDE-only.

The native interface is currently in Brazilian Portuguese. This guide includes its exact labels where you need to find a control.

Vozena does not provide echo cancellation and cannot promise to remove every background sound. It does not control the microphone's hardware gain or pickup pattern; set those on the Blue Yeti itself. Compatibility with any particular meeting app is not guaranteed.

## Install from a release

The release is a clean source archive. It contains no vendored `.deps`, virtual environment, plugin binary, or Python wheel. Preparation therefore needs a network connection to download pinned files from GitHub and PyPI.

1. Install the system prerequisites:

   **On Fedora 44:**

   ```bash
   sudo dnf install python3 python3-pip pipewire pipewire-utils systemd \
     libsndfile libatomic libstdc++ xcb-util-cursor lsp-plugins-ladspa
   ```

   **On Ubuntu or Kubuntu 26.04/26.10:**

   ```bash
   sudo apt install python3 python3-pip python3-venv pipewire pipewire-bin systemd \
     libsndfile1 libatomic1 libstdc++6 libxcb-cursor0 lsp-plugins-ladspa
   ```

   `lsp-plugins-ladspa` provides the compressor and limiter. Vozena uses your distribution's copy only after checking that it is owned by the system and exposes every control Vozena sets, so it keeps receiving your distribution's updates. Without that package, preparation downloads a pinned Fedora 44 build instead; it needs glibc 2.43 plus `rpm` and `cpio` on Fedora, or `rpm2cpio` and `cpio` on Ubuntu.

2. In a browser, download `vozena-0.5.0-source.tar.gz` and `SHA256SUMS` from the [v0.5.0 release](https://github.com/caiolombello/vozena/releases/tag/v0.5.0). Put both files in the same directory, then verify the archive before extracting it:

   ```bash
   sha256sum --check SHA256SUMS
   tar -xzf vozena-0.5.0-source.tar.gz
   cd vozena-0.5.0
   ```

   Continue only if `sha256sum` reports `vozena-0.5.0-source.tar.gz: OK`.

3. Prepare and install for your user:

   ```bash
   python3 scripts/prepare.py
   ```

   The script checks the supported platform, selects the LSP plugin (`--lsp system` or `--lsp pinned` forces one source), downloads fixed upstream archives over HTTPS, verifies their SHA-256 hashes, extracts only the required plugins and license files, installs hash-pinned PySide6 packages in an isolated persistent environment under `~/.local/share/vozena/runtime/`, and installs the app. It never launches Vozena or captures audio.

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

Install the system prerequisites above and `git`, then:

```bash
git clone https://github.com/caiolombello/vozena.git
cd vozena
python3 scripts/prepare.py
~/.local/bin/vozena
```

Preparation options for development and CI are documented by `python3 scripts/prepare.py --help`. `--plugins-only` prepares only the native plugins, `--root` selects another source checkout, and `--venv-dir` selects an absolute persistent runtime directory.

## Use

1. Connect the classic USB Blue Yeti and open Vozena. The app starts paused.
2. Adjust noise reduction (**Redução de ruído**), voice clarity (**Clareza da voz**), and software volume (**Volume da voz**), or choose a voice profile (**Perfil de voz**). **Salvar** stores the current controls as your own profile, for example "Ventilador ligado"; **Excluir** removes it.
3. Optionally open calibration (**Calibrar**) and run the guided 10-second capture: stay quiet for 3 seconds, speak normally for 7 seconds, review the suggestion, then click **Aplicar ajustes**. Calibration never applies a suggestion on its own.
4. Click **Ativar tratamento**.
5. Select **Yeti Processado** as the microphone in the calling app. The **Na sua reunião** card names the apps that are using it. **Usar como microfone padrão** makes it the system default input, so apps that follow the default pick it up automatically; **Restaurar microfone anterior** undoes that.
6. With headphones on, **Ouvir ao vivo** plays the processed voice back in real time while you adjust the controls.
7. **Comparar áudio** records one 10-second sample and plays the original and processed versions on request. If the sample is silent, check the Yeti's mute button (red light).

The **Preferências** tab can start the installed app in the tray at login, activate the treatment on launch (waiting for the Yeti if it is unplugged), and warn you when you speak while Yeti Processado is muted.

Vozena reconnects its owned PipeWire graph after the Yeti, PipeWire, or the computer returns. On KDE, `Meta+Shift+M` toggles mute and Plasma shows its microphone indicator. Closing the window keeps processing in the system tray when a tray is available; use the tray menu to quit.

### When the microphone is captured

An active treatment does not keep the Yeti capturing. The Yeti runs only while an app uses Yeti Processado, while the Vozena window is open (for the level meter), during live listening, or while recording a comparison or calibration sample. The muted-speech warning reads the Yeti only while a meeting app already has it open, through a passive PipeWire stream that cannot open the microphone by itself; nothing is recorded.

Voice settings are stored at `~/.config/yeti-voice/settings.json`; preferences and your profiles at `~/.config/yeti-voice/preferences.json`. The internal Python package and local data paths retain the `yeti_voice` and `yeti-voice` names so existing installations remain compatible.

## How it works

Vozena runs its own PipeWire filter chain between the Yeti and a virtual microphone named **Yeti Processado**: an 80 Hz high-pass filter, RNNoise suppression (blended with the dry signal), gentle voice EQ, an LSP compressor, software gain, and an LSP peak limiter. All plugins run locally inside PipeWire; no audio is sent over the network.

## Uninstall

Close Vozena, preview the owned paths that would be removed, then uninstall:

```bash
python3 scripts/uninstall.py --dry-run
python3 scripts/uninstall.py
```

The uninstaller checks Vozena's ownership markers and refuses to continue while an app instance is open. It removes the managed app releases, desktop entry, login entry, and primary and compatibility launchers. It preserves your settings and preferences under `~/.config/yeti-voice/` and the reusable runtime under `~/.local/share/vozena/runtime/`.

## Contributing and security

See [CONTRIBUTING.md](CONTRIBUTING.md) for the local test commands and project boundaries. Please report security problems through [GitHub's private vulnerability form](https://github.com/caiolombello/vozena/security/advisories/new), not a public issue.

Vozena is licensed under [GPL-3.0-or-later](LICENSE). Downloaded dependencies retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Vozena is an independent open-source project and is not affiliated with or endorsed by Blue or Logitech. Blue Yeti and Logitech are trademarks of their respective owners.
