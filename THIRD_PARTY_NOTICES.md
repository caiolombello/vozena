# Third-party notices

Vozena's own source code is licensed under GPL-3.0-or-later as stated in [LICENSE](LICENSE). The dependencies below are separate upstream works and retain their own copyright notices and license terms.

The clean Vozena source release does not redistribute their binaries. During local preparation, `scripts/prepare.py` downloads the pinned upstream artifacts directly, verifies their SHA-256 hashes, and retains the license files supplied by or fetched from those upstream projects under `.deps/` or the isolated Python environment. Those installed license files are the authoritative notices for the exact downloaded artifacts.

## Native audio plugins

### Noise Suppression for Voice / RNNoise

- Component used: `librnnoise_ladspa.so` from Noise Suppression for Voice v1.10
- Upstream release and corresponding source: <https://github.com/werman/noise-suppression-for-voice/releases/tag/v1.10>
- Upstream project license: GNU General Public License version 3, as stated in the [v1.10 license](https://github.com/werman/noise-suppression-for-voice/blob/v1.10/LICENSE)
- Embedded noise suppression library: Xiph RNNoise, BSD 3-Clause; [RNNoise source and license](https://github.com/xiph/rnnoise)

The preparer stores the wrapper's verified license at `.deps/rnnoise/LICENSE` alongside the locally extracted plugin.

### LSP Plugins

- Component used: `lsp-plugins-ladspa.so` 1.2.29 from Fedora package `lsp-plugins-ladspa-1.2.29-1.fc44.x86_64`
- Fedora package page: <https://packages.fedoraproject.org/pkgs/lsp-plugins/lsp-plugins-ladspa/>
- Fedora source package: <https://koji.fedoraproject.org/koji/packageinfo?packageID=26577>
- Upstream source: <https://github.com/lsp-plugins/lsp-plugins/releases/tag/1.2.29>
- Package license expression: LGPL-3.0-or-later AND Zlib

The Fedora RPM supplies `COPYING` and `COPYING.LESSER`; the preparer extracts and verifies both under `.deps/lsp/usr/share/licenses/lsp-plugins-ladspa/`.

The pinned LSP binary is built for Fedora 44 x86_64 and requires glibc 2.43. It is verified and supported on Fedora 44 and Ubuntu 26.04/26.10 x86_64. It is not presented as a portable binary for older Fedora/Ubuntu releases or other distributions.

## Python and Qt runtime

Vozena's isolated runtime installs these hash-pinned official PyPI wheels:

- PySide6 6.11.2
- PySide6_Addons 6.11.2
- PySide6_Essentials 6.11.2
- shiboken6 6.11.2

Qt for Python is available under the GNU Lesser General Public License version 3 and other licensing options described in the [Qt for Python licensing documentation](https://doc.qt.io/qtforpython-6/licenses.html). The installed wheel metadata and license files govern each exact component.

Fedora and Ubuntu system libraries, PipeWire, Python, and other operating-system packages are installed and licensed independently by their respective distributions; they are not part of the Vozena source archive.
