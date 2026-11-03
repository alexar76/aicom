"""In the new image, no network: theme.py as built, the app imports, site.css carries the fallback, pages render."""
import hashlib
assert hashlib.sha256(open("/app/aimarket_hub/theme.py", "rb").read()).hexdigest() == "7d9b90add3e707269ad413cf618ecf271f67a76ba4b58d114acdf93b61349aaa"
import aimarket_hub.api  # noqa: F401
from aimarket_hub import landing, theme
assert theme.__file__ == "/app/aimarket_hub/theme.py"
assert ":where(a[href]) { color: var(--cyan); }" in theme.SITE_CSS
assert 'class="section-note"' in landing.integration_examples_html(lang="en")
print("smoke ok: theme.py as built, app imports, site.css has the link fallback, /examples still has section-note")
