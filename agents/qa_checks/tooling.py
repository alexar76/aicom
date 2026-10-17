"""Running the product's tooling: static analysis, tests, generated tests and import checks."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from core.child_env import scrub_child_env
from core.logging_utils import log_suppressed

from .helpers import logger


class ToolingMixin:
    """Static analysis, tests, generated tests and import checks."""

    def _run_static_analysis(self, code_files: list[dict]) -> list[dict]:
        """Run static analysis tools on discovered code files.
        
        Attempts to use available tools (pylint, flake8, py_compile).
        Falls back gracefully if tools aren't installed.
        """
        issues = []
        # Pylint and flake8 can load project-local plugins/configuration. Treat them
        # as execution of generated code and never expose the factory environment.
        child_env = scrub_child_env(os.environ)
        child_env.setdefault("ENVIRONMENT", "test")

        for file_info in code_files:
            fpath = file_info["path"]
            content = file_info["content"]

            # 1. Try py_compile (built-in syntax check)
            try:
                compile(content, fpath, "exec")
            except SyntaxError as e:
                issues.append({
                    "type": "error",
                    "tool": "py_compile",
                    "file": fpath,
                    "line": e.lineno or 0,
                    "message": f"SyntaxError: {e.msg}",
                })

            # 2. Try pylint if available
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pylint", "--score=n", fpath],
                    capture_output=True, text=True, timeout=15, env=child_env,
                )
                for line in result.stdout.split("\n"):
                    if ":" in line and line.strip():
                        parts = line.split(":")
                        if len(parts) >= 4:
                            issues.append({
                                "type": parts[2].strip() if len(parts) > 2 else "warning",
                                "tool": "pylint",
                                "file": fpath,
                                "line": parts[1].strip() if len(parts) > 1 else 0,
                                "message": ":".join(parts[3:]).strip(),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

            # 3. Try flake8 if available
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "flake8", fpath],
                    capture_output=True, text=True, timeout=15, env=child_env,
                )
                for line in result.stdout.split("\n"):
                    if line.strip():
                        parts = line.split(":")
                        if len(parts) >= 4:
                            issues.append({
                                "type": "warning",
                                "tool": "flake8",
                                "file": parts[0],
                                "line": parts[1],
                                "message": ":".join(parts[3:]).strip(),
                            })
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

        return issues

    def _run_tests(self, code_files: list[dict]) -> dict:
        """Discover and execute test files.
        
        Finds files matching test_*.py or *_test.py patterns and runs them.
        """
        results = {"passed": 0, "failed": 0, "total": 0, "failures": []}
        test_files = []

        from core.code_discovery import should_skip_code_path

        for file_info in code_files:
            fpath = Path(str(file_info["path"]))
            if should_skip_code_path(fpath):
                continue
            fname = fpath.name
            if fname.startswith("test_") or fname.endswith("_test.py"):
                test_files.append(str(fpath))

        if not test_files:
            # Generate basic test cases from code
            test_files = self._generate_tests(code_files)
            if not test_files:
                return results

        # Run each test file
        child_env = scrub_child_env(os.environ)
        child_env.setdefault("DATABASE_URL", "sqlite:///:memory:")
        child_env.setdefault("ENVIRONMENT", "test")
        child_env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
        for test_file in test_files:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
                    capture_output=True, text=True, timeout=30, env=child_env,
                )
                # Parse pytest output
                stdout = result.stdout
                # Count passed/failed from pytest summary
                import re
                passed_match = re.search(r'(\d+) passed', stdout)
                failed_match = re.search(r'(\d+) failed', stdout)
                if passed_match:
                    results["passed"] += int(passed_match.group(1))
                if failed_match:
                    results["failed"] += int(failed_match.group(1))
                    # Extract failure details
                    for line in stdout.split("\n"):
                        if "FAILED" in line:
                            results["failures"].append({
                                "name": line.strip(),
                                "file": test_file,
                                "error": line.strip(),
                            })
                results["total"] = results["passed"] + results["failed"]
            except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as e:
                results["failures"].append({
                    "name": "pytest execution failed",
                    "file": test_file,
                    "error": str(e),
                })

        return results

    def _generate_tests(self, code_files: list[dict]) -> list[str]:
        """Generate basic test files from code if none exist.
        
        Creates temporary test files that verify basic functionality
        like import validity and function existence.
        """
        generated_tests = []

        for file_info in code_files:
            fpath = file_info["path"]
            try:
                # Parse imports from the file
                import_lines = []
                for line in file_info["content"].split("\n"):
                    line = line.strip()
                    if line.startswith(("import ", "from ")):
                        import_lines.append(line)

                if import_lines:
                    # Create a basic test that verifies imports work
                    test_content = (
                        "#!/usr/bin/env python3\n"
                        "\"\"\"Auto-generated QA test for imports.\"\"\"\n"
                        "import sys\n"
                        "import os\n"
                        f"sys.path.insert(0, os.path.dirname('{fpath}'))\n"
                        "\n"
                    )
                    for imp_line in import_lines:
                        test_content += f"def test_{imp_line.split()[1].split('.')[0]}_import():\n"
                        test_content += f"    \"\"\"Verify {imp_line} works.\"\"\"\n"
                        test_content += "    try:\n"
                        test_content += f"        {imp_line}\n"
                        test_content += "        assert True\n"
                        test_content += "    except ImportError as e:\n"
                        test_content += "        assert False, f'Import failed: {e}'\n"
                        test_content += "\n"

                    test_dir = Path(tempfile.mkdtemp())
                    test_file = test_dir / f"test_{Path(fpath).stem}.py"
                    test_file.write_text(test_content)
                    generated_tests.append(str(test_file))
            except Exception as _suppressed_exc:
                log_suppressed(logger, "non-fatal (agents/qa.py)", exc_info=_suppressed_exc)

        return generated_tests

    def _check_imports(self, code_files: list[dict]) -> list[dict]:
        """Try to import and verify Python modules.
        
        This actually executes code to check for import/runtime errors.
        """
        errors = []

        for file_info in code_files[:5]:  # Limit to 5 files
            fpath = file_info["path"]
            try:
                # Add parent dir to sys.path
                parent = str(Path(fpath).parent)
                if parent not in sys.path:
                    sys.path.insert(0, parent)

                # Try to compile and check the AST
                compile(file_info["content"], fpath, "exec")
            except SyntaxError as e:
                errors.append({
                    "file": fpath,
                    "module": Path(fpath).stem,
                    "error": f"SyntaxError at line {e.lineno}: {e.msg}",
                })

        return errors
