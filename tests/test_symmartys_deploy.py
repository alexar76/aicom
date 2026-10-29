"""Local-only deployment preparation checks; Docker/SSH are never contacted."""

import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("symmartys_deploy_state", ROOT / "deploy/symmartys_state.py")
state = importlib.util.module_from_spec(spec)
spec.loader.exec_module(state)
KEY = base64.b64encode(b"k" * 32).decode()


class DeploymentPreparationTests(unittest.TestCase):
    def env_file(self, root, extra=""):
        path = root / ".env"
        path.write_text("EMPORION_PUBLIC_URL=https://modelmarket.dev/providers/emporion\n"
                        "EMPORION_SIGNING_KEY_PATH=/data/emporion_signing_key\n"
                        "EMPORION_API_TOKEN='opaque-$value#not-a-command'\n"
                        "ORACLE_TRUSTED_HUBS=https://hub.example=pin-with-padding==\n"
                        "ORACLE_HUB_AUDIENCES=https://old-alias.example\n"
                        "SYMMARTYS_VOLUME_NAME=existing-provider-data\n"
                        f"SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY={KEY}\n" + extra)
        return path

    def test_existing_destination_is_preferred_and_explicit_path_is_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy, current = root / "emporion", root / "symmartys"
            self.assertEqual(state.destination(None, legacy, current), current)
            legacy.mkdir()
            self.assertEqual(state.destination(None, legacy, current), legacy)
            self.assertEqual(state.destination(str(current), legacy, current), current)
            with self.assertRaises(ValueError):
                state.destination("/opt/../wrong")

    def test_key_and_trust_preservation_with_old_and_new_audiences(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.env_file(Path(directory))
            original = path.read_text()
            prepared, summary = state.prepare_env(path)
            self.assertEqual(path.read_text(), original, "plan must not write")
            self.assertIn("SYMMARTYS_SIGNING_KEY_PATH=/data/emporion_signing_key", prepared)
            self.assertIn("SYMMARTYS_API_TOKEN='opaque-$value#not-a-command'", prepared)
            self.assertIn("ORACLE_TRUSTED_HUBS=https://hub.example=pin-with-padding==", prepared)
            self.assertIn("ORACLE_HUB_AUDIENCES=https://old-alias.example,https://modelmarket.dev/providers/emporion,https://modelmarket.dev/providers/symmartys", prepared)
            self.assertNotIn("opaque-$value", json.dumps(summary))
            state.apply_env(path)
            self.assertEqual(path.with_name(".env.before-symmartys").read_text(), original)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state.prepare_env(path)[0], path.read_text(), "migration must be idempotent")

    def test_missing_volume_or_previous_identity_pin_refuses_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.env_file(Path(directory))
            for name in ("SYMMARTYS_VOLUME_NAME", "SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY"):
                original = path.read_text()
                path.write_text("\n".join(line for line in original.splitlines() if not line.startswith(name + "=")) + "\n")
                before = path.read_text()
                with self.assertRaises(ValueError):
                    state.apply_env(path)
                self.assertEqual(path.read_text(), before)
                self.assertFalse(path.with_name(".env.before-symmartys").exists())
                path.write_text(original)
            path.write_text("SYMMARTYS_VOLUME_NAME=deliberately-new-data\n")
            self.assertTrue(state.prepare_env(path, fresh=True)[1]["fresh_identity_requested"])

    def test_rendered_vhost_uses_the_actual_legacy_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "rendered.conf"
            result = subprocess.run(["bash", str(ROOT / "scripts/deploy_symmartys.sh"),
                                     "--dest", "/opt/emporion", "--render-vhost", str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("root /opt/emporion/src/symmartys/docs/landing;", output.read_text())
            self.assertNotIn("@@", output.read_text())

    def preflight(self, root, *, legacy="false", volume="1"):
        (root / "src/symmartys").mkdir(parents=True)
        (root / "src/symmartys/docker-compose.yml").write_text("services: {}\n")
        env_file = self.env_file(root)
        binary = root / "bin"
        binary.mkdir()
        docker = binary / "docker"
        docker.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALL_LOG\"\n"
                          "case \"$1\" in\ninfo) exit 0;;\ninspect) echo \"$LEGACY_RUNNING\";;\n"
                          "ps) exit 0;;\nvolume) test \"$VOLUME_EXISTS\" = 1;;\n*) exit 97;;\nesac\n")
        docker.chmod(0o755)
        env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ["PATH"],
                   CALL_LOG=str(root / "docker-calls.log"), LEGACY_RUNNING=legacy, VOLUME_EXISTS=volume)
        before = env_file.read_text()
        result = subprocess.run(["bash", str(ROOT / "scripts/deploy_symmartys.sh"), "--dest", str(root), "--check"],
                                env=env, capture_output=True, text=True)
        self.assertEqual(env_file.read_text(), before)
        self.assertFalse(env_file.with_name(".env.before-symmartys").exists())
        self.assertNotIn("opaque-$value", result.stdout + result.stderr)
        calls = (root / "docker-calls.log").read_text()
        self.assertNotIn("create", calls)
        self.assertNotIn("stop", calls)
        self.assertNotIn("compose", calls)
        return result

    def test_preflight_is_read_only_with_existing_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.preflight(Path(directory))
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_running_legacy_runtime_is_refused_without_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.preflight(Path(directory), legacy="true")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Legacy container", result.stderr)

    def test_missing_existing_volume_is_refused_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.preflight(Path(directory), volume="0")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("volume does not exist", result.stderr)


if __name__ == "__main__":
    unittest.main()
