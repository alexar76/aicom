"""In the new image, no network: the file is the one built, the app imports, both pages carry the styled links."""
import hashlib
assert hashlib.sha256(open("/app/aimarket_hub/landing.py", "rb").read()).hexdigest() == "99f75d83d5656c22d7bbb0d0c2a17920e052e21c1b622835b7f99e06470e1aed"
import aimarket_hub.api  # noqa: F401 - the whole app imports
from aimarket_hub import landing
assert landing.__file__ == "/app/aimarket_hub/landing.py", landing.__file__
for lang in ("en", "ru", "es", "fr", "zh"):
    for page in (landing.integration_examples_html(lang=lang), landing.docs_html(lang=lang)):
        assert f'<p class="section-note"><a href="/developers?lang={lang}">' in page, lang
print("smoke ok: landing.py as built, app imports, /examples and /developers in 5 languages carry section-note links")
