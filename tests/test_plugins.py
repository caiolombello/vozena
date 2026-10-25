"""Plugin sources: pinned copies or a verified distribution LSP."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from yeti_voice import plugins
from yeti_voice.processing import ladspa_requirements

ROOT = Path(__file__).resolve().parent.parent


class PluginSourceTests(unittest.TestCase):
    def setUp(self):
        plugins._verified.clear()

    def test_paths_follow_the_manifest_and_default_to_bundled_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(plugins.plugin_paths(root)["lsp"], root / ".deps" / plugins.BUNDLED["lsp"])
            (root / ".deps").mkdir()
            (root / ".deps/manifest.json").write_text(json.dumps({
                "rnnoise": {"path": plugins.BUNDLED["rnnoise"]},
                "lsp": plugins.system_entry("/usr/lib/ladspa/lsp-plugins-ladspa.so")}))
            paths = plugins.plugin_paths(root)
        self.assertEqual(paths["lsp"], Path("/usr/lib/ladspa/lsp-plugins-ladspa.so"))
        self.assertEqual(paths["rnnoise"], root / ".deps" / plugins.BUNDLED["rnnoise"])

    def test_plugins_writable_by_other_users_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            library = Path(directory) / "lsp-plugins-ladspa.so"
            library.write_bytes(b"not a plugin")
            with patch.object(plugins.subprocess, "run") as run:
                with self.assertRaisesRegex(ValueError, "outros usuários"):
                    plugins.verify_system_plugin("lsp", library)
                with self.assertRaisesRegex(ValueError, "absoluto"):
                    plugins.verify_system_plugin("lsp", "relative/lsp.so")
                run.assert_not_called()

    def test_verification_runs_once_per_file_version(self):
        library = Path(sys.executable).resolve()  # root-owned on a normal system
        try:
            plugins._check_secure(library)
        except ValueError:
            self.skipTest("interpreter is not root-owned here")
        passed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(plugins.subprocess, "run", return_value=passed) as run:
            plugins.verify_system_plugin("lsp", library)
            plugins.verify_system_plugin("lsp", library)
        self.assertEqual(run.call_count, 1)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[1:3], ["-I", str(plugins.CHECKER)])
        self.assertEqual(json.loads(arguments[-1]), ladspa_requirements()["lsp"])
        failed = subprocess.CompletedProcess([], 1, "", "missing http://lsp-plug.in/x: Ratio\n")
        plugins._verified.clear()
        with patch.object(plugins.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(ValueError, "não é compatível.*Ratio"):
                plugins.verify_system_plugin("lsp", library)


@unittest.skipUnless((ROOT / ".deps" / plugins.BUNDLED["lsp"]).is_file(), "needs prepared plugins")
class LadspaCheckerTests(unittest.TestCase):
    def check(self, library, name):
        return subprocess.run([sys.executable, "-I", str(plugins.CHECKER), str(library),
                               json.dumps(ladspa_requirements()[name])], capture_output=True, text=True, timeout=30)

    def test_pinned_plugins_expose_every_control_vozena_sets(self):
        for name in ("lsp", "rnnoise"):
            with self.subTest(name=name):
                result = self.check(ROOT / ".deps" / plugins.BUNDLED[name], name)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_a_different_library_is_rejected_with_the_missing_controls(self):
        result = self.check(ROOT / ".deps" / plugins.BUNDLED["rnnoise"], "lsp")
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing http://lsp-plug.in/plugins/ladspa/compressor_mono: Ratio", result.stderr)


if __name__ == "__main__":
    unittest.main()
