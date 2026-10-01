"""Colab links must survive f-string expansion and the course-directory migration."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATORS = sorted((ROOT / 'courses').glob('*/scripts/labs_to_notebooks.py'))


def expected_target(course: Path, stem: str) -> str:
    config = json.loads((course / 'course.config.json').read_text(encoding='utf-8'))
    prefix = (config.get('repo_subpath') or '').strip('/')
    if prefix:
        prefix += '/'
    return f"https://colab.research.google.com/github/{config['github_repo']}/blob/main/{prefix}notebooks/{stem}.ipynb"


class NotebookLinksTest(unittest.TestCase):
    def check_badge(self, path: Path, course: Path) -> None:
        notebook = json.loads(path.read_text(encoding='utf-8'))
        markdown = ''.join(notebook['cells'][0]['source'])
        self.assertIn('](' + expected_target(course, path.stem) + ')', markdown)
        self.assertNotIn('/notebooks/{}', markdown)
        self.assertNotIn('__NB__', markdown)

    def test_every_generator_emits_real_colab_targets(self) -> None:
        self.assertTrue(GENERATORS)
        for script in GENERATORS:
            with self.subTest(course=script.parent.parent.name), tempfile.TemporaryDirectory() as out:
                spec = importlib.util.spec_from_file_location('course_notebook_generator', script)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.OUT_DIR = Path(out)
                with contextlib.redirect_stdout(io.StringIO()):
                    module.main()
                generated = sorted(Path(out).glob('*.ipynb'))
                self.assertEqual(len(generated), len(module.LABS))
                for path in generated:
                    self.check_badge(path, script.parent.parent)

    def test_committed_notebooks_have_real_colab_targets(self) -> None:
        for script in GENERATORS:
            course = script.parent.parent
            for path in sorted((course / 'notebooks').glob('*.ipynb')):
                with self.subTest(notebook=str(path.relative_to(ROOT))):
                    self.check_badge(path, course)


if __name__ == '__main__':
    unittest.main()
