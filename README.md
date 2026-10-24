<div align="center">

# Vozena

**Real-time voice processing for Linux.**  
Built for clean speech, reliable virtual audio devices, and clear local control.

[![CI](https://github.com/caiolombello/vozena/actions/workflows/ci.yml/badge.svg)](https://github.com/caiolombello/vozena/actions/workflows/ci.yml)
[![License: GPL-3.0-or-later](https://img.shields.io/badge/License-GPL--3.0--or--later-blue.svg)](LICENSE)

</div>

---

Vozena v0.4.2 is a public preview. It has been validated on:

- Fedora 44 x86_64
- Ubuntu 26.04 x86_64
- KDE Plasma with PipeWire 1.6.9
- the classic USB Blue Yeti (`USB b58e:9e84`)

Other Linux distributions, desktop environments, architectures, PipeWire versions, and microphones have not been validated. The pinned Fedora LSP build requires glibc 2.43, so the bootstrap is intentionally limited to Fedora 44 and Ubuntu 26.04 x86_64. Windows and macOS are not supported.

The native interface is currently in Brazilian Portuguese. This guide includes its exact labels where you need to find a control.

Vozena does not provide echo cancellation and cannot promise to remove every background sound. It does not control the microphone's hardware gain or pickup pattern; set those on the Blue Yeti itself. Compatibility with any particular meeting app is not guaranteed.

## Install from a release

The release is a clean source archive. It contains no vendored `.deps`, virtual environment, plugin binary, or Python wheel. Preparation therefore needs a network connection to download pinned files from GitHub, Fedora, and PyPI.

1. Install the system prerequisites:

   **On Fedora 44:**

   ```bash
   sudo dnf install python3 python3-pip pipewire pipewire-utils rpm cpio systemd \
     libsndfile libatomic libstdc++ xcb-util-cursor
   ```

   **On Ubuntu 26.04:**

   ```bash
   sudo apt install python3 python3-pip python3-venv pipewire pipewire-bin cpio systemd \
     libsndfile1 libatomic1 libstdc++6 libxcb-cursor0 rpm2cpio
   ```

   A normal Fedora 44 or Ubuntu 26.04 KDE installation already supplies the remaining Qt display libraries used by the app.

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

Install the system prerequisites for your distribution (Fedora or Ubuntu) as shown above, then:

```bash
git clone https://github.com/caiolombello/vozena.git
cd vozena
python3 scripts/prepare.py
~/.local/bin/vozena
```

Preparation options for development and CI are documented by `python3 scripts/prepare.py --help`. `--plugins-only` prepares only the pinned native plugins, `--root` selects another source checkout, and `--venv-dir` selects an absolute persistent runtime directory.

## First setup

1. Plug in your Blue Yeti and set the physical polar pattern switch on the back to **Cardioid** (the icon shaped like a heart).
2. Adjust the physical gain knob on the back so your loudest speech never distorts.
3. Open Vozena and click **Ativar tratamento**.
4. In your calling app (Discord, Google Meet, Teams, Zoom, Slack, Telegram, OBS Studio), choose **Yeti Processado** as the microphone.
5. In that same app, turn off any built-in noise suppression and automatic gain control if possible, so two algorithms do not compete.

## Daily usage

- **Tray icon**: closing the main window leaves Vozena running in the system tray. Use the tray icon to reopen the controls or quit.
- **Global mute shortcut**: press <kbd>Meta</kbd>+<kbd>Shift</kbd>+<kbd>M</kbd> anywhere on the desktop to toggle mute. You can reassign it at any time in **KDE System Settings → Shortcuts → Vozena**.
- **Quick controls**:
  - **Suavização de ruído**: adjust between softer room noise and stronger suppression.
  - **Portão de ruído**: sets the threshold where background sound is silenced.
  - **Volume de saída**: fine adjustment for processed speech.
  - **Testar voz**: record a short test phrase in memory, listen to the original vs. treated version, and apply calibrated settings.
- **Microphone disconnection**: if you unplug the Blue Yeti, Vozena automatically pauses and releases the device. Reconnect it and click **Reconectar**.

## Uninstall

To remove the application, the desktop entry, and the launcher without touching your configuration or settings:

```bash
python3 scripts/uninstall.py
```

Settings remain at `~/.config/yeti-voice/settings.json` and the isolated Python runtime remains at `~/.local/share/vozena/runtime/`.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│ Blue Yeti (ALSA / PipeWire hardware node)                              │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ PipeWire Filter Chain: vozena-yeti-sink                                │
│   ├─ LADSPA noise suppression (RNNoise v1.10)                          │
│   ├─ LADSPA gate (LSP Plugins v1.2.29)                                 │
│   └─ LADSPA limiter (LSP Plugins v1.2.29)                              │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Virtual Source: Yeti Processado                                        │
│   └─ selected by meeting applications                                  │
└────────────────────────────────────────────────────────────────────────┘
```

The audio pipeline runs entirely on your system through local LADSPA plugins loaded into PipeWire. No audio stream is sent over the network.

## Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md) before submitting pull requests or issue reports.
