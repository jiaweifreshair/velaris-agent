"""Skills Hub — source abstraction, data models, and utility functions.

Provides:
- ``SkillMeta`` / ``SkillBundle`` — Pydantic models for search results and fetched bundles.
- ``SkillSource`` ABC — unified interface for skill sources.
- ``GitHubAuth`` / ``GitHubSource`` — GitHub-backed skill source.
- ``OptionalSkillSource`` — local ``optional-skills/`` directory source.
- Utility functions for hashing, validation, and path normalisation.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import re
import shutil
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel

from openharness.skills.guard import scan_skill as guard_scan_skill
from openharness.skills.guard import should_allow_install
from openharness.skills.loader import get_user_skills_dir
from openharness.skills.lock import HubLockFile, LockEntry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SkillMeta(BaseModel):
    """Skill search-result metadata."""

    name: str
    description: str
    source: str  # "github", "optional", "tap:<repo>"
    identifier: str  # unique id, e.g. "owner/repo/path"
    trust_level: str  # "builtin" | "trusted" | "community"
    repo: str | None = None
    path: str | None = None
    tags: list[str] = []


class SkillBundle(BaseModel):
    """A complete skill file bundle fetched from a source."""

    name: str
    files: dict[str, str]  # relative_path -> content
    source: str
    identifier: str
    trust_level: str
    content_hash: str  # SHA-256 of all files
    metadata: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

_VALID_SKILL_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


def content_hash(content: str) -> str:
    """Return ``sha256:<hex>`` hash of a single file's content."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def bundle_content_hash(files: dict[str, str]) -> str:
    """Return ``sha256:<hex>`` hash of all files sorted by path.

    The hash is computed by concatenating ``path + '\\0' + content``
    for every file in sorted-path order, then hashing the result.
    """
    h = hashlib.sha256()
    for path in sorted(files.keys()):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(files[path].encode("utf-8"))
    return f"sha256:{h.hexdigest()}"


def _validate_skill_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a valid skill name.

    Valid names start with an alphanumeric character and may contain
    alphanumerics, dots, hyphens, and underscores.
    """
    if not name or not _VALID_SKILL_NAME_RE.match(name):
        raise ValueError(
            f"Invalid skill name: {name!r}. "
            "Must start with alphanumeric and contain only [a-zA-Z0-9._-]."
        )


def _validate_bundle_rel_path(rel_path: str) -> None:
    """Raise ``ValueError`` if *rel_path* attempts path traversal."""
    # Check for absolute paths before normalisation (which strips slashes)
    stripped = rel_path.replace("\\", "/")
    if stripped.startswith("/"):
        raise ValueError(f"Absolute path not allowed in bundle: {rel_path!r}")
    normalised = _normalize_bundle_path(rel_path)
    parts = normalised.split("/")
    if ".." in parts:
        raise ValueError(f"Path traversal not allowed in bundle: {rel_path!r}")


def _normalize_bundle_path(rel_path: str) -> str:
    """Normalise path separators to forward-slash and collapse duplicates."""
    normalised = rel_path.replace("\\", "/")
    # Collapse repeated slashes
    while "//" in normalised:
        normalised = normalised.replace("//", "/")
    # Strip leading/trailing slashes
    return normalised.strip("/")


# ---------------------------------------------------------------------------
# SkillSource ABC
# ---------------------------------------------------------------------------


class SkillSource(ABC):
    """Abstract base class for skill source adapters."""

    @abstractmethod
    async def search(self, query: str) -> list[SkillMeta]:
        """Search for skills matching *query*."""

    @abstractmethod
    async def fetch(self, identifier: str) -> SkillBundle:
        """Fetch the complete skill bundle for *identifier*."""

    @abstractmethod
    def source_id(self) -> str:
        """Return a short identifier for this source (e.g. ``"github"``)."""

    @abstractmethod
    def trust_level_for(self, identifier: str) -> str:
        """Return the trust level for *identifier*."""


# ---------------------------------------------------------------------------
# GitHubAuth
# ---------------------------------------------------------------------------


class GitHubAuth:
    """GitHub authentication chain.

    Tries, in order:
    1. ``GITHUB_TOKEN`` environment variable (PAT).
    2. ``gh auth token`` CLI command.
    3. ``None`` (anonymous / unauthenticated).
    """

    async def get_token(self) -> str | None:
        """Return a GitHub token or ``None`` for anonymous access."""
        # 1. Environment variable
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            return token

        # 2. gh CLI
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh", "auth", "token",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                return stdout.decode().strip()
        except FileNotFoundError:
            pass
        except OSError:
            pass

        # 3. Anonymous
        return None


# ---------------------------------------------------------------------------
# GitHubSource
# ---------------------------------------------------------------------------

_GITHUB_API = "https://api.github.com"


class GitHubSource(SkillSource):
    """GitHub repository skill source.

    Uses the GitHub Contents API to search for ``SKILL.md`` files and
    the Git Tree API to fetch complete skill directories.
    """

    def __init__(self, repo: str, auth: GitHubAuth | None = None) -> None:
        self._repo = repo  # "owner/repo"
        self._auth = auth or GitHubAuth()

    # -- SkillSource interface -----------------------------------------------

    def source_id(self) -> str:
        return "github"

    def trust_level_for(self, identifier: str) -> str:  # noqa: ARG002
        return "community"

    async def search(self, query: str) -> list[SkillMeta]:
        """Search for SKILL.md files in the repository via Contents API."""
        headers = await self._build_headers()
        url = f"{_GITHUB_API}/repos/{self._repo}/git/trees/main?recursive=1"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            logger.warning("GitHub tree request failed for %s: %s", self._repo, exc)
            return []

        results: list[SkillMeta] = []
        tree = data.get("tree", [])
        for item in tree:
            path: str = item.get("path", "")
            if not path.endswith("/SKILL.md") and path != "SKILL.md":
                continue

            # Derive skill name from parent directory
            skill_dir = path.rsplit("/SKILL.md", 1)[0] if "/" in path else ""
            skill_name = skill_dir.rsplit("/", 1)[-1] if skill_dir else self._repo.split("/")[-1]

            if query and query.lower() not in skill_name.lower():
                continue

            identifier = f"{self._repo}/{skill_dir}" if skill_dir else self._repo
            results.append(
                SkillMeta(
                    name=skill_name,
                    description=f"Skill from {self._repo}",
                    source="github",
                    identifier=identifier,
                    trust_level=self.trust_level_for(identifier),
                    repo=self._repo,
                    path=skill_dir or None,
                )
            )

        return results

    async def fetch(self, identifier: str) -> SkillBundle:
        """Fetch a complete skill directory via Git Tree API."""
        # identifier format: "owner/repo/path/to/skill"
        parts = identifier.split("/", 2)
        if len(parts) < 2:
            raise ValueError(f"Invalid identifier: {identifier!r}")

        repo = f"{parts[0]}/{parts[1]}"
        skill_path = parts[2] if len(parts) > 2 else ""

        headers = await self._build_headers()

        # Get the tree for the default branch
        tree_url = f"{_GITHUB_API}/repos/{repo}/git/trees/main?recursive=1"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(tree_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch tree for {repo}: {exc}") from exc

        # Filter tree items to the skill directory
        prefix = f"{skill_path}/" if skill_path else ""
        files: dict[str, str] = {}
        tree = data.get("tree", [])

        blobs_to_fetch: list[tuple[str, str]] = []  # (rel_path, sha)
        for item in tree:
            item_path: str = item.get("path", "")
            if item.get("type") != "blob":
                continue
            if prefix and not item_path.startswith(prefix):
                continue
            if not prefix and "/" in item_path:
                # Top-level repo: only include root files
                continue

            rel_path = item_path[len(prefix):] if prefix else item_path
            _validate_bundle_rel_path(rel_path)
            blobs_to_fetch.append((rel_path, item["sha"]))

        # Fetch blob contents
        async with httpx.AsyncClient(timeout=30.0) as client:
            for rel_path, sha in blobs_to_fetch:
                blob_url = f"{_GITHUB_API}/repos/{repo}/git/blobs/{sha}"
                try:
                    blob_resp = await client.get(blob_url, headers=headers)
                    blob_resp.raise_for_status()
                    blob_data = blob_resp.json()
                    file_content = base64.b64decode(blob_data["content"]).decode("utf-8")
                    normalised = _normalize_bundle_path(rel_path)
                    files[normalised] = file_content
                except (httpx.HTTPError, KeyError, UnicodeDecodeError) as exc:
                    logger.warning("Failed to fetch blob %s: %s", rel_path, exc)

        if not files:
            raise RuntimeError(f"No files found for skill: {identifier}")

        # Derive name from the last path component
        skill_name = skill_path.rsplit("/", 1)[-1] if skill_path else repo.split("/")[-1]

        return SkillBundle(
            name=skill_name,
            files=files,
            source="github",
            identifier=identifier,
            trust_level=self.trust_level_for(identifier),
            content_hash=bundle_content_hash(files),
        )

    # -- internals -----------------------------------------------------------

    async def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers with optional auth token."""
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = await self._auth.get_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers


# ---------------------------------------------------------------------------
# OptionalSkillSource
# ---------------------------------------------------------------------------


class OptionalSkillSource(SkillSource):
    """Local ``optional-skills/`` directory skill source.

    Scans a local directory for sub-directories containing ``SKILL.md``.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    # -- SkillSource interface -----------------------------------------------

    def source_id(self) -> str:
        return "optional"

    def trust_level_for(self, identifier: str) -> str:  # noqa: ARG002
        return "builtin"

    async def search(self, query: str) -> list[SkillMeta]:
        """Scan local directory for SKILL.md files matching *query*."""
        results: list[SkillMeta] = []

        if not self._base_dir.is_dir():
            return results

        for skill_md in sorted(self._base_dir.rglob("SKILL.md")):
            skill_dir = skill_md.parent
            skill_name = skill_dir.name

            if query and query.lower() not in skill_name.lower():
                continue

            # Read first line of description from SKILL.md
            description = f"Optional skill: {skill_name}"
            try:
                text = skill_md.read_text(encoding="utf-8")
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith(("#", "---")):
                        description = stripped[:200]
                        break
            except OSError:
                pass

            identifier = f"optional/{skill_name}"
            results.append(
                SkillMeta(
                    name=skill_name,
                    description=description,
                    source="optional",
                    identifier=identifier,
                    trust_level=self.trust_level_for(identifier),
                    path=str(skill_dir),
                )
            )

        return results

    async def fetch(self, identifier: str) -> SkillBundle:
        """Read all files from the local skill directory."""
        # identifier format: "optional/<skill_name>"
        parts = identifier.split("/", 1)
        if len(parts) < 2:
            raise ValueError(f"Invalid optional identifier: {identifier!r}")

        skill_name = parts[1]
        skill_dir = self._base_dir / skill_name

        if not skill_dir.is_dir():
            raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

        files: dict[str, str] = {}
        for fpath in sorted(skill_dir.rglob("*")):
            if not fpath.is_file():
                continue
            rel = str(fpath.relative_to(skill_dir))
            normalised = _normalize_bundle_path(rel)
            _validate_bundle_rel_path(normalised)
            try:
                files[normalised] = fpath.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                logger.warning("Skipping unreadable file %s: %s", fpath, exc)

        if not files:
            raise RuntimeError(f"No readable files in skill: {identifier}")

        return SkillBundle(
            name=skill_name,
            files=files,
            source="optional",
            identifier=identifier,
            trust_level=self.trust_level_for(identifier),
            content_hash=bundle_content_hash(files),
        )


# ---------------------------------------------------------------------------
# Hub operation functions
# ---------------------------------------------------------------------------


def ensure_hub_dirs() -> tuple[Path, Path]:
    """Create and return the ``quarantine/`` and ``audit/`` directories.

    Both directories live under ``get_user_skills_dir()``.

    Returns
    -------
    tuple[Path, Path]
        ``(quarantine_dir, audit_dir)``
    """
    base = get_user_skills_dir()
    quarantine_dir = base / ".quarantine"
    quarantine_dir.mkdir(parents=True, exist_ok=True)

    # audit/ lives one level up (under config dir) per design doc layout
    from openharness.config.paths import get_config_dir

    audit_dir = get_config_dir() / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return quarantine_dir, audit_dir


def quarantine_bundle(bundle: SkillBundle) -> Path:
    """Write *bundle* files into the quarantine directory.

    Creates ``<quarantine>/<bundle.name>/`` and writes every file from
    ``bundle.files`` into it.

    Returns
    -------
    Path
        The quarantine path for this bundle.
    """
    quarantine_dir, _ = ensure_hub_dirs()
    dest = quarantine_dir / bundle.name

    # Clean up any previous quarantine for the same name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)

    for rel_path, content in bundle.files.items():
        _validate_bundle_rel_path(rel_path)
        normalised = _normalize_bundle_path(rel_path)
        file_path = dest / normalised
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return dest


def install_from_quarantine(quarantine_path: Path, target_dir: Path) -> Path:
    """Copy files from *quarantine_path* to *target_dir*.

    If *target_dir* already exists it is removed first (force-install
    scenario).

    Returns
    -------
    Path
        The *target_dir* after installation.
    """
    if target_dir.exists():
        shutil.rmtree(target_dir)
    shutil.copytree(quarantine_path, target_dir)
    return target_dir


async def install_skill(
    identifier: str,
    sources: list[SkillSource],
    *,
    force: bool = False,
) -> str:
    """Complete skill installation flow.

    1. Find the right source and fetch the bundle.
    2. Check if already installed (via ``HubLockFile``); reject if
       *force* is ``False``.
    3. Quarantine the bundle.
    4. Run ``scan_skill()`` from ``guard.py``.
    5. Check ``should_allow_install()`` — if blocked, clean up and raise.
    6. Copy from quarantine to the user skills directory.
    7. Record the install in the lock file.
    8. Append an audit log entry.
    9. Clean up the quarantine directory.

    Returns
    -------
    str
        A human-readable success message.
    """
    # --- 1. Fetch bundle from the first source that can provide it ---
    bundle: SkillBundle | None = None
    last_error: Exception | None = None
    for source in sources:
        try:
            bundle = await source.fetch(identifier)
            break
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.debug("Source %s cannot fetch %s: %s", source.source_id(), identifier, exc)

    if bundle is None:
        msg = f"No source could provide skill: {identifier}"
        if last_error:
            msg += f" (last error: {last_error})"
        raise RuntimeError(msg)

    _validate_skill_name(bundle.name)

    # --- 2. Check if already installed ---
    lock = HubLockFile()
    existing = lock.get_installed(bundle.name)
    if existing and not force:
        raise RuntimeError(
            f"Skill '{bundle.name}' is already installed. "
            "Use force=True or the update command to reinstall."
        )

    quarantine_path: Path | None = None
    try:
        # --- 3. Quarantine ---
        quarantine_path = quarantine_bundle(bundle)

        # --- 4. Security scan ---
        scan_result = guard_scan_skill(
            skill_dir=quarantine_path,
            skill_name=bundle.name,
            source=bundle.source,
            trust_level=bundle.trust_level,
        )

        # --- 5. Gate install ---
        allowed, reason = should_allow_install(scan_result)
        if not allowed:
            raise RuntimeError(
                f"Installation of '{bundle.name}' blocked by security scan: {reason}"
            )

        # --- 6. Install from quarantine ---
        target_dir = get_user_skills_dir() / bundle.name
        install_from_quarantine(quarantine_path, target_dir)

        # --- 7. Record in lock file ---
        now = datetime.now(timezone.utc).isoformat()
        entry = LockEntry(
            name=bundle.name,
            source=bundle.source,
            identifier=bundle.identifier,
            trust_level=bundle.trust_level,
            content_hash=bundle.content_hash,
            install_path=str(target_dir),
            files=sorted(bundle.files.keys()),
            installed_at=now,
            updated_at=now if force else None,
        )
        lock.record_install(entry)

        # --- 8. Audit log ---
        append_audit_log(
            action="install" if not force else "update",
            skill_name=bundle.name,
            details={
                "source": bundle.source,
                "identifier": bundle.identifier,
                "content_hash": bundle.content_hash,
                "verdict": scan_result.verdict,
                "findings_count": len(scan_result.findings),
            },
        )

        return f"Successfully installed skill '{bundle.name}' from {bundle.source}."

    finally:
        # --- 9. Clean up quarantine ---
        if quarantine_path and quarantine_path.exists():
            shutil.rmtree(quarantine_path, ignore_errors=True)


def uninstall_skill(name: str) -> str:
    """Uninstall a skill by *name*.

    Removes the skill directory and its lock-file entry, then appends
    an audit log record.

    Returns
    -------
    str
        A human-readable success message.
    """
    _validate_skill_name(name)

    lock = HubLockFile()
    existing = lock.get_installed(name)
    if not existing:
        raise RuntimeError(f"Skill '{name}' is not installed.")

    # Remove skill directory
    skill_dir = get_user_skills_dir() / name
    if skill_dir.exists():
        shutil.rmtree(skill_dir)

    # Remove lock entry
    lock.record_uninstall(name)

    # Audit log
    append_audit_log(
        action="uninstall",
        skill_name=name,
        details={"source": existing.source, "identifier": existing.identifier},
    )

    return f"Successfully uninstalled skill '{name}'."


async def check_for_skill_updates(
    sources: list[SkillSource],
) -> list[dict[str, Any]]:
    """Check all installed skills for available updates.

    For each installed skill, fetch the latest content hash from its
    source and compare with the lock-file hash.

    Returns
    -------
    list[dict[str, Any]]
        A list of dicts with keys ``name``, ``current_hash``,
        ``latest_hash``, and ``source`` for skills that have updates.
    """
    lock = HubLockFile()
    installed = lock.list_installed()
    updates: list[dict[str, Any]] = []

    for entry in installed:
        # Try to fetch the latest bundle from any source
        for source in sources:
            try:
                bundle = await source.fetch(entry.identifier)
                if bundle.content_hash != entry.content_hash:
                    updates.append({
                        "name": entry.name,
                        "current_hash": entry.content_hash,
                        "latest_hash": bundle.content_hash,
                        "source": entry.source,
                    })
                break  # found the right source
            except Exception:  # noqa: BLE001
                logger.debug(
                    "Source %s cannot fetch %s for update check",
                    source.source_id(),
                    entry.identifier,
                )
                continue

    return updates


async def update_skill(name: str, sources: list[SkillSource]) -> str:
    """Update an installed skill by re-installing with ``force=True``.

    Returns
    -------
    str
        A human-readable success message.
    """
    lock = HubLockFile()
    existing = lock.get_installed(name)
    if not existing:
        raise RuntimeError(f"Skill '{name}' is not installed.")

    return await install_skill(existing.identifier, sources, force=True)


async def parallel_search_sources(
    query: str,
    sources: list[SkillSource],
) -> list[SkillMeta]:
    """Search all *sources* in parallel and merge results.

    Duplicate identifiers are removed — the first occurrence (by source
    order) wins.

    Returns
    -------
    list[SkillMeta]
        De-duplicated search results.
    """

    async def _safe_search(src: SkillSource) -> list[SkillMeta]:
        try:
            return await src.search(query)
        except Exception:  # noqa: BLE001
            logger.warning("Search failed for source %s", src.source_id())
            return []

    all_results = await asyncio.gather(*[_safe_search(s) for s in sources])

    seen: set[str] = set()
    merged: list[SkillMeta] = []
    for results in all_results:
        for meta in results:
            if meta.identifier not in seen:
                seen.add(meta.identifier)
                merged.append(meta)

    return merged


def append_audit_log(
    action: str,
    skill_name: str,
    details: dict[str, Any],
) -> None:
    """Append a JSON-line entry to the audit log file.

    The log file is located at ``<config_dir>/audit/skills-audit.log``.
    """
    _, audit_dir = ensure_hub_dirs()
    log_path = audit_dir / "skills-audit.log"

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "skill": skill_name,
        **details,
    }

    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
