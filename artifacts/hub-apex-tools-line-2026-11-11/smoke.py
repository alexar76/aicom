"""In the new image, no network: both files as built, the dictionary has the line in five languages, the app imports."""
import hashlib, json
want = {
    "/app/terminal-home.html": "1d79a2164a7511a562427b7c310cb060d35f280b06c0bc4a3768b6ba98169c23",
    "/app/hub-ui-i18n.json": "a478a613708e7f47046aed2e654a523384486ea534ae9c6b42aea33ca8cfbf1d",
}
for path, digest in want.items():
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == digest, path
html = open("/app/terminal-home.html", encoding="utf-8").read()
assert html.count('<p class="apex-tools">') == 1 and html.count("<!-- apex-only -->") == 1
ui = json.load(open("/app/hub-ui-i18n.json", encoding="utf-8"))["ui"]
for lang in ("en", "ru", "es", "fr", "zh"):
    assert ui[lang]["apex_tools_line"] and ui[lang]["apex_tools_free"], lang
import aimarket_hub.api  # noqa: F401
from aimarket_hub.ui_assets import ui_asset_path
assert ui_asset_path("terminal-home.html", "/app") == "/app/terminal-home.html"
print("smoke ok: files as built, line once, five languages, app imports, /app copy is the one served")
