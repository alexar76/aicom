"""The course exporter must not launch Hub tests with Xcode's Python 3.9."""
import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / 'courses/_tooling/update_monorepo_coverage.py'
if not SCRIPT.is_file():
    pytest.skip("courses/ is its own satellite, not in the factory trimmed tree", allow_module_level=True)
spec = importlib.util.spec_from_file_location('course_coverage', SCRIPT)
coverage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage)


@pytest.fixture
def environment(monkeypatch, tmp_path):
    root = tmp_path / 'courses'
    root.mkdir()
    monkeypatch.setattr(coverage, 'ROOT', root)
    monkeypatch.delenv('COURSE_PYTHON', raising=False)
    monkeypatch.setattr(coverage.sys, 'version_info', (3, 9))
    monkeypatch.setattr(coverage.sys, 'executable', '/xcode/python3')
    return root


def test_supported_active_environment_is_preserved(environment, monkeypatch):
    monkeypatch.setattr(coverage.sys, 'version_info', (3, 12))
    monkeypatch.setattr(coverage.sys, 'executable', '/active/venv/bin/python')
    assert coverage.course_python() == '/active/venv/bin/python'


def test_old_system_python_uses_monorepo_venv(environment, monkeypatch):
    (environment.parent / 'aimarket-hub').mkdir()
    expected = str(environment.parent / '.venv/bin/python')
    probes = []

    def probe(args, **kwargs):
        probes.append(args)
        if args[0] != expected:
            raise FileNotFoundError(args[0])
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(coverage.subprocess, 'run', probe)
    assert coverage.course_python() == expected
    assert all(args[1] == '-c' for args in probes)


def test_missing_supported_environment_fails_before_pytest(environment, monkeypatch):
    def probe(args, **kwargs):
        assert args[1] == '-c'
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(coverage.subprocess, 'run', probe)
    with pytest.raises(SystemExit, match='COURSE_PYTHON='):
        coverage.main()


def test_explicit_old_python_is_rejected_without_silent_fallback(environment, monkeypatch):
    monkeypatch.setenv('COURSE_PYTHON', '/explicit/python')
    monkeypatch.setattr(coverage.sys, 'version_info', (3, 12))
    probes = []

    def probe(args, **kwargs):
        probes.append(args[0])
        return subprocess.CompletedProcess(args, 1)

    monkeypatch.setattr(coverage.subprocess, 'run', probe)
    with pytest.raises(SystemExit, match='Python >=3.11'):
        coverage.course_python()
    assert probes == ['/explicit/python']


def test_explicit_supported_python_is_used(environment, monkeypatch):
    monkeypatch.setenv('COURSE_PYTHON', '/explicit/python')
    monkeypatch.setattr(coverage.subprocess, 'run', lambda args, **kw: subprocess.CompletedProcess(args, 0))
    assert coverage.course_python() == '/explicit/python'
