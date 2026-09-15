from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from chromapress.models import ChangeItem
from chromapress.services.part7 import validate_build_plan_payload

_SUPPORTED_KINDS = {"package_repository", "package_remove", "package_replace"}
_SAFE_PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+:~-]{0,127}$")


class BuildError(RuntimeError):
    pass


def _emit_build_progress(
    progress_path: Path | None,
    percent: int,
    phase: str,
    detail: str = "",
) -> None:
    # Percentages represent completed build phases, not elapsed time.
    # 100 is emitted only after all static post-build checks have passed.
    if progress_path is None:
        return
    value = max(0, min(100, int(percent)))
    payload = {
        "percent": value,
        "phase": str(phase),
        "detail": str(detail),
    }
    temp = progress_path.with_name(progress_path.name + ".tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, progress_path)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass


def _run(
    args: list[str],
    *,
    timeout: int = 3600,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        args,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
        env=env,
    )
    if cp.returncode != 0:
        detail = (cp.stderr or cp.stdout or "").strip()
        raise BuildError(detail or f"Command failed ({cp.returncode}): {' '.join(args)}")
    return cp


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise BuildError(f"Required build tool is missing: {name}")
    return path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_package(value: str, *, label: str) -> str:
    value = str(value or "").strip()
    if not _SAFE_PACKAGE.fullmatch(value):
        raise BuildError(f"Unsafe or unsupported {label}: {value!r}")
    return value


def _production_change(change: dict[str, Any]) -> bool:
    payload = change.get("payload") if isinstance(change, dict) else None
    return isinstance(payload, dict) and payload.get("config_type") == "part7_production_build_plan"


def _validate_execution_plan(
    plan: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], Path, Path, Path]:
    if not isinstance(plan, dict) or plan.get("schema") != "chromapress-build-execution-v1":
        raise BuildError("Build execution schema is invalid.")

    production = plan.get("production")
    changes = plan.get("changes")
    if not isinstance(production, dict) or not isinstance(changes, list):
        raise BuildError("Build execution plan must contain production metadata and staged changes.")

    ok, message = validate_build_plan_payload(production)
    if not ok:
        raise BuildError(message)

    if production.get("expert_hooks"):
        raise BuildError("Expert hooks are not enabled in the first verified ISO mutation gate.")

    if any(_production_change(c) for c in changes):
        raise BuildError("Execution changes must not contain the production-plan change itself.")

    expected_count = int(production.get("change_count", -1))
    if len(changes) != expected_count:
        raise BuildError(
            f"Staged change count changed after production preflight: expected {expected_count}, got {len(changes)}."
        )

    parsed: list[ChangeItem] = []
    for raw in changes:
        if not isinstance(raw, dict):
            raise BuildError("Malformed staged change.")
        parsed.append(ChangeItem.from_dict(raw))

    unsupported = sorted({c.kind.value for c in parsed if c.kind.value not in _SUPPORTED_KINDS})
    if unsupported:
        raise BuildError(
            "Build blocked: the first verified mutation gate supports only APT repository add/remove/replace. "
            "Unsupported staged kind(s): " + ", ".join(unsupported)
        )

    source = Path(str(production.get("source_path") or ""))
    output_dir = Path(str(production.get("output_dir") or ""))
    output = output_dir / str(production.get("output_name") or "")
    workspace = Path(str(plan.get("workspace_dir") or ""))

    if not source.is_absolute() or not source.is_file():
        raise BuildError(f"Source ISO does not exist: {source}")
    if not output_dir.is_absolute():
        raise BuildError("Output directory is not absolute.")
    if not workspace.is_absolute():
        raise BuildError("Build workspace is not absolute.")
    if source.resolve() == output.resolve():
        raise BuildError("Output ISO may not replace the source ISO.")
    if output.exists():
        raise BuildError(f"Output already exists; implicit overwrite is forbidden: {output}")

    expected_sha = str(production.get("source_sha256") or "").lower()
    actual_sha = _sha256(source)
    if actual_sha != expected_sha:
        raise BuildError(
            f"Source ISO SHA-256 mismatch. Expected {expected_sha}, got {actual_sha}. Build stopped before mutation."
        )

    for change in parsed:
        payload = dict(change.payload or {})
        manager = str(payload.get("manager") or "apt").strip().lower()
        if change.kind.value == "package_repository":
            if manager not in {"", "apt", "repository"}:
                raise BuildError(
                    f"Build blocked: package manager {manager!r} is not supported by the first apply gate."
                )
            _safe_package(payload.get("package", ""), label="repository package")
        elif change.kind.value == "package_remove":
            package = str(payload.get("package") or "").strip()
            desktop = str(payload.get("desktop_file") or "").strip()
            if package:
                _safe_package(package, label="remove package")
            elif not desktop:
                raise BuildError("Remove change has neither an exact package nor a desktop-file locator.")
        elif change.kind.value == "package_replace":
            _safe_package(payload.get("replacement_package", ""), label="replacement package")
            package = str(payload.get("package") or "").strip()
            desktop = str(payload.get("desktop_file") or "").strip()
            if package:
                _safe_package(package, label="replaced package")
            elif not desktop:
                raise BuildError("Replace change has neither an exact package nor a desktop-file locator.")

    return production, changes, source, output, workspace


def _iso_files(path: Path) -> list[str]:
    listing = _run(["xorriso", "-indev", str(path), "-find", "/", "-type", "f"], timeout=300)
    files: list[str] = []
    combined = (listing.stdout or "") + "\n" + (listing.stderr or "")
    for raw in combined.splitlines():
        item = raw.strip().strip("'\"")
        if item.startswith("/"):
            files.append(item)
    return sorted(set(files))


def _rootfs_layers(files: list[str]) -> list[str]:
    """Match the source-analysis ordering: Casper/live base -> standard -> live."""
    candidates = [
        x
        for x in files
        if x.lower().endswith(".squashfs")
        and any(part in x.lower() for part in ("/casper/", "/live/", "/liveos/"))
    ]

    def order(member: str) -> tuple[int, int, str]:
        name = PurePosixPath(member).name.lower()
        if name == "minimal.squashfs":
            rank = 10
        elif name == "minimal.standard.squashfs":
            rank = 20
        elif name == "minimal.standard.live.squashfs":
            rank = 30
        elif name == "filesystem.squashfs":
            rank = 40
        else:
            rank = 50
        return (rank, name.count("."), name)

    return sorted(candidates, key=order)


def _extract_iso_member(iso: Path, member: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _run(
        ["xorriso", "-indev", str(iso), "-osirrox", "on", "-extract", member, str(target)],
        timeout=3600,
    )


def _compression_of(squashfs: Path) -> str:
    text = _run(["unsquashfs", "-s", str(squashfs)], timeout=120).stdout
    m = re.search(r"(?im)^Compression\s+([A-Za-z0-9_-]+)\s*$", text)
    if not m:
        raise BuildError("Could not determine source SquashFS compression.")
    return m.group(1).lower()


def _sibling_metadata(member: str, suffix: str) -> str:
    p = PurePosixPath(member)
    name = p.name
    if not name.lower().endswith(".squashfs"):
        raise BuildError(f"Unexpected rootfs member name: {member}")
    stem = name[: -len(".squashfs")]
    return str(p.with_name(stem + suffix))


def _parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    if not path.is_file():
        return entries
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = raw.strip().split()
        if len(parts) >= 2:
            entries[parts[0]] = parts[1]
    return entries


def _installed_manifest_entries(rootfs: Path) -> list[tuple[str, str]]:
    cp = _run(
        [
            "chroot",
            str(rootfs),
            "/usr/bin/dpkg-query",
            "-W",
            "-f=${binary:Package}\\t${Version}\\t${db:Status-Abbrev}\\n",
        ],
        timeout=300,
    )
    entries: list[tuple[str, str]] = []
    for raw in cp.stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        package, version, status = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if package and version and status.startswith("ii"):
            entries.append((package, version))
    entries.sort(key=lambda item: item[0].casefold())
    return entries


def _write_manifest_entries(entries: list[tuple[str, str]], target: Path) -> None:
    target.write_text(
        "".join(f"{package} {version}\n" for package, version in entries),
        encoding="utf-8",
        newline="\n",
    )


def _write_delta_manifest(
    lower_full: Path,
    final_entries: list[tuple[str, str]],
    target: Path,
) -> None:
    lower = _parse_manifest(lower_full)
    delta = [(package, version) for package, version in final_entries if lower.get(package) != version]
    _write_manifest_entries(delta, target)


def _resolve_package_from_desktop(rootfs: Path, desktop_file: str) -> str:
    desktop_file = str(desktop_file or "").strip()
    if not desktop_file:
        raise BuildError("Desktop-file locator is empty.")
    candidates = [desktop_file]
    if not desktop_file.startswith("/"):
        candidates.extend(
            [
                f"/usr/share/applications/{desktop_file}",
                f"/usr/local/share/applications/{desktop_file}",
            ]
        )
    for candidate in candidates:
        cp = subprocess.run(
            ["chroot", str(rootfs), "/usr/bin/dpkg-query", "-S", candidate],
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if cp.returncode == 0 and ":" in cp.stdout:
            package = cp.stdout.split(":", 1)[0].strip()
            if package:
                return _safe_package(package, label="resolved package")
    raise BuildError(f"Could not resolve package ownership for desktop file: {desktop_file}")


def _mount_chroot(rootfs: Path) -> list[Path]:
    mounted: list[Path] = []
    specs = [
        (["mount", "--bind", "/dev", str(rootfs / "dev")], rootfs / "dev"),
        (["mount", "--bind", "/dev/pts", str(rootfs / "dev/pts")], rootfs / "dev/pts"),
        (["mount", "-t", "proc", "proc", str(rootfs / "proc")], rootfs / "proc"),
        (["mount", "-t", "sysfs", "sysfs", str(rootfs / "sys")], rootfs / "sys"),
        (["mount", "--bind", "/run", str(rootfs / "run")], rootfs / "run"),
    ]
    for _, target in specs:
        target.mkdir(parents=True, exist_ok=True)
    try:
        for args, target in specs:
            _run(args, timeout=60)
            mounted.append(target)
    except Exception:
        for target in reversed(mounted):
            subprocess.run(["umount", "-l", str(target)], capture_output=True, text=True, check=False)
        raise
    return mounted


def _restore_resolver(rootfs: Path, saved: tuple[str, bytes | str | None]) -> None:
    kind, data = saved
    target = rootfs / "etc" / "resolv.conf"
    try:
        if target.exists() or target.is_symlink():
            target.unlink()
    except OSError:
        pass
    if kind == "symlink" and isinstance(data, str):
        target.symlink_to(data)
    elif kind == "file" and isinstance(data, bytes):
        target.write_bytes(data)


def _prepare_resolver(rootfs: Path) -> tuple[str, bytes | str | None]:
    target = rootfs / "etc" / "resolv.conf"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        saved: tuple[str, bytes | str | None] = ("symlink", os.readlink(target))
        target.unlink()
    elif target.exists():
        saved = ("file", target.read_bytes())
        target.unlink()
    else:
        saved = ("missing", None)
    target.write_bytes(Path("/etc/resolv.conf").read_bytes())
    return saved



_CDROM_APT_URI = re.compile(r"file:/{1,3}cdrom(?:/|\b)", re.IGNORECASE)


def _filter_legacy_apt_source(text: str) -> str:
    """Remove active file:/cdrom entries from a temporary .list copy only."""
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if not stripped.startswith("#") and _CDROM_APT_URI.search(line):
            continue
        kept.append(line)
    return "".join(kept)


def _filter_deb822_apt_source(text: str) -> str:
    """Remove deb822 stanzas whose URIs field points at the live ISO CD-ROM."""
    stanzas = re.split(r"\n[ \t]*\n", text)
    kept: list[str] = []
    for stanza in stanzas:
        if not stanza.strip():
            continue
        has_uris = re.search(r"(?im)^[ \t]*URIs[ \t]*:", stanza) is not None
        if has_uris and _CDROM_APT_URI.search(stanza):
            continue
        kept.append(stanza.rstrip())
    return ("\n\n".join(kept) + "\n") if kept else ""


def _prepare_filtered_apt_sources(rootfs: Path) -> tuple[str, str, Path, list[str]]:
    """Create a temporary APT view excluding live-media file:/cdrom sources."""
    apt_dir = rootfs / "etc" / "apt"
    sourceparts = apt_dir / "sources.list.d"
    temp_name = f".chromapress-build-sources-{uuid.uuid4().hex}"
    temp_dir = apt_dir / temp_name
    temp_parts = temp_dir / "sources.list.d"
    temp_parts.mkdir(parents=True, exist_ok=False)
    disabled: list[str] = []

    main = apt_dir / "sources.list"
    temp_main = temp_dir / "sources.list"
    if main.is_file():
        text = main.read_text(encoding="utf-8", errors="replace")
        filtered = _filter_legacy_apt_source(text)
        if filtered != text:
            disabled.append("/etc/apt/sources.list")
        temp_main.write_text(filtered, encoding="utf-8", newline="\n")
    else:
        temp_main.write_text("", encoding="utf-8", newline="\n")

    if sourceparts.is_dir():
        for source in sorted(sourceparts.iterdir(), key=lambda p: p.name.casefold()):
            if not source.is_file() or source.suffix.lower() not in {".list", ".sources"}:
                continue
            text = source.read_text(encoding="utf-8", errors="replace")
            filtered = (_filter_deb822_apt_source(text)
                        if source.suffix.lower() == ".sources"
                        else _filter_legacy_apt_source(text))
            if filtered != text:
                disabled.append(f"/etc/apt/sources.list.d/{source.name}")
            if filtered.strip():
                target = temp_parts / source.name
                target.write_text(filtered, encoding="utf-8", newline="\n")
                try:
                    shutil.copystat(source, target, follow_symlinks=False)
                except OSError:
                    pass

    if not any(temp_parts.iterdir()) and not temp_main.read_text(encoding="utf-8", errors="replace").strip():
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise BuildError("Build APT source filtering removed every package source; at least one non-CD-ROM repository is required.")

    return (f"{temp_name}/sources.list", f"{temp_name}/sources.list.d", temp_dir, disabled)


def _cleanup_filtered_apt_sources(temp_dir: Path | None) -> None:
    if temp_dir is not None:
        shutil.rmtree(temp_dir, ignore_errors=True)



def _apply_packages(
    rootfs: Path,
    raw_changes: list[dict[str, Any]],
    progress_path: Path | None = None,
) -> tuple[list[str], list[str], list[tuple[str, str]]]:
    adds: list[str] = []
    removes: list[str] = []
    replacements: list[tuple[str, str]] = []

    parsed = [ChangeItem.from_dict(raw) for raw in raw_changes]
    for change in parsed:
        payload = dict(change.payload or {})
        if change.kind.value == "package_repository":
            adds.append(_safe_package(payload.get("package", ""), label="repository package"))
        elif change.kind.value == "package_remove":
            package = str(payload.get("package") or "").strip()
            if not package:
                package = _resolve_package_from_desktop(
                    rootfs,
                    str(payload.get("desktop_file") or ""),
                )
            removes.append(_safe_package(package, label="remove package"))
        elif change.kind.value == "package_replace":
            old = str(payload.get("package") or "").strip()
            if not old:
                old = _resolve_package_from_desktop(
                    rootfs,
                    str(payload.get("desktop_file") or ""),
                )
            new = _safe_package(payload.get("replacement_package", ""), label="replacement package")
            replacements.append((_safe_package(old, label="replaced package"), new))

    adds = list(dict.fromkeys(adds))
    removes = list(dict.fromkeys(removes))
    replacements = list(dict.fromkeys(replacements))

    policy = rootfs / "usr" / "sbin" / "policy-rc.d"
    policy.parent.mkdir(parents=True, exist_ok=True)
    policy_saved = policy.read_bytes() if policy.exists() and not policy.is_symlink() else None
    policy_was_symlink = policy.is_symlink()
    policy_link = os.readlink(policy) if policy_was_symlink else None
    if policy.exists() or policy.is_symlink():
        policy.unlink()
    policy.write_text("#!/bin/sh\nexit 101\n", encoding="utf-8")
    policy.chmod(0o755)

    resolver_saved = _prepare_resolver(rootfs)
    mounted: list[Path] = []

    apt_sourcelist: str | None = None
    apt_sourceparts: str | None = None
    apt_source_temp: Path | None = None
    disabled_build_sources: list[str] = []

    def chroot_apt(*args: str, timeout: int = 3600) -> None:
        if not apt_sourcelist or not apt_sourceparts:
            raise BuildError("Temporary build APT source view was not prepared.")
        _run(
            [
                "chroot",
                str(rootfs),
                "/usr/bin/env",
                "DEBIAN_FRONTEND=noninteractive",
                "/usr/bin/apt-get",
                "-o",
                f"Dir::Etc::sourcelist={apt_sourcelist}",
                "-o",
                f"Dir::Etc::sourceparts={apt_sourceparts}",
                *args,
            ],
            timeout=timeout,
        )

    try:
        _emit_build_progress(progress_path, 38, "Preparing package environment")
        mounted = _mount_chroot(rootfs)
        (
            apt_sourcelist,
            apt_sourceparts,
            apt_source_temp,
            disabled_build_sources,
        ) = _prepare_filtered_apt_sources(rootfs)

        _emit_build_progress(progress_path, 43, "Refreshing package indexes")
        chroot_apt("update", timeout=1800)

        install_set = list(dict.fromkeys(adds + [new for _, new in replacements]))
        remove_set = list(dict.fromkeys(removes + [old for old, _ in replacements]))

        _emit_build_progress(progress_path, 50, "Validating package changes")
        if install_set:
            chroot_apt("-s", "install", *install_set, timeout=1800)
        if remove_set:
            chroot_apt("-s", "remove", *remove_set, timeout=1800)

        _emit_build_progress(progress_path, 55, "Applying package changes")
        if install_set:
            chroot_apt("-y", "--no-install-recommends", "install", *install_set, timeout=7200)
        if remove_set:
            chroot_apt("-y", "remove", *remove_set, timeout=7200)

        _emit_build_progress(progress_path, 65, "Auditing package database")
        audit = subprocess.run(
            ["chroot", str(rootfs), "/usr/bin/dpkg", "--audit"],
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
        if audit.returncode != 0 or audit.stdout.strip():
            raise BuildError((audit.stderr or audit.stdout or "dpkg audit failed").strip())

        _emit_build_progress(progress_path, 68, "Package changes verified")

        # Do not ship downloaded package archives.
        subprocess.run(
            ["chroot", str(rootfs), "/usr/bin/apt-get", "clean"],
            text=True,
            capture_output=True,
            check=False,
            timeout=300,
        )
    finally:
        _cleanup_filtered_apt_sources(apt_source_temp)
        for target in reversed(mounted):
            subprocess.run(["umount", "-l", str(target)], capture_output=True, text=True, check=False)
        _restore_resolver(rootfs, resolver_saved)
        try:
            if policy.exists() or policy.is_symlink():
                policy.unlink()
        except OSError:
            pass
        if policy_was_symlink and isinstance(policy_link, str):
            policy.symlink_to(policy_link)
        elif policy_saved is not None:
            policy.write_bytes(policy_saved)

    return adds, removes, replacements


def _rootfs_size_bytes(rootfs: Path) -> int:
    cp = _run(["du", "-sx", "--block-size=1", str(rootfs)], timeout=300)
    return int(cp.stdout.strip().split()[0])


def _make_linux_semantic_workspace(
    workspace_dir: Path,
    required_bytes: int,
) -> tuple[Path, Path | None, Path | None]:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    is_drvfs = str(workspace_dir).startswith("/mnt/")
    if not is_drvfs:
        work = workspace_dir / f"chromapress-build-{uuid.uuid4().hex[:12]}"
        work.mkdir(parents=True, exist_ok=False)
        return work, None, None

    _require_tool("mkfs.ext4")
    _require_tool("truncate")
    image_size = max(8 * 1024**3, required_bytes)
    free = shutil.disk_usage(workspace_dir).free
    if free < image_size + 2 * 1024**3:
        raise BuildError(
            f"Insufficient workspace capacity. Need about {image_size / 1024**3:.1f} GiB plus 2 GiB headroom."
        )

    image = workspace_dir / f".chromapress-build-{uuid.uuid4().hex[:12]}.ext4"
    _run(["truncate", "-s", str(image_size), str(image)], timeout=60)
    _run(["mkfs.ext4", "-F", "-q", str(image)], timeout=600)

    mountpoint = Path(tempfile.mkdtemp(prefix="chromapress-build-mnt-"))
    try:
        _run(["mount", "-o", "loop", str(image), str(mountpoint)], timeout=120)
    except Exception:
        shutil.rmtree(mountpoint, ignore_errors=True)
        image.unlink(missing_ok=True)
        raise
    return mountpoint, image, mountpoint


def _cleanup_linux_semantic_workspace(
    work: Path,
    image: Path | None,
    mountpoint: Path | None,
) -> None:
    if image is not None and mountpoint is not None:
        subprocess.run(["umount", "-l", str(mountpoint)], capture_output=True, text=True, check=False)
        shutil.rmtree(mountpoint, ignore_errors=True)
        image.unlink(missing_ok=True)
    else:
        shutil.rmtree(work, ignore_errors=True)


def _prepare_layered_rootfs(
    source: Path,
    work: Path,
    layers: list[str],
) -> tuple[Path, Path, str, list[Path]]:
    """Return (merged_rootfs, repack_source, top_compression, mounts_to_cleanup).

    For a layered Casper image, the original top SquashFS is extracted into a
    writable OverlayFS upperdir while all lower layers remain loop-mounted read-only.
    APT therefore sees the same merged rootfs that the live image sees, and package
    removals become real OverlayFS whiteouts in the rebuilt top layer.
    """
    images_dir = work / "layer-images"
    images_dir.mkdir(parents=True, exist_ok=True)

    extracted: list[Path] = []
    for index, member in enumerate(layers):
        target = images_dir / f"{index:02d}-{PurePosixPath(member).name}"
        _extract_iso_member(source, member, target)
        extracted.append(target)

    top_image = extracted[-1]
    top_compression = _compression_of(top_image)

    if len(layers) == 1:
        rootfs = work / "rootfs"
        _run(["unsquashfs", "-d", str(rootfs), str(top_image)], timeout=7200)
        return rootfs, rootfs, top_compression, []

    upperdir = work / "overlay-upper"
    overlay_work = work / "overlay-work"
    merged = work / "merged-rootfs"
    lower_mount_root = work / "lower-mounts"

    overlay_work.mkdir(parents=True, exist_ok=True)
    merged.mkdir(parents=True, exist_ok=True)
    lower_mount_root.mkdir(parents=True, exist_ok=True)

    # The top source layer becomes the writable upperdir, preserving any existing
    # top-layer files, whiteouts and xattrs before ChromaPress applies new changes.
    _run(["unsquashfs", "-d", str(upperdir), str(top_image)], timeout=7200)

    mounted: list[Path] = []
    try:
        lower_mounts: list[Path] = []
        for index, image_path in enumerate(extracted[:-1]):
            target = lower_mount_root / f"{index:02d}"
            target.mkdir(parents=True, exist_ok=True)
            _run(["mount", "-o", "loop,ro", str(image_path), str(target)], timeout=120)
            mounted.append(target)
            lower_mounts.append(target)

        # OverlayFS expects the highest-priority lowerdir first.
        lowerdir = ":".join(str(path) for path in reversed(lower_mounts))
        opts = f"lowerdir={lowerdir},upperdir={upperdir},workdir={overlay_work}"
        _run(["mount", "-t", "overlay", "overlay", "-o", opts, str(merged)], timeout=120)
        mounted.append(merged)
    except Exception:
        for target in reversed(mounted):
            subprocess.run(["umount", "-l", str(target)], capture_output=True, text=True, check=False)
        raise

    return merged, upperdir, top_compression, mounted


def _unmount_layered_rootfs(mounted: list[Path]) -> None:
    for target in reversed(mounted):
        subprocess.run(["umount", "-l", str(target)], capture_output=True, text=True, check=False)


def build_iso_from_plan(plan_path: Path) -> dict[str, Any]:
    if os.name == "nt":
        raise BuildError("The Linux ISO mutation engine must run inside WSL/Linux.")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and geteuid() != 0:
        raise BuildError("ISO build requires the isolated Linux engine to run as root.")

    for tool in (
        "xorriso",
        "unsquashfs",
        "mksquashfs",
        "chroot",
        "mount",
        "umount",
        "du",
    ):
        _require_tool(tool)

    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    progress_raw = str(plan.get("progress_path") or "").strip()
    progress_path = Path(progress_raw) if progress_raw else None
    _emit_build_progress(progress_path, 1, "Validating reviewed build plan")

    production, changes, source, output, workspace_dir = _validate_execution_plan(plan)
    _emit_build_progress(progress_path, 5, "Build plan and source hash verified")

    output.parent.mkdir(parents=True, exist_ok=True)
    reserve_gb = int(plan.get("reserve_gb") or 0)
    source_size = source.stat().st_size
    required = max(12 * 1024**3, source_size * 4)

    capacity_probe = workspace_dir if workspace_dir.exists() else workspace_dir.parent
    free = shutil.disk_usage(capacity_probe).free
    if free - required < reserve_gb * 1024**3:
        raise BuildError(
            f"Storage reserve would be violated: free={free / 1024**3:.1f} GiB, "
            f"estimated build={required / 1024**3:.1f} GiB, reserve={reserve_gb} GiB."
        )

    _emit_build_progress(progress_path, 7, "Preparing isolated Linux workspace")
    work, image, mountpoint = _make_linux_semantic_workspace(workspace_dir, required)
    layer_mounts: list[Path] = []

    try:
        _emit_build_progress(progress_path, 10, "Inspecting ISO filesystem")
        files = _iso_files(source)
        file_set = set(files)
        layers = _rootfs_layers(files)
        if not layers:
            raise BuildError("No supported SquashFS root filesystem was found in this image.")

        _emit_build_progress(
            progress_path,
            15,
            "Preparing layered root filesystem",
            f"{len(layers)} SquashFS layer(s)",
        )
        rootfs, repack_source, source_compression, layer_mounts = _prepare_layered_rootfs(
            source,
            work,
            layers,
        )
        top_member = layers[-1]
        _emit_build_progress(progress_path, 35, "Layered root filesystem ready")

        adds, removes, replacements = _apply_packages(
            rootfs,
            changes,
            progress_path=progress_path,
        )

        _emit_build_progress(progress_path, 70, "Regenerating package manifests")
        final_entries = _installed_manifest_entries(rootfs)
        if not final_entries:
            raise BuildError("Could not generate a non-empty installed-package manifest after apply.")

        generated_dir = work / "generated-metadata"
        generated_dir.mkdir(parents=True, exist_ok=True)
        full_manifest = generated_dir / "top.manifest.full"
        delta_manifest = generated_dir / "top.manifest"
        size_file = generated_dir / "top.size"
        _write_manifest_entries(final_entries, full_manifest)

        top_manifest_member = _sibling_metadata(top_member, ".manifest")
        top_full_member = _sibling_metadata(top_member, ".manifest.full")
        top_size_member = _sibling_metadata(top_member, ".size")

        maps: list[tuple[Path, str]] = []

        if top_full_member in file_set:
            maps.append((full_manifest, top_full_member))

        if top_manifest_member in file_set:
            if len(layers) > 1:
                lower_full_member = _sibling_metadata(layers[-2], ".manifest.full")
                if lower_full_member not in file_set:
                    raise BuildError(
                        "Layered ISO is missing the cumulative lower-layer manifest required "
                        "to regenerate the top-layer package delta safely."
                    )
                lower_full = generated_dir / "lower.manifest.full"
                _extract_iso_member(source, lower_full_member, lower_full)
                _write_delta_manifest(lower_full, final_entries, delta_manifest)
                maps.append((delta_manifest, top_manifest_member))
            else:
                maps.append((full_manifest, top_manifest_member))

        if len(layers) > 1 and top_full_member not in file_set:
            raise BuildError(
                "Layered ISO is missing the top cumulative package manifest; "
                "ChromaPress refuses to emit inconsistent package metadata."
            )

        if top_size_member in file_set:
            size_file.write_text(
                str(_rootfs_size_bytes(repack_source)) + "\n",
                encoding="ascii",
            )
            maps.append((size_file, top_size_member))

        requested_compression = str(production.get("compression") or "preserve").lower()
        compression = source_compression if requested_compression == "preserve" else requested_compression
        if compression not in {"gzip", "xz", "lzo", "lz4", "zstd"}:
            raise BuildError(f"Unsupported SquashFS compression for apply: {compression}")

        rebuilt = work / PurePosixPath(top_member).name
        _emit_build_progress(progress_path, 74, "Rebuilding SquashFS")
        _run(
            [
                "mksquashfs",
                str(repack_source),
                str(rebuilt),
                "-noappend",
                "-comp",
                compression,
            ],
            timeout=7200,
        )
        _emit_build_progress(progress_path, 84, "SquashFS rebuilt")
        maps.insert(0, (rebuilt, top_member))

        # No chroot/bind mounts remain now. Unmount the OverlayFS stack before
        # xorriso reads the rebuilt upper-layer image and before workspace cleanup.
        _unmount_layered_rootfs(layer_mounts)
        layer_mounts = []

        if output.exists():
            raise BuildError("Output appeared during build; refusing implicit overwrite.")

        xorriso_args = [
            "xorriso",
            "-indev",
            str(source),
            "-outdev",
            str(output),
            "-boot_image",
            "any",
            "replay",
            "-overwrite",
            "on",
        ]
        for source_file, iso_member in maps:
            xorriso_args += ["-map", str(source_file), iso_member]
        xorriso_args += ["-commit"]
        _emit_build_progress(progress_path, 86, "Writing bootable ISO image")
        _run(xorriso_args, timeout=7200)

        _emit_build_progress(progress_path, 93, "ISO image written")
        _emit_build_progress(progress_path, 94, "Calculating output SHA-256")
        output_sha = _sha256(output)
        _emit_build_progress(progress_path, 96, "Output SHA-256 verified")

        _emit_build_progress(progress_path, 97, "Verifying boot structure")
        boot = _run(
            [
                "xorriso",
                "-indev",
                str(output),
                "-report_el_torito",
                "plain",
                "-report_system_area",
                "plain",
            ],
            timeout=300,
        )
        boot_text = (boot.stdout or "") + "\n" + (boot.stderr or "")
        boot_ok = bool(boot_text.strip())

        verification_policy = str(production.get("verification_policy") or "")
        if verification_policy in {"sha256_boot_structure", "strict_runtime_required"} and not boot_ok:
            raise BuildError("Post-build boot-structure verification produced no evidence.")

        # Verify that the same top rootfs member still exists in the output image.
        output_files = _iso_files(output)
        output_layers = _rootfs_layers(output_files)
        if top_member not in output_layers:
            raise BuildError(f"Post-build verification could not find rebuilt rootfs layer: {top_member}")

        _emit_build_progress(progress_path, 99, "Rechecking source ISO integrity")
        source_sha_after = _sha256(source)
        expected_source_sha = str(production.get("source_sha256") or "").lower()
        if source_sha_after != expected_source_sha:
            raise BuildError(
                "Source ISO hash changed during build. Output is rejected and the build is aborted."
            )

        _emit_build_progress(
            progress_path,
            100,
            "ISO BUILD COMPLETE!",
            "Output hash and static boot structure verified; runtime boot test is still required.",
        )
        return {
            "status": "PASS",
            "source_path": str(source),
            "source_sha256": expected_source_sha,
            "output_path": str(output),
            "output_sha256": output_sha,
            "rootfs_layers": layers,
            "rebuilt_rootfs_member": top_member,
            "source_compression": source_compression,
            "output_compression": compression,
            "added_packages": adds,
            "removed_packages": removes,
            "replacements": [{"from": old, "to": new} for old, new in replacements],
            "boot_structure_checked": True,
            "runtime_boot_verification_required": True,
            "source_mutated": False,
        }
    except Exception:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if layer_mounts:
            _unmount_layered_rootfs(layer_mounts)
        _cleanup_linux_semantic_workspace(work, image, mountpoint)
