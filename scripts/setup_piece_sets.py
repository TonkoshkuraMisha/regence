# --- FILE: scripts/setup_piece_sets.py ---
"""
Downloads piece sets into frontend/public/assets/pieces.

The source is the lichess repository (lila), but only the sets that its COPYING.md classes
as free and usable in any project, including a commercial one, are taken. Sets with the
"non-commercial use" condition (CC BY-NC-SA, "free for personal non commercial use")
and sets without a stated licence are not added here.

When adding a set: check the licence at https://github.com/lichess-org/lila/blob/master/COPYING.md,
add it to PIECE_SETS below, to frontend/src/config/boardAppearance.ts and to ATTRIBUTION.md -
tests/test_assets_licensing.py checks that all three lists match.
"""

import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIECES_ROOT = PROJECT_ROOT / "frontend" / "public" / "assets" / "pieces"

PIECE_CODES = ["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK"]

LILA_PIECE_URL = "https://raw.githubusercontent.com/lichess-org/lila/master/public/piece/{name}/{code}.svg"

# Set folder -> (author, licence). The single source of truth about what lies in pieces/.
PIECE_SETS: dict[str, tuple[str, str]] = {
    "merida": ("Armando Hernandez Marroquin", "GPL-2.0-or-later"),
    "cburnett": ("Colin M.L. Burnett", "GPL-2.0-or-later"),
    "chessnut": ("Alexis Luengas", "Apache-2.0"),
    "fantasy": ("Maurizio Monge", "MIT"),
    "rhosgfx": ("RhosGFX", "CC0-1.0"),
    # Task 18.2: audit of lila's COPYING.md (15.11.2026) - only licences without "NC".
    "mpchess": ("Maxime Chupin", "GPL-3.0-or-later"),
    "celtic": ("Maurizio Monge", "MIT"),
    "spatial": ("Maurizio Monge", "MIT"),
    "papercut": ("Nikolay Anzarov", "CC-BY-4.0"),
    "totoy": ("Kosal Sen", "CC-BY-4.0"),
    "pirouetti": ("pirouetti", "AGPL-3.0-or-later"),
    "pixel": ("therealqtpi", "AGPL-3.0-or-later"),
    "firi": ("James Faure", "CC-BY-4.0"),
    "shapes": ("flugsio", "CC-BY-SA-4.0"),
    "letter": ("usolando", "AGPL-3.0-or-later"),
}

# The project's own derivative of merida (white/dark outline) - inherits its licence.
OUTLINE_SET = "outline"
OUTLINE_SOURCE = "merida"
DERIVED_SETS: dict[str, tuple[str, str]] = {
    OUTLINE_SET: ("regence, based on Merida (Armando Hernandez Marroquin)", "GPL-2.0-or-later"),
}

# The project's own sets (task 18.2): drawn by its own scripts, not downloaded.
OWN_SETS: dict[str, tuple[str, str]] = {
    "lewis": ("regence, inspired by the 12th-century Lewis chessmen (scripts/build_lewis_pieces.py)", "CC0-1.0"),
}


def make_outlined_svg(base_svg: str, code: str) -> str:
    """Adds a contrasting outline filter to the SVG pieces for the outline set."""
    is_black = code.startswith("b")
    halo_color = "#FFFFFF" if is_black else "#111827"
    filter_id = f"outline_halo_{code}"

    halo_def = (
        f'<defs><filter id="{filter_id}" x="-12%" y="-12%" width="124%" height="124%">'
        f'<feMorphology in="SourceAlpha" operator="dilate" radius="1.15" result="dilated"/>'
        f'<feFlood flood-color="{halo_color}" flood-opacity="0.98" result="flood"/>'
        f'<feComposite in="flood" in2="dilated" operator="in" result="outline"/>'
        f'<feMerge><feMergeNode in="outline"/><feMergeNode in="SourceGraphic"/></feMerge>'
        f'</filter></defs>'
    )

    idx = base_svg.find(">")
    if idx == -1 or "</svg>" not in base_svg:
        return base_svg

    header = base_svg[: idx + 1]
    body = base_svg[idx + 1:].replace("</svg>", "")
    return f'{header}{halo_def}<g filter="url(#{filter_id})">{body}</g></svg>\n'


def download_svg(url: str) -> str | None:
    """Downloads one piece SVG file by URL with an integrity check."""
    req = urllib.request.Request(url, headers={"User-Agent": "piece-set-setup/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                text = resp.read().decode("utf-8", errors="ignore")
                if "<svg" in text:
                    return text
    except Exception as exc:
        print(f"[!] Failed to download {url}: {exc}")
    return None


def setup_all_piece_sets() -> None:
    """Downloads the free piece sets and builds the derived outlined set."""
    PIECES_ROOT.mkdir(parents=True, exist_ok=True)

    for set_name in PIECE_SETS:
        set_dir = PIECES_ROOT / set_name
        set_dir.mkdir(parents=True, exist_ok=True)
        ready = 0
        for code in PIECE_CODES:
            target_file = set_dir / f"{code}.svg"
            if target_file.exists() and target_file.stat().st_size > 200:
                ready += 1
                continue
            svg_content = download_svg(LILA_PIECE_URL.format(name=set_name, code=code))
            if svg_content:
                target_file.write_text(svg_content, encoding="utf-8")
                ready += 1
        print(f"[+] Set '{set_name}' is ready ({ready}/12 pieces)")

    outline_dir = PIECES_ROOT / OUTLINE_SET
    outline_dir.mkdir(parents=True, exist_ok=True)
    for code in PIECE_CODES:
        src_file = PIECES_ROOT / OUTLINE_SOURCE / f"{code}.svg"
        if src_file.exists():
            outlined = make_outlined_svg(src_file.read_text(encoding="utf-8"), code)
            (outline_dir / f"{code}.svg").write_text(outlined, encoding="utf-8")
    print(f"[+] Set '{OUTLINE_SET}' built from '{OUTLINE_SOURCE}'")


if __name__ == "__main__":
    setup_all_piece_sets()
