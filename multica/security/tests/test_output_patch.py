"""Exercise exact-source validation and the actual diff without fetching upstream."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("output_patch", HERE / "apply-output-patch.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PatchSafety(unittest.TestCase):
    def test_unknown_source_is_refused_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "server/internal/daemon/client.go"
            path.parent.mkdir(parents=True)
            path.write_text("unreviewed source\n")
            with self.assertRaisesRegex(ValueError, "source differs"):
                module.apply(root, False)
            self.assertEqual(path.read_text(), "unreviewed source\n")
            self.assertEqual(len(list(root.rglob("*.go"))), 1)

    def test_source_escape_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "server").symlink_to("/tmp", target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes"):
                module.apply(root, False)

    def test_bundle_integrity_and_upstream_tests_are_shipped(self):
        manifest = json.loads((HERE / "patches/0001-redact-task-results.json").read_text())
        patch = HERE / "patches/0001-redact-task-results.patch"
        self.assertEqual(module.digest(patch), manifest["patch_sha256"])
        paths = {entry["path"] for entry in manifest["files"]}
        for path in ("server/internal/daemon/terminal_report_queue.go",
                     "server/internal/handler/daemon.go", "server/internal/service/task.go",
                     "server/internal/daemon/aicom_output_redaction_test.go"):
            self.assertIn(path, paths)


if __name__ == "__main__":
    unittest.main()
