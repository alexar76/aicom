"""Bundle the authored UI without maintaining a second tracked copy."""
from pathlib import Path
import runpy
import shutil

from setuptools import setup
from setuptools.command.build_py import build_py

ROOT = Path(__file__).resolve().parent
UI_FILES = runpy.run_path(str(ROOT / "aimarket_hub" / "ui_assets.py"))["UI_FILES"]


class BuildPy(build_py):
    def run(self):
        super().run()
        target = Path(self.build_lib) / "aimarket_hub" / "static" / "ui"
        target.mkdir(parents=True, exist_ok=True)
        for name in UI_FILES:
            shutil.copyfile(ROOT / name, target / name)


setup(cmdclass={"build_py": BuildPy})
