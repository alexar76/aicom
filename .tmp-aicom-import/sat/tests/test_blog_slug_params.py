"""Blog post pages must await Next 16 async params — sync params.slug is undefined."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SLUG_PAGE = ROOT / "web" / "frontend" / "app" / "blog" / "[slug]" / "page.tsx"
STATUS_PAGE = ROOT / "web" / "frontend" / "app" / "status" / "[token]" / "page.tsx"


def test_blog_slug_page_awaits_params_like_the_status_page():
    """Next 16 passes params as a Promise. Reading params.slug without await
    404s every launch post (and the editorial playbooks) while /blog still lists them."""
    src = SLUG_PAGE.read_text(encoding="utf-8")
    status = STATUS_PAGE.read_text(encoding="utf-8")
    assert "params: Promise<{ token: string }>" in status
    assert "const { token } = await params" in status
    assert "params: Promise<{ slug: string }>" in src
    assert "const { slug } = await params" in src
    assert "params.slug" not in src
    assert "cache: 'no-store'" in (ROOT / "web" / "frontend" / "lib" / "server-blog.ts").read_text(
        encoding="utf-8"
    )
