"""Dataset directories are literal arguments, never shell commands."""
import json
import subprocess
import sys
from pathlib import Path


def test_mcptox_builder_accepts_shell_metacharacters_as_literal_paths(tmp_path):
    script = Path(__file__).resolve().parents[1] / "warden/scripts/scanner-comparison/build_mcptox.py"
    source = tmp_path / "input;touch PWN;#"
    definitions = source / "def_tool"
    definitions.mkdir(parents=True)
    (definitions / "tool.py").write_text('def example(value: str):\n    """A harmless example."""\n    return value\n')
    (source / "pure_tool.json").write_text(json.dumps([{"example": {
        "server_name": "example", "tool_address": "tool.py", "tool_name": "example",
        "tool_content": "A harmless example.", "security risk": "none", "paradigm": "none",
    }}]))
    (source / "response_all.json").write_text(json.dumps({"servers": {
        "example": {"malicious_instance": [], "clean_system_promot": ""},
    }}))
    output = tmp_path / "output with spaces"
    result = subprocess.run([sys.executable, str(script), str(source), str(output)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "PWN").exists()
    assert json.loads((output / "mcptox-labels.json").read_text())["def_tool_files_parsed"] == 1
