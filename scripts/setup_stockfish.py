# --- FILE: setup_stockfish.py ---
"""
Installation of the Stockfish engine into the project's bin/ folder.

Downloads the latest official release from GitHub (official-stockfish/Stockfish) and picks the build for the current
system and processor (get_target_asset_url). The engine is distributed under GPL-3.0 (ATTRIBUTION.md); it is not part of
the repository. Run: `python scripts/setup_stockfish.py`; start_dev.ps1 also calls it if the engine is not there yet.
The server finds the engine itself: bin/, PATH, standard Linux paths (src/services/bots/base.resolve_stockfish_path).
"""

import io
import os
import platform
import shutil
import stat
import tarfile
import zipfile

import chess.engine
import requests

GITHUB_RELEASE_API = "https://api.github.com/repos/official-stockfish/Stockfish/releases/latest"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")


def get_target_asset_url(assets: list[dict]) -> tuple[str, str]:
    """Picks the optimal Stockfish binary for the current OS (including universal builds of SF 19+)."""
    sys_name = platform.system().lower()

    if sys_name == "windows":
        preferred = [
            "windows-x86-64-universal.zip",
            "windows-x86-64-avx2.zip",
            "windows-x86-64-sse41-popcnt.zip",
            "windows-x86-64.zip",
        ]
    elif sys_name == "linux":
        preferred = [
            "linux-x86-64-universal.tar.gz",
            "linux-x86-64-universal.tar",
            "ubuntu-x86-64-avx2.tar",
            "ubuntu-x86-64-sse41-popcnt.tar",
            "ubuntu-x86-64.tar",
        ]
    else:
        preferred = [
            "macos-universal.tar.gz",
            "macos-m1-apple-silicon.tar",
            "macos-x86-64-avx2.tar",
        ]

    for suffix in preferred:
        for asset in assets:
            name = asset.get("name", "")
            if suffix in name:
                return name, asset["browser_download_url"]

    # Fallback: any x86-64 archive for the required OS
    for asset in assets:
        name = asset.get("name", "").lower()
        if sys_name == "windows" and "windows" in name and "x86-64" in name and name.endswith(".zip"):
            return asset["name"], asset["browser_download_url"]
        if sys_name == "linux" and ("linux" in name or "ubuntu" in name) and "x86-64" in name:
            return asset["name"], asset["browser_download_url"]

    available = [a.get("name", "") for a in assets]
    raise RuntimeError(f"No suitable Stockfish archive found for OS '{sys_name}'. Available: {available}")


def download_and_install_stockfish() -> str:
    """Downloads and installs the official Stockfish binary for the current OS."""
    os.makedirs(BIN_DIR, exist_ok=True)
    is_windows = platform.system().lower() == "windows"
    target_filename = "stockfish.exe" if is_windows else "stockfish"
    target_path = os.path.join(BIN_DIR, target_filename)

    if os.path.exists(target_path) and os.path.getsize(target_path) > 1_000_000:
        print(f"[~] Stockfish binary already installed: {target_path}")
        return target_path

    print("[1/3] Requesting the latest Stockfish release from GitHub...")
    headers = {"User-Agent": "Regence-Setup/1.0"}
    resp = requests.get(GITHUB_RELEASE_API, headers=headers, timeout=20)
    resp.raise_for_status()
    release_data = resp.json()
    tag_name = release_data.get("tag_name", "latest")

    asset_name, download_url = get_target_asset_url(release_data.get("assets", []))
    print(f"[2/3] Downloading {asset_name} (version {tag_name})...")

    archive_resp = requests.get(download_url, headers=headers, stream=True, timeout=180)
    archive_resp.raise_for_status()
    archive_bytes = io.BytesIO(archive_resp.content)

    print(f"[3/3] Extracting the engine to {target_path}...")
    extracted = False

    if asset_name.endswith(".zip"):
        with zipfile.ZipFile(archive_bytes) as zf:
            # Take the largest .exe file with the word stockfish (or avx2/universal), ignoring small wrappers
            exe_members = [
                m for m in zf.infolist()
                if not m.is_dir() and m.filename.lower().endswith(".exe") and "stockfish" in m.filename.lower()
            ]
            exe_members.sort(key=lambda m: m.file_size, reverse=True)
            if exe_members:
                best_member = exe_members[0]
                with zf.open(best_member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted = True
    elif asset_name.endswith((".tar", ".tar.gz", ".tgz")):
        with tarfile.open(fileobj=archive_bytes, mode="r:*") as tf:
            bin_members = [
                m for m in tf.getmembers()
                if m.isfile()
                   and "stockfish" in os.path.basename(m.name).lower()
                   and not m.name.lower().endswith((".txt", ".md", ".1", ".cpp", ".h", ".sh"))
            ]
            bin_members.sort(key=lambda m: m.size, reverse=True)
            if bin_members:
                src = tf.extractfile(bin_members[0])
                if src:
                    with src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    os.chmod(target_path, os.stat(target_path).st_mode | stat.S_IEXEC)
                    extracted = True

    if not extracted:
        raise RuntimeError("Could not find the Stockfish executable inside the archive.")

    with chess.engine.SimpleEngine.popen_uci(target_path) as engine:
        engine_name = engine.id.get("name", "Stockfish")
        print(f"[+] Success! The engine is ready: {engine_name} -> {target_path}")

    return target_path


if __name__ == "__main__":
    download_and_install_stockfish()
