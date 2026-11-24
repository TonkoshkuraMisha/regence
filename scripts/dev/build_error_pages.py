"""
Builds two service pages with a retro collage: "Technical maintenance" and the waiting page shown before launch.

What it does: takes portraits of masters from frontend/public/assets/champions (public domain and CC0 only - their
licences are recorded in ATTRIBUTION.md), turns them into small sepia photos, lays them on the background as "photos on a table" together with
piece silhouettes and scraps of score sheets, and sets large text straight over the collage (no dark veil: a shadow around
the letters keeps them readable while the photos stay visible).
It writes two files:
  * frontend/public/maintenance.html - a self-contained 502/503/504 page (nginx and Cloudflare Custom Errors);
  * ops/landing/src/page.js - the HTML of the waiting page for the regence-landing Worker (export PAGE).
The pages deliberately differ in layout: "Technical maintenance" has two strips of frames at the top and bottom and a game form, the waiting page -
photos along the sides, like on a club wall. The pages contain no scripts or external resources: images are data URIs.

    python -m scripts.dev.build_error_pages
"""
# ruff: noqa: E501  - inside CSS and data URIs, their lines are not wrapped

import base64
import io
import pathlib

from PIL import Image, ImageEnhance, ImageOps

ROOT = pathlib.Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "frontend" / "public" / "assets" / "champions"
MAINTENANCE_OUT = ROOT / "frontend" / "public" / "maintenance.html"
LANDING_OUT = ROOT / "ops" / "landing" / "src" / "page.js"

# Public domain and CC0 only (ATTRIBUTION.md, portraits section): no attribution is required on the page.
LANDING_PHOTOS = ["morphy", "Capablanca", "Alekhine", "Steinitz", "Tal", "Tarrasch", "Pillsbury", "anderssen"]
LANDING_NARROW = {0, 3, 7}  # indices of the landing photos kept on narrow screens (above and below the text)
MAINTENANCE_PHOTOS = ["philidor", "staunton", "zukertort", "Marshall", "Keres", "Rubinstein", "paulsen", "labourdonnais"]

PHOTO_SIZE = (150, 190)  # pixels: the photo is seen small, no headroom for retina screens is needed - the background is muted
SEPIA_DARK, SEPIA_LIGHT = (38, 24, 12), (236, 214, 170)


def sepia_photo(name: str) -> str:
    """A master's portrait -> a small sepia photo as a data URI (JPEG)."""
    image = Image.open(PHOTOS / f"{name}.jpg").convert("L")
    image = ImageOps.fit(image, PHOTO_SIZE, method=Image.Resampling.LANCZOS, centering=(0.5, 0.25))
    image = ImageOps.autocontrast(image, cutoff=1)
    image = ImageEnhance.Contrast(image).enhance(1.1)
    toned = ImageOps.colorize(image, black=SEPIA_DARK, white=SEPIA_LIGHT)
    buffer = io.BytesIO()
    toned.save(buffer, "JPEG", quality=58, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


# Piece silhouettes (viewBox 0 0 100 130), the fill is set by a class.
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
/* No veil under the text (owner's request 24.11): the photos and score sheets stay fully visible; the text keeps its
   contrast through a shadow that hugs the letters (--ink) instead of a dark patch. */
/* Film grain and vignette: a shared "documentary" look. */
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
main {
    --ink: 0 1px 2px rgba(0, 0, 0, .95), 0 0 10px rgba(0, 0, 0, .85), 0 0 22px rgba(0, 0, 0, .6);
    position: relative; z-index: 2; width: 100%; max-width: 900px; text-align: center; text-shadow: var(--ink);
}
.brand { margin: 0 0 30px; font-size: clamp(1rem, 1.5vw, 1.3rem); letter-spacing: .42em; text-indent: .42em; text-transform: uppercase; color: var(--gold); }
.emblem { width: clamp(84px, 7vw, 112px); height: auto; display: block; margin: 0 auto 28px; filter: drop-shadow(0 2px 8px rgba(0, 0, 0, .8)); }
.status { margin: 0 0 18px; font: 600 clamp(.95rem, 1.3vw, 1.15rem)/1.2 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: .22em;
    text-indent: .22em; text-transform: uppercase; color: #C9B08A; }
.rule { width: 80px; height: 2px; margin: 0 auto 30px; background: linear-gradient(90deg, transparent, var(--gold), transparent); }
h1 { margin: 0 0 18px; font-size: clamp(2.2rem, 4.4vw, 3.6rem); line-height: 1.15; font-weight: 600; color: var(--wheat); }
.copy { margin: 0 auto; max-width: 760px; font-size: clamp(1.2rem, 1.9vw, 1.55rem); line-height: 1.55; color: #E3CFA8; }
a.retry {
    display: inline-block; margin-top: 42px; padding: 16px 46px; border: 1px solid var(--gold); border-radius: 2px;
    font: 600 clamp(.95rem, 1.2vw, 1.1rem)/1 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; letter-spacing: .18em; text-transform: uppercase;
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
    """A photo on the table: position and tilt are in style; narrow - keep it on a narrow screen too."""
    cls = "photo narrow" if narrow else "photo"
    return f'<figure class="{cls}" style="margin:0;{style}"><img src="{src}" alt=""/></figure>'


def piece(kind: str, style: str) -> str:
    """A piece silhouette on the background."""
    return f'<svg class="piece" viewBox="0 0 100 130" style="{style}" aria-hidden="true">{PIECES[kind]}</svg>'


def note(text: str, style: str) -> str:
    """A scrap of a score sheet typed on a typewriter."""
    return f'<div class="note" style="{style}" aria-hidden="true">{text}</div>'


def landing_collage(photos: list[str]) -> str:
    """Waiting page: photos along the sides, like on a club wall; pieces and moves between them."""
    spots = [  # (left/right, top %, angle)
        ("left:3%", 8, -7), ("left:13%", 52, 5), ("left:2%", 70, -4), ("right:4%", 6, 6),
        ("right:14%", 48, -6), ("right:3%", 68, 4), ("left:24%", 4, 3), ("right:25%", 78, -5),
    ]
    # On a phone the text has no veil under it, so only photos clear of the text stay: the top corners and the bottom one.
    parts = [photo(src, f"{side};top:{top}%;transform:rotate({angle}deg)", narrow=i in LANDING_NARROW)
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
    """Technical maintenance: strips of frames at the top and bottom and a game form - a different layout from the waiting page."""
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
    """On narrow screens we keep a few photos and mute the background even more."""
    return """
@media (max-width: 900px) {
    .photo:not(.narrow), .note { display: none; }
    .photo { width: 96px; padding: 5px 5px 14px; opacity: .45; }
    .piece { opacity: .09; }
}
"""


def page(title: str, status: str, heading: str, text: str, collage: str, retry: bool, extra_css: str = "") -> str:
    """The full HTML of the page."""
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
  "Maintenance" page (502 / 503 / 504). A self-contained file: no scripts or external resources; the images
  (sepia photos of masters from the public domain and CC0, ATTRIBUTION.md), silhouettes and styles are inline, so it suits both
  nginx and a Cloudflare "Custom Error" (Custom Error Rules, paid plans: the HTML is inserted as is).
  There are no scripts on purpose: the site CSP forbids inline scripts. The text is English only (owner's decision 22.11).
  THE FILE IS GENERATED: python -m scripts.dev.build_error_pages - edit the template there, not this file.
-->
"""


def main() -> None:
    """Builds both pages."""
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
        "// Waiting page of regence.club - GENERATED: python -m scripts.dev.build_error_pages (do not edit by hand).\n"
        "export const PAGE = " + _js_string(landing) + ";\n", encoding="utf-8", newline="\n")
    print(f"maintenance {len(maintenance) // 1024} KB, landing {len(landing) // 1024} KB")


def _js_string(text: str) -> str:
    """A JS string from HTML (through JSON: escapes quotes and newlines)."""
    import json

    return json.dumps(text, ensure_ascii=False)


if __name__ == "__main__":
    main()
