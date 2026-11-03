"""Resolve authored UI files in source checkouts and portable wheel installations."""
from pathlib import Path

UI_FILES = (
    "terminal-home.html", "operator.html", "plugins-demo.html",
    "hub-ui-i18n.json", "cap-descriptions-i18n.json", "studio-ui-i18n.json",
)


def ui_asset_path(name: str, source_root: str | Path | None = None) -> str:
    if name not in UI_FILES:
        raise ValueError("Unknown bundled UI asset")
    package = Path(__file__).resolve().parent
    source = Path(source_root) if source_root is not None else package.parent
    authored = source / name
    return str(authored if authored.is_file() else package / "static" / "ui" / name)
