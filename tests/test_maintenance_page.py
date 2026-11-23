"""The "Maintenance" page (frontend/public/maintenance.html): self-contained and English only."""

import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "frontend" / "public" / "maintenance.html"


def test_page_is_self_contained():
    """No scripts or external resources: the site CSP forbids inline scripts, and Cloudflare serves the file as is."""
    html = PAGE.read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    external = re.findall(r"""(?:src|href)=["'](https?:)?//""", html)
    assert external == []
    assert "url(http" not in html and "@import" not in html


def test_page_is_english_only_with_retry_link():
    """English only and no language picker (owner decision of 22.11); the retry button leads to the home page."""
    html = PAGE.read_text(encoding="utf-8")
    assert 'lang="en"' in html and "Technical maintenance" in html
    visible = re.sub(r"<!--.*?-->|/\*.*?\*/", "", html, flags=re.S)  # comments are stripped; the page text has no Cyrillic
    assert not re.search("[А-Яа-яІіЇїЄє]", visible)
    assert 'class="retry" href="/"' in html
