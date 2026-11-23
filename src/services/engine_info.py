# --- FILE: src/services/engine_info.py ---
"""
Engine information for the "About" page (task 23.1, Stockfish licence GPL-3.0).

The GPL requires giving the user the source of exactly the version that runs on our side. The version name is taken from the
engine itself (UCI "id name", for example "Stockfish 17.1") -- so the link matches the binary in the image, not the latest
release. Stockfish releases are tagged sf_<version>; development builds link to the list of releases. The full licence
text in the image is /usr/share/common-licenses/GPL-3 and /usr/share/doc/stockfish/copyright (Debian package).

Called by GET /bots/engine (src/api/bots.py); the path to the binary is resolve_stockfish_path().
"""

import logging
import re
from functools import lru_cache

from src.services.engine_pool import get_engine_pool

logger = logging.getLogger(__name__)

# Engine source that the "source code" link on the "About" page points to.
REPOSITORY = "https://github.com/official-stockfish/Stockfish"
LICENSE = "GPL-3.0"
LICENSE_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
# Release name from UCI "id name": "Stockfish 17.1" -> the version number for the tag sf_<version>.
_RELEASE = re.compile(r"^Stockfish (\d+(?:\.\d+)*)\b")


def source_url(engine_name: str | None) -> str:
    """Source of this version: the release tag, and for development builds and unknown names -- the list of releases."""
    match = _RELEASE.match(engine_name or "")
    return f"{REPOSITORY}/tree/sf_{match.group(1)}" if match else f"{REPOSITORY}/releases"


@lru_cache(maxsize=1)
def engine_name(path: str) -> str | None:
    """The engine name from UCI (once per process lifetime). None -- the engine does not start."""
    try:
        with get_engine_pool(path).acquire() as engine:
            return str(engine.id.get("name") or "") or None
    except Exception as exc:
        logger.warning("Engine name unavailable (%s): %s", path, exc)
        return None


def describe(path: str | None) -> dict:
    """
    Engine information for the "About" page: the version name, the licence and a link to the source of exactly this version.
    """
    name = engine_name(path) if path else None
    return {
        "name": name,
        "license": LICENSE,
        "license_url": LICENSE_URL,
        "source_url": source_url(name),
        "repository": REPOSITORY,
    }
