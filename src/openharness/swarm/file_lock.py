"""Cross-platform file locking helpers for swarm coordination."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@contextmanager
def exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    """Acquire an exclusive lock for *lock_path* across supported platforms."""

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r+") as lock_file:
        _lock_file(lock_file)
        try:
            yield
        finally:
            _unlock_file(lock_file)


def _lock_file(lock_file: TextIO) -> None:
    if os.name == "nt":
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        return
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)


def _unlock_file(lock_file: TextIO) -> None:
    if os.name == "nt":
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
