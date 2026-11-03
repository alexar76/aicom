import pytest

from aimarket_hub import landing


@pytest.mark.parametrize("lang", ["en", "ru", "es", "fr", "zh"])
@pytest.mark.parametrize("render", [landing.docs_html, landing.integration_examples_html])
def test_localized_entry_and_language_preserving_role_links(lang, render):
    html = render("https://modelmarket.dev", ecosystem_links=True, lang=lang)
    assert f'<html lang="{lang}">' in html
    assert landing.COPY[lang][2] in html
    for role in ("provider", "consumer"):
        assert f'/start?role={role}&amp;lang={lang}' in html
    assert f'/publish?lang={lang}' in html
    if lang != "en":
        assert '<div lang="en">' in html
        assert landing.COPY[lang][8] in html


def test_third_party_hub_does_not_advertise_reference_workspaces():
    html = landing.docs_html("https://hub.example", ecosystem_links=False, lang="ru")
    assert "play.modelmarket.dev" not in html
    assert 'href="/start?lang=ru"' in html


def test_docker_example_builds_the_public_standalone_context():
    html = landing.integration_examples_html()
    assert "Dockerfile.standalone" in html
    assert "127.0.0.1:9083:9083" in html
    assert "aimarket-hub-data:/app/data" in html
    assert "modelmarket/hub" not in html


def test_invalid_locale_falls_back_without_reflecting_input():
    html = landing.docs_html(lang='<script>alert(1)</script>')
    assert '<html lang="en">' in html
    assert "alert(1)" not in html
