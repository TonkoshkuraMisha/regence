"""Страница «Технические работы» (frontend/public/maintenance.html): самодостаточна и на трёх языках."""

import re
from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "frontend" / "public" / "maintenance.html"


def test_page_is_self_contained():
    """Без скриптов и внешних ресурсов: CSP сайта запрещает встроенные скрипты, а Cloudflare отдаёт файл как есть."""
    html = PAGE.read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    external = re.findall(r"""(?:src|href)=["'](https?:)?//""", html)
    assert external == []
    assert "url(http" not in html and "@import" not in html


def test_page_has_three_languages_and_retry_link():
    html = PAGE.read_text(encoding="utf-8")
    for lang in ("en", "uk", "ru"):
        assert f'<section class="lang" lang="{lang}">' in html
    assert 'class="retry" href="/"' in html
