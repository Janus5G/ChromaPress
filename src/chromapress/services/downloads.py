from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib
import os


class DownloadCancelled(RuntimeError):
    """Raised when the user cancels a download or verification."""


@dataclass(frozen=True)
class OfficialSource:
    id: str
    label: str
    distribution: str
    version: str
    architecture: str
    iso_url: str
    checksums_url: str
    expected_sha256: str | None = None
    download_headroom_bytes: int = 0


# Exact release URLs and the matching hashes published by the upstream project.
# Keeping the expected hash in the version catalogue means ChromaPress can start
# the ISO request immediately instead of waiting for a SHA256SUMS round trip.
# checksums_url remains as a fallback for catalogue entries that do not yet have
# an embedded release hash.
OFFICIAL_SOURCES = (
    OfficialSource(
        id="lubuntu-26.04.1-desktop-amd64",
        label="Lubuntu 26.04.1 LTS Desktop (amd64)",
        distribution="Lubuntu",
        version="26.04.1",
        architecture="amd64",
        iso_url="https://cdimage.ubuntu.com/lubuntu/releases/26.04/release/lubuntu-26.04.1-desktop-amd64.iso",
        checksums_url="https://cdimage.ubuntu.com/lubuntu/releases/26.04/release/SHA256SUMS",
        expected_sha256="a8038585420f2270845549c6f493e0ec98e68d4b2c49571cbe500a4b5fab3062",
        download_headroom_bytes=4 * 1024**3,
    ),
    OfficialSource(
        id="ubuntu-26.04.1-desktop-amd64",
        label="Ubuntu 26.04.1 LTS Desktop (amd64)",
        distribution="Ubuntu",
        version="26.04.1",
        architecture="amd64",
        iso_url="https://releases.ubuntu.com/26.04/ubuntu-26.04.1-desktop-amd64.iso",
        checksums_url="https://releases.ubuntu.com/26.04/SHA256SUMS",
        expected_sha256="601e30fbf5d97759367c632e2c33630665039b7e2158fd068403da3ccf1bda1f",
        download_headroom_bytes=7 * 1024**3,
    ),
)


def _cancelled(cancelled) -> bool:
    return bool(cancelled and cancelled())


def _check_cancel(cancelled) -> None:
    if _cancelled(cancelled):
        raise DownloadCancelled("Cancelled by user")


def _expected_hash(source: OfficialSource, cancelled=None) -> str:
    if source.expected_sha256:
        return source.expected_sha256.lower()

    _check_cancel(cancelled)
    text = urlopen(
        Request(source.checksums_url, headers={"User-Agent": "ChromaPress/1"}),
        timeout=15,
    ).read().decode("utf-8", "replace")
    _check_cancel(cancelled)

    filename = source.iso_url.rsplit("/", 1)[-1]
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == filename:
            return parts[0].lower()
    raise RuntimeError(f"Official SHA256 entry not found for {filename}")


def download_official(
    source: OfficialSource,
    cache_dir: Path,
    progress=None,
    status=None,
    cancelled=None,
    reserve_gb: int = 20,
) -> Path:
    """Download one pinned official ISO with resume, cancellation and SHA-256.

    A cancelled partial download is intentionally retained as ``.part`` so the
    next attempt can resume instead of starting over.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    filename = source.iso_url.rsplit("/", 1)[-1]
    final = cache_dir / filename
    part = cache_dir / (filename + ".part")

    def say(text: str) -> None:
        if status:
            status(text)

    _check_cancel(cancelled)

    if final.is_file():
        # Cached files must be verified before reuse, but a fresh download is
        # never delayed by checksum work.
        expected = _expected_hash(source, cancelled=cancelled)
        say("Verifying cached ISO…")
        if sha256_file(final, cancelled=cancelled) == expected:
            if progress:
                progress(1, 1)
            say("Verified cached ISO")
            return final
        # A stale/corrupt cache entry is never trusted.
        final.unlink(missing_ok=True)

    offset = part.stat().st_size if part.exists() else 0

    # Fail closed before any new multi-GB write. A partial download reduces the
    # remaining headroom required. No fallback path is ever selected.
    from chromapress.services.storage import require_write_capacity
    remaining = max(0, source.download_headroom_bytes - offset)
    require_write_capacity(cache_dir, reserve_gb=reserve_gb, required_bytes=remaining)
    headers = {"User-Agent": "ChromaPress/1"}
    if offset:
        headers["Range"] = f"bytes={offset}-"

    _check_cancel(cancelled)
    say(f"Connecting directly to {filename}…")
    req = Request(source.iso_url, headers=headers)
    try:
        response = urlopen(req, timeout=20)
    except HTTPError as exc:
        if exc.code == 416 and part.exists():
            response = None
        else:
            raise

    if response is not None:
        status_code = getattr(response, "status", 200)
        if offset and status_code != 206:
            part.unlink(missing_ok=True)
            offset = 0

        total = response.headers.get("Content-Length")
        total_size = int(total) + offset if total and status_code == 206 else int(total or 0)
        mode = "ab" if offset and status_code == 206 else "wb"
        written = offset

        if offset:
            say(f"Resuming download at {offset / (1024 ** 2):.1f} MiB…")
        else:
            say("Downloading from official release server…")

        if progress:
            progress(written, total_size)

        try:
            with part.open(mode) as out:
                while True:
                    _check_cancel(cancelled)
                    chunk = response.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if progress:
                        progress(written, total_size)
        finally:
            response.close()

    _check_cancel(cancelled)
    # Download is complete before checksum lookup/hash verification begins.
    say("Download complete — verifying SHA-256…")
    expected = _expected_hash(source, cancelled=cancelled)
    actual = sha256_file(part, cancelled=cancelled)
    _check_cancel(cancelled)

    if actual != expected:
        raise RuntimeError(
            f"SHA256 mismatch for {filename}: expected {expected}, got {actual}"
        )

    os.replace(part, final)
    if progress:
        progress(1, 1)
    say("Download verified")
    return final


def sha256_file(path: Path, cancelled=None) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            _check_cancel(cancelled)
            h.update(chunk)
    _check_cancel(cancelled)
    return h.hexdigest()
