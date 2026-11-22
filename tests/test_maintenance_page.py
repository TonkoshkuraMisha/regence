"""Страница «Технические работы» (frontend/public/maintenance.html): самодостаточна и только английская."""

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


def test_page_is_english_only_with_retry_link():
    """Только английский и без выбора языка (решение владельца 22.11); кнопка повтора ведёт на главную."""
    html = PAGE.read_text(encoding="utf-8")
    assert 'lang="en"' in html and "Technical maintenance" in html
    visible = re.sub(r"<!--.*?-->|/\*.*?\*/", "", html, flags=re.S)  # комментарии по-русски (правило 6), текст страницы — нет
    assert not re.search("[А-Яа-яІіЇїЄє]", visible)
    assert 'class="retry" href="/"' in html
