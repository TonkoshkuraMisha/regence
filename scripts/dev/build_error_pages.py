"""
Сборка двух служебных страниц с ретро-коллажем: «Технические работы» и страница ожидания до запуска.

Что делает: берёт портреты мастеров из frontend/public/assets/champions (только общественное достояние и CC0 — их
лицензии записаны в ATTRIBUTION.md), превращает в маленькие сепия-снимки, кладёт на фон «снимками на столе» вместе с
силуэтами фигур и обрывками партитур, а текст оставляет поверх тёмной вуали, чтобы фон не мешал читать.
Пишет два файла:
  * frontend/public/maintenance.html — самодостаточная страница 502/503/504 (nginx и Cloudflare Custom Errors);
  * ops/landing/src/page.js — HTML страницы ожидания для Worker regence-landing (экспорт PAGE).
Страницы нарочно разные по раскладке: у «Технических работ» две ленты кадров сверху и снизу и бланк партии, у ожидания —
снимки по бокам, как на стене клуба. Скриптов и внешних ресурсов в страницах нет: картинки — data-URI.

    python -m scripts.dev.build_error_pages
"""
# ruff: noqa: E501  — внутри CSS и data-URI, их строки не переносятся

import base64
import io
import pathlib

from PIL import Image, ImageEnhance, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "frontend" / "public" / "assets" / "champions"
MAINTENANCE_OUT = ROOT / "frontend" / "public" / "maintenance.html"
LANDING_OUT = ROOT / "ops" / "landing" / "src" / "page.js"

# Только общественное достояние и CC0 (ATTRIBUTION.md, раздел портретов): атрибуция на странице не требуется.
LANDING_PHOTOS = ["morphy", "Capablanca", "Alekhine", "Steinitz", "Tal", "Tarrasch", "Pillsbury", "anderssen"]
MAINTENANCE_PHOTOS = ["philidor", "staunton", "zukertort", "Marshall", "Keres", "Rubinstein", "paulsen", "labourdonnais"]

PHOTO_SIZE = (150, 190)  # пикселей: снимок виден небольшим, запас на ретина-экраны не нужен — фон приглушён
SEPIA_DARK, SEPIA_LIGHT = (38, 24, 12), (236, 214, 170)


def sepia_photo(name: str) -> str:
    """Портрет мастера → маленький сепия-снимок как data-URI (JPEG)."""
    image = Image.open(PHOTOS / f"{name}.jpg").convert("L")
    image = ImageOps.fit(image, PHOTO_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.25))
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.1)
    toned = ImageOps.colorize(image, black=SEPIA_DARK, white=SEPIA_LIGHT)
    buffer = io.BytesIO()
    toned.save(buffer, "JPEG", quality=58, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


# Силуэты фигур (viewBox 0 0 100 130), заливка задаётся классом.
PIECES = {
    "pawn": '<circle cx="50" cy="28" r="15"/><rect x="33" y="44" width="34" height="7" rx="3.5"/>'
            '<path d="M41 51Q39 78 29 100L71 100Q61 78 59 51Z"/><rect x="23" y="100" width="54" height="9" rx="4.5"/>'
            '<rect x="17" y="109" width="66" height="10" rx="5"/>',
    "rook": '<path d="M24 14h14v12h8V14h8v12h8V14h14v28H24z"/><path d="M30 42h40l5 56H25z"/>'
            '<rect x="18" y="98" width="64" height="10" rx="4"/><rect x="12" y="108" width="76" height="11" rx="5"/>',
    "bishop": '<circle cx="50" cy="12" r="7"/><path d="M50 20C30 34 30 56 42 66L36 78h28l-6-12C70 56 70 34 50 20z"/>'
              '<rect x="30" y="78" width="40" height="8" rx="4"/><path d="M38 86h24l6 14H32z"/>'
              '<rect x="20" y="100" width="60" height="10" rx="5"/><rect x="14" y="110" width="72" height="10" rx="5"/>',
    "king": '<rect x="46" y="4" width="8" height="26" rx="2"/><rect x="38" y="12" width="24" height="8" rx="2"/>'
            '<path d="M50 30C28 32 24 58 38 70L32 98h36l-6-28C76 58 72 32 50 30z"/>'
            '<rect x="22" y="98" width="56" height="10" rx="4"/><rect x="14" y="108" width="72" height="11" rx="5"/>',
    "queen": '<circle cx="22" cy="22" r="6"/><circle cx="50" cy="12" r="6"/><circle cx="78" cy="22" r="6"/>'
             '<path d="M20 30l12 36h36l12-36-16 14-14-24-14 24z"/><path d="M34 66h32l6 32H28z"/>'
             '<rect x="20" y="98" width="60" height="10" rx="4"/><rect x="12" y="108" width="76" height="11" rx="5"/>',
}

COMMON_CSS = """
:root { color-scheme: dark; --bg: #1A120B; --gold: #D0A972; --wheat: #F5DEB3; --muted: #A68F6C; }
html, body { margin: 0; min-height: 100%; }
body {
    position: relative; overflow: hidden; min-height: 100vh; box-sizing: border-box; padding: 32px 20px; display: flex;
    align-items: center; justify-content: center; color: var(--wheat); font-family: Georgia, 'Times New Roman', serif;
    background:
        radial-gradient(ellipse 70% 45% at 50% 0%, rgba(208, 169, 114, .14), transparent 70%),
        repeating-conic-gradient(rgba(245, 222, 179, .06) 0 25%, transparent 0 50%) 0 0 / 200px 200px,
        var(--bg);
}
/* Вуаль: затемняет коллаж под текстом, по краям отпускает — снимки видны, читать не мешают. */
body::before {
    content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none;
    background: radial-gradient(ellipse 46% 52% at 50% 50%, rgba(26, 18, 11, .94) 0 55%, rgba(26, 18, 11, .55) 100%);
}
/* Плёночное зерно и виньетка — общий «документальный» вид. */
body::after {
    content: ''; position: absolute; inset: 0; z-index: 3; pointer-events: none; opacity: .5; mix-blend-mode: overlay;
    background:
        url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 .5 0 0 0 0 .4 0 0 0 0 .3 0 0 0 .55 0'/%3E%3C/filter%3E%3Crect width='160' height='160' filter='url(%23n)'/%3E%3C/svg%3E"),
        radial-gradient(ellipse at center, transparent 55%, rgba(0, 0, 0, .55) 100%);
}
.collage { position: absolute; inset: 0; z-index: 0; }
.photo {
    position: absolute; width: 150px; padding: 8px 8px 22px; background: #E8D8B4; box-shadow: 0 6px 18px rgba(0, 0, 0, .55);
    opacity: .62; filter: sepia(.35) contrast(1.05);
}
.photo img { display: block; width: 100%; height: auto; }
.piece { position: absolute; fill: var(--gold); opacity: .13; }
.note { position: absolute; font: 600 .95rem/1.5 'Courier New', Courier, monospace; color: #B89A6A; opacity: .5; white-space: pre; }
main { position: relative; z-index: 2; width: 100%; max-width: 560px; text-align: center; }
.brand { margin: 0 0 28px; font-size: .78rem; letter-spacing: .42em; text-indent: .42em; text-transform: uppercase; color: var(--gold); }
.emblem { width: 76px; height: auto; display: block; margin: 0 auto 26px; }
.status { margin: 0 0 14px; font: 600 .74rem/1 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: .22em;
    text-indent: .22em; text-transform: uppercase; color: var(--muted); }
.rule { width: 56px; height: 1px; margin: 0 auto 28px; background: linear-gradient(90deg, transparent, var(--gold), transparent); }
h1 { margin: 0 0 12px; font-size: 1.7rem; line-height: 1.3; font-weight: 600; color: var(--wheat); }
.copy { margin: 0 auto; max-width: 460px; font-size: 1.02rem; line-height: 1.6; color: #CDB894; }
a.retry {
    display: inline-block; margin-top: 38px; padding: 12px 34px; border: 1px solid var(--gold); border-radius: 2px;
    font: 600 .78rem/1 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: .18em; text-transform: uppercase;
    color: var(--wheat); text-decoration: none; background: rgba(26, 18, 11, .7); transition: background .2s, color .2s;
}
a.retry:hover, a.retry:focus-visible { background: var(--gold); color: var(--bg); outline: none; }
@media (prefers-reduced-motion: no-preference) { .emblem { animation: glow 3.2s ease-in-out infinite; } }
@keyframes glow { 0%, 100% { filter: drop-shadow(0 0 0 rgba(245, 222, 179, 0)); } 50% { filter: drop-shadow(0 0 14px rgba(245, 222, 179, .28)); } }
"""

EMBLEM = (
    '<svg class="emblem" viewBox="0 0 100 130" role="img" aria-label="Pawn"><defs><linearGradient id="g" x1="0" y1="0" '
    'x2="0" y2="1"><stop offset="0" stop-color="#F5DEB3"/><stop offset="1" stop-color="#C9A265"/></linearGradient></defs>'
    f'<g fill="url(#g)">{PIECES["pawn"]}</g></svg>'
)

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' "
    "rx='14' fill='%231A120B'/%3E%3Crect x='6' y='6' width='52' height='52' rx='10' fill='none' stroke='%23D0A972' "
    "stroke-width='3'/%3E%3Ctext x='32' y='44' font-family='Georgia,serif' font-size='36' fill='%23F5DEB3' "
    "text-anchor='middle'%3E%E2%99%9E%3C/text%3E%3C/svg%3E"
)


def photo(src: str, style: str, narrow: bool = False) -> str:
    """Снимок на столе: позиция и наклон — в style; narrow — оставить и на узком экране."""
    cls = "photo narrow" if narrow else "photo"
    return f'<figure class="{cls}" style="margin:0;{style}"><img src="{src}" alt=""/></figure>'


def piece(kind: str, style: str) -> str:
    """Силуэт фигуры на фоне."""
    return f'<svg class="piece" viewBox="0 0 100 130" style="{style}" aria-hidden="true">{PIECES[kind]}</svg>'


def note(text: str, style: str) -> str:
    """Обрывок партитуры пишущей машинкой."""
    return f'<div class="note" style="{style}" aria-hidden="true">{text}</div>'


def landing_collage(photos: list[str]) -> str:
    """Ожидание: снимки по бокам, как на стене клуба; фигуры и ходы между ними."""
    spots = [  # (left/right, top %, угол)
        ("left:3%", 8, -7), ("left:13%", 52, 5), ("left:2%", 70, -4), ("right:4%", 6, 6),
        ("right:14%", 48, -6), ("right:3%", 68, 4), ("left:24%", 4, 3), ("right:25%", 78, -5),
    ]
    parts = [photo(src, f"{side};top:{top}%;transform:rotate({angle}deg)", narrow=i < 4)
             for i, (src, (side, top, angle)) in enumerate(zip(photos, spots, strict=False))]
    parts += [
        piece("king", "width:120px;left:30%;top:60%;transform:rotate(-8deg)"),
        piece("rook", "width:100px;right:32%;top:14%;transform:rotate(9deg)"),
        piece("queen", "width:130px;left:6%;top:36%;transform:rotate(-12deg)"),
        piece("bishop", "width:110px;right:7%;top:30%;transform:rotate(10deg)"),
        note("1.e4 e5 2.Nf3 Nc6\n3.Bb5 a6 4.Ba4 Nf6", "left:8%;top:90%;transform:rotate(-3deg)"),
        note("1.d4 Nf6 2.c4 e6\n3.Nc3 Bb4", "right:8%;top:90%;transform:rotate(2deg)"),
        note("Qxf7#", "left:36%;top:6%;transform:rotate(4deg);font-size:1.6rem"),
        note("O-O-O", "right:34%;top:88%;transform:rotate(-5deg);font-size:1.3rem"),
    ]
    return '<div class="collage" aria-hidden="true">' + "".join(parts) + "</div>"


def maintenance_collage(photos: list[str]) -> str:
    """Технические работы: ленты кадров сверху и снизу и бланк партии — раскладка не такая, как у страницы ожидания."""
    top = [photo(src, f"left:{5 + i * 24}%;top:-34px;transform:rotate({(-1) ** i * 3}deg)", narrow=i < 2)
           for i, src in enumerate(photos[:4])]
    bottom = [photo(src, f"left:{12 + i * 24}%;bottom:-34px;transform:rotate({(-1) ** i * -3}deg)", narrow=i < 2)
              for i, src in enumerate(photos[4:8])]
    parts = top + bottom + [
        piece("rook", "width:110px;left:4%;top:34%;transform:rotate(-6deg)"),
        piece("pawn", "width:90px;left:18%;top:62%;transform:rotate(8deg)"),
        piece("bishop", "width:110px;right:5%;top:30%;transform:rotate(7deg)"),
        piece("queen", "width:120px;right:19%;top:58%;transform:rotate(-9deg)"),
        note("White   Black\n1. e4     c5\n2. Nf3    d6\n3. d4     cxd4\n4. Nxd4   Nf6", "left:3%;top:48%;transform:rotate(-2deg)"),
        note("5. Nc3 a6\n6. Be3 e5\n7. Nb3 Be6", "right:3%;top:46%;transform:rotate(3deg)"),
    ]
    return '<div class="collage" aria-hidden="true">' + "".join(parts) + "</div>"


def narrow_css() -> str:
    """На узких экранах оставляем несколько снимков и приглушаем фон ещё сильнее."""
    return """
@media (max-width: 900px) {
    .photo:not(.narrow), .note { display: none; }
    .photo { width: 96px; padding: 5px 5px 14px; opacity: .45; }
    .piece { opacity: .09; }
    body::before { background: radial-gradient(ellipse 90% 60% at 50% 50%, rgba(26, 18, 11, .95) 0 60%, rgba(26, 18, 11, .7) 100%); }
}
"""


def page(title: str, status: str, heading: str, text: str, collage: str, retry: bool, extra_css: str = "") -> str:
    """Полный HTML страницы."""
    button = '    <a class="retry" href="/">Retry</a>\n' if retry else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<meta name="theme-color" content="#1A120B"/>
<meta name="robots" content="noindex"/>
<link rel="icon" type="image/svg+xml" href="{FAVICON}"/>
<title>{title}</title>
<style>{COMMON_CSS}{extra_css}{narrow_css()}</style>
</head>
<body>
{collage}
<main>
    <p class="brand">Regence</p>
    {EMBLEM}
    <p class="status">{status}</p>
    <div class="rule"></div>
    <h1>{heading}</h1>
    <p class="copy">{text}</p>
{button}</main>
</body>
</html>
"""


MAINTENANCE_HEADER = """<!doctype html>
<!--
  Страница «Технические работы» (502 / 503 / 504). Самодостаточный файл: без скриптов и внешних ресурсов — картинки
  (сепия-снимки мастеров из общественного достояния и CC0, ATTRIBUTION.md), силуэты и стили внутри, поэтому годится и для
  nginx, и для «Пользовательской ошибки» Cloudflare (Custom Error Rules, платные тарифы: HTML вставляется как есть).
  Скриптов нет намеренно: CSP сайта запрещает встроенные скрипты. Текст только английский (решение владельца 22.11).
  ФАЙЛ СОБИРАЕТСЯ: python -m scripts.dev.build_error_pages — правьте шаблон там, а не этот файл.
-->
"""


def main() -> None:
    """Собирает обе страницы."""
    maintenance = page(
        "Regence — technical maintenance", "Service temporarily unavailable", "Technical maintenance",
        "We are improving the service and will be back shortly. Please try again in a few minutes.",
        maintenance_collage([sepia_photo(n) for n in MAINTENANCE_PHOTOS]), retry=True,
    ).replace("<!doctype html>\n", MAINTENANCE_HEADER, 1)
    MAINTENANCE_OUT.write_text(maintenance, encoding="utf-8", newline="\n")

    landing = page(
        "Regence — coming soon", "Coming soon", "We are getting ready to launch",
        "An online chess club to play, train and learn. The doors open shortly.",
        landing_collage([sepia_photo(n) for n in LANDING_PHOTOS]), retry=False,
    )
    LANDING_OUT.parent.mkdir(parents=True, exist_ok=True)
    LANDING_OUT.write_text(
        "// Страница ожидания regence.club — ГЕНЕРИРУЕТСЯ: python -m scripts.dev.build_error_pages (не править руками).\n"
        "export const PAGE = " + _js_string(landing) + ";\n", encoding="utf-8", newline="\n")
    print(f"maintenance {len(maintenance) // 1024} KB, landing {len(landing) // 1024} KB")


def _js_string(text: str) -> str:
    """Строка JS из HTML (через JSON: экранирует кавычки и переводы строк)."""
    import json

    return json.dumps(text, ensure_ascii=False)


if __name__ == "__main__":
    main()
