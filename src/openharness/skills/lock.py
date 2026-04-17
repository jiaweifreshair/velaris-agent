"""Lock file and Taps management for Skills Hub.

Provides:
- ``LockEntry`` — Pydantic model for a single installed skill record.
- ``HubLockFile`` — Atomic read/write of ``lock.json``.
- ``TapsManager`` — CRUD for custom tap sources in ``taps.json``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class LockEntry(BaseModel):
    """A single installed-skill record inside ``lock.json``."""

    name: str
    source: str
    identifier: str
    trust_level: str
    content_hash: str
    install_path: str
    files: list[str]
    installed_at: str
    updated_at: str | None = None


# ---------------------------------------------------------------------------
# HubLockFile
# ---------------------------------------------------------------------------


class HubLockFile:
    """Manage the Hub lock file (``lock.json``).

    The file uses atomic writes (write to a temp file, then
    ``os.replace()``) to avoid corruption from concurrent access.
    """

    def __init__(self, lock_path: Path | None = None) -> None:
        if lock_path is None:
            from openharness.skills.loader import get_user_skills_dir

            lock_path = get_user_skills_dir() / "lock.json"
        self._path = lock_path

    # -- public API ----------------------------------------------------------

    def load(self) -> dict[str, LockEntry]:
        """Load all skill entries from the lock file.

        Returns an empty dict when the file is missing or contains
        invalid JSON, logging a warning in the latter case.
        """
        if not self._path.exists():
            return {}

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse lock file %s: %s", self._path, exc)
            return {}

        if not isinstance(data, dict):
            logger.warning("Lock file %s has unexpected format", self._path)
            return {}
        skills_dict: dict = data.get("skills", {})
        entries: dict[str, LockEntry] = {}
        for name, value in skills_dict.items():
            try:
                entries[name] = LockEntry.model_validate(value)
            except Exception:  # noqa: BLE001
                logger.warning("Skipping invalid lock entry: %s", name)
        return entries

    def save(self, entries: dict[str, LockEntry]) -> None:
        """Atomically write *entries* to the lock file."""
        payload = {
            "version": 1,
            "skills": {k: v.model_dump() for k, v in entries.items()},
        }
        self._atomic_write(json.dumps(payload, indent=2, ensure_ascii=False))

    def record_install(self, entry: LockEntry) -> None:
        """Add or update *entry* in the lock file."""
        entries = self.load()
        entries[entry.name] = entry
        self.save(entries)

    def record_uninstall(self, name: str) -> None:
        """Remove the entry for *name* from the lock file."""
        entries = self.load()
        entries.pop(name, None)
        self.save(entries)

    def get_installed(self, name: str) -> LockEntry | None:
        """Return the ``LockEntry`` for *name*, or ``None``."""
        return self.load().get(name)

    def list_installed(self) -> list[LockEntry]:
        """Return all installed skill entries."""
        return list(self.load().values())

    # -- internals -----------------------------------------------------------

    def _atomic_write(self, content: str) -> None:
        """Write *content* to a temp file then ``os.replace()``."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=self._path.parent,
            suffix=".tmp",
        )
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp, self._path)
        except BaseException:
            if not closed:
                os.close(fd)
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise


# ---------------------------------------------------------------------------
# TapsManager
# ---------------------------------------------------------------------------

_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class TapsManager:
    """Manage custom tap sources stored in ``taps.json``."""

    def __init__(self, taps_path: Path | None = None) -> None:
        if taps_path is None:
            from openharness.config.paths import get_config_dir

            taps_path = get_config_dir() / "taps.json"
        self._path = taps_path

    # -- public API ----------------------------------------------------------

    def load(self) -> list[dict[str, str]]:
        """Return the list of registered taps."""
        if not self._path.exists():
            return []

        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse taps file %s: %s", self._path, exc)
            return []

        return list(data.get("taps", []))

    def save(self, taps: list[dict[str, str]]) -> None:
        """Persist *taps* to the taps file."""
        payload = {"version": 1, "taps": taps}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, repo: str) -> None:
        """Register a new tap.

        Raises ``ValueError`` if *repo* does not match ``owner/repo`` format.
        """
        if not _OWNER_REPO_RE.match(repo):
            raise ValueError(
                f"Invalid tap format: {repo!r}. Expected 'owner/repo'."
            )

        taps = self.load()
        # Avoid duplicates
        if any(t.get("repo") == repo for t in taps):
            return

        taps.append({
            "repo": repo,
            "added_at": datetime.now(timezone.utc).isoformat(),
        })
        self.save(taps)

    def remove(self, repo: str) -> None:
        """Remove the tap identified by *repo*."""
        taps = self.load()
        taps = [t for t in taps if t.get("repo") != repo]
        self.save(taps)

    def list_taps(self) -> list[dict[str, str]]:
        """Return all registered taps."""
        return self.load()
