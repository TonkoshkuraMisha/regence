# --- FILE: scripts/download_champions.py ---
"""
Chess player portraits from Wikimedia Commons - only with a free licence and with an author record.

For each player the lead image of his article in the English Wikipedia is taken, but only if
the file sits on Wikimedia Commons under a licence that allows use in any project (public
domain, CC0, CC BY, CC BY-SA). Files uploaded to Wikipedia locally ("fair
use") and licences with NC/ND conditions are skipped: such a player has no portrait and the
interface shows initials.

Next to the portraits a manifest frontend/src/config/portraitCredits.json is written: file, author,
licence, source link. The "About" page and the ATTRIBUTION.md section are built from it;
tests/test_assets_licensing.py checks that every portrait in the repository has an entry.

Run:  python scripts/download_champions.py            # download what is missing
         python scripts/download_champions.py --force    # re-download everything
"""

import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_CHAMPIONS_DIR = PROJECT_ROOT / "frontend" / "public" / "assets" / "champions"
SRC_CHAMPIONS_DIR = PROJECT_ROOT / "frontend" / "src" / "assets" / "champions"
CREDITS_PATH = PROJECT_ROOT / "frontend" / "src" / "config" / "portraitCredits.json"

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
THUMB_WIDTH = 500

# portrait file id -> article title in the English Wikipedia
PLAYERS: dict[str, str] = {
    "philidor": "François-André Danican Philidor",
    "labourdonnais": "Louis-Charles Mahé de La Bourdonnais",
    "staunton": "Howard Staunton",
    "anderssen": "Adolf Anderssen",
    "morphy": "Paul Morphy",
    "paulsen": "Louis Paulsen",
    "zukertort": "Johannes Zukertort",
    "Steinitz": "Wilhelm Steinitz",
    "Lasker": "Emanuel Lasker",
    "Rubinstein": "Akiba Rubinstein",
    "Capablanca": "José Raúl Capablanca",
    "Alekhine": "Alexander Alekhine",
    "Euwe": "Max Euwe",
    "Keres": "Paul Keres",
    "Botvinnik": "Mikhail Botvinnik",
    "Geller": "Efim Geller",
    "Korchnoi": "Viktor Korchnoi",
    "Smyslov": "Vasily Smyslov",
    "Tal": "Mikhail Tal",
    "Petrosian": "Tigran Petrosian",
    "Spassky": "Boris Spassky",
    "Fischer": "Bobby Fischer",
    "Karpov": "Anatoly Karpov",
    "Kasparov": "Garry Kasparov",
    "Kramnik": "Vladimir Kramnik",
    "Anand": "Viswanathan Anand",
    "Carlsen": "Magnus Carlsen",
    "Ding": "Ding Liren",
    # Second-wave masters (task 21.5)
    "Chigorin": "Mikhail Chigorin",
    "Tarrasch": "Siegbert Tarrasch",
    "Pillsbury": "Harry Nelson Pillsbury",
    "Marshall": "Frank Marshall (chess player)",
    "Nimzowitsch": "Aron Nimzowitsch",
    "Reti": "Richard Réti",
    "Tartakower": "Savielly Tartakower",
}

_TAG_RE = re.compile(r"<[^>]+>")


def is_free_license(short_name: str) -> bool:
    """The licence allows use in any project, including commercial, and modification."""
    name = short_name.strip().lower()
    tokens = set(re.split(r"[\s-]+", name))
    if not name or tokens & {"nc", "nd"}:
        return False
    return name.startswith(("public domain", "pd", "cc0", "cc by", "cc-by", "no restrictions"))


JPEG_MAGIC = bytes.fromhex("ffd8")


def as_jpeg(content: bytes) -> bytes:
    """
    Portraits are stored as .jpg, while Wikimedia Commons serves a downscaled copy in the original's format
    (PNG for a PNG). A file with the .jpg extension and PNG content is shown by browsers, but this breaks
    everything that trusts the extension. We re-encode; a transparent background is replaced with white.
    """
    if content.startswith(JPEG_MAGIC):
        return content
    from PIL import Image  # needed only for non-JPEG originals: uv sync

    image = Image.open(io.BytesIO(content)).convert("RGBA")
    background = Image.new("RGB", image.size, (255, 255, 255))
    background.paste(image, mask=image.getchannel("A"))
    buffer = io.BytesIO()
    background.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _clean(html_text: str) -> str:
    """Cleans Wikimedia Commons metadata of HTML tags and duplicated lines."""
    text = _TAG_RE.sub("", html_text or "").replace("&amp;", "&").replace("\n", " ").strip()
    # Wikimedia Commons duplicates "Unknown author" in the visible and hidden markup.
    text = text.replace("Unknown authorUnknown author", "Unknown author").replace("AnonymousUnknown author", "Unknown author")
    return re.sub(r"\s+", " ", text).rstrip("] ").strip() or "Unknown author"


def _get_json(session: requests.Session, url: str, params: dict) -> dict:
    """Makes a GET request to the Wikimedia Commons/Wikipedia API with retries on 429."""
    last_status = 0
    for _attempt in range(5):
        response = session.get(url, params=params, timeout=30)
        last_status = response.status_code
        if response.status_code == 200:
            return response.json()
        time.sleep(10)  # 429 - wait and retry
    raise RuntimeError(f"{url}: HTTP {last_status}")


def find_lead_images(session: requests.Session) -> dict[str, dict]:
    """Player id -> {file, thumb} of the article's lead image (one request for all)."""
    data = _get_json(session, WIKIPEDIA_API, {
        "action": "query", "titles": "|".join(PLAYERS.values()), "prop": "pageimages",
        "piprop": "name|thumbnail", "pithumbsize": str(THUMB_WIDTH), "pilimit": "50",
        "redirects": "1", "format": "json", "formatversion": "2",
    })["query"]
    renamed = {item["from"]: item["to"] for item in data.get("normalized", [])}
    renamed.update({item["from"]: item["to"] for item in data.get("redirects", [])})
    pages = {page["title"]: page for page in data["pages"]}

    found: dict[str, dict] = {}
    for player_id, title in PLAYERS.items():
        resolved = renamed.get(title, title)
        resolved = renamed.get(resolved, resolved)
        page = pages.get(resolved, {})
        if page.get("pageimage") and page.get("thumbnail"):
            found[player_id] = {"file": page["pageimage"], "thumb": page["thumbnail"]["source"]}
    return found


def fetch_commons_metadata(session: requests.Session, file_names: list[str]) -> dict[str, dict]:
    """File name -> {license, license_url, author, source_url}. Files not from Commons are absent from the response."""
    data = _get_json(session, COMMONS_API, {
        "action": "query", "titles": "|".join(f"File:{name}" for name in file_names), "prop": "imageinfo",
        "iiprop": "extmetadata|url", "format": "json", "formatversion": "2",
    })["query"]
    original = {item["to"]: item["from"] for item in data.get("normalized", [])}

    metadata: dict[str, dict] = {}
    for page in data["pages"]:
        if "imageinfo" not in page:
            continue
        info = page["imageinfo"][0]
        ext = info.get("extmetadata", {})
        name = original.get(page["title"], page["title"]).removeprefix("File:")
        metadata[name] = {
            "license": _clean(ext.get("LicenseShortName", {}).get("value", "")),
            "license_url": ext.get("LicenseUrl", {}).get("value", ""),
            "author": _clean(ext.get("Artist", {}).get("value", "")),
            "source_url": info.get("descriptionurl", ""),
        }
    return metadata


def main(force: bool = False) -> int:
    """Downloads free portraits of chess players and updates the licence manifest."""
    PUBLIC_CHAMPIONS_DIR.mkdir(parents=True, exist_ok=True)
    SRC_CHAMPIONS_DIR.mkdir(parents=True, exist_ok=True)
    credits: dict[str, dict] = {}
    if CREDITS_PATH.exists() and not force:
        credits = json.loads(CREDITS_PATH.read_text(encoding="utf-8"))

    session = requests.Session()
    session.headers["User-Agent"] = "portrait-downloader/2.0 (python-requests)"

    images = find_lead_images(session)
    time.sleep(2)
    metadata = fetch_commons_metadata(session, [item["file"] for item in images.values()])

    for player_id in PLAYERS:
        target = PUBLIC_CHAMPIONS_DIR / f"{player_id}.jpg"
        if player_id in credits and target.exists() and not force:
            print(f"[~] {player_id}: already present")
            continue

        image = images.get(player_id)
        meta = metadata.get(image["file"]) if image else None
        if not image or not meta or not is_free_license(meta["license"]):
            reason = "no image" if not image else "not on Commons" if not meta else meta["license"]
            print(f"[-] {player_id}: skipped ({reason}) - the interface will show initials")
            target.unlink(missing_ok=True)
            credits.pop(player_id, None)
            continue

        time.sleep(1.5)
        response = session.get(image["thumb"], timeout=30)
        if response.status_code != 200 or not response.content:
            print(f"[!] {player_id}: download failed (HTTP {response.status_code})")
            continue
        target.write_bytes(as_jpeg(response.content))
        credits[player_id] = {"file": image["file"], **meta}
        print(f"[+] {player_id}: {meta['license']} — {meta['author']}")

    for extra in PUBLIC_CHAMPIONS_DIR.glob("*.jpg"):
        if extra.stem not in credits:
            print(f"[!] {extra.name}: no source record - removed")
            extra.unlink()

    # Bot portraits are imported by the builder from src/assets, the rest are served from public.
    shutil.rmtree(SRC_CHAMPIONS_DIR)
    SRC_CHAMPIONS_DIR.mkdir(parents=True)
    for portrait in PUBLIC_CHAMPIONS_DIR.glob("*.jpg"):
        shutil.copy2(portrait, SRC_CHAMPIONS_DIR / portrait.name)

    ordered = {player_id: credits[player_id] for player_id in PLAYERS if player_id in credits}
    CREDITS_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nDone: {len(ordered)} of {len(PLAYERS)} portraits, manifest - {CREDITS_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(force="--force" in sys.argv))
