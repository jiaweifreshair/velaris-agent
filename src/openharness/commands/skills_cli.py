"""Skills Hub CLI subcommands.

Provides ``skills_app`` (search/install/check/update/uninstall/list/audit)
and ``tap_app`` (add/remove/list) Typer command groups.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Optional

import typer

# ---------------------------------------------------------------------------
# Typer apps
# ---------------------------------------------------------------------------

skills_app = typer.Typer(name="skills", help="Skills Hub management")
tap_app = typer.Typer(name="tap", help="Manage custom Tap sources")
skills_app.add_typer(tap_app)


# ---------------------------------------------------------------------------
# Skills commands
# ---------------------------------------------------------------------------


@skills_app.command("search")
def do_search(
    query: str = typer.Argument(..., help="Search query"),
) -> None:
    """Search for skills across all sources."""
    from openharness.skills.hub import parallel_search_sources
    from openharness.tools.skills_hub_tool import default_sources

    try:
        sources = default_sources()
        results = asyncio.run(parallel_search_sources(query, sources))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    if not results:
        print("No skills found.")
        return

    print(f"Found {len(results)} skill(s):")
    for meta in results:
        print(f"  - {meta.name} [{meta.source}] ({meta.identifier}): {meta.description}")


@skills_app.command("install")
def do_install(
    identifier: str = typer.Argument(..., help="Skill identifier to install"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reinstall if already installed"),
) -> None:
    """Install a skill from any available source."""
    from openharness.skills.hub import install_skill
    from openharness.tools.skills_hub_tool import default_sources

    try:
        sources = default_sources()
        msg = asyncio.run(install_skill(identifier, sources, force=force))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    print(msg)


@skills_app.command("check")
def do_check(
    name: Optional[str] = typer.Argument(None, help="Skill name to check (all if omitted)"),
) -> None:
    """Check for available skill updates."""
    from openharness.skills.hub import check_for_skill_updates
    from openharness.tools.skills_hub_tool import default_sources

    try:
        sources = default_sources()
        updates = asyncio.run(check_for_skill_updates(sources))
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    if name:
        updates = [u for u in updates if u["name"] == name]

    if not updates:
        print("All installed skills are up to date.")
        return

    print(f"{len(updates)} skill(s) have updates available:")
    for u in updates:
        print(f"  - {u['name']} (source: {u['source']})")


@skills_app.command("update")
def do_update(
    name: Optional[str] = typer.Argument(None, help="Skill name to update (all if omitted)"),
) -> None:
    """Update an installed skill."""
    from openharness.skills.hub import check_for_skill_updates, update_skill
    from openharness.tools.skills_hub_tool import default_sources

    try:
        sources = default_sources()
        if name:
            msg = asyncio.run(update_skill(name, sources))
            print(msg)
        else:
            updates = asyncio.run(check_for_skill_updates(sources))
            if not updates:
                print("All installed skills are up to date.")
                return
            for u in updates:
                msg = asyncio.run(update_skill(u["name"], sources))
                print(msg)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)


@skills_app.command("uninstall")
def do_uninstall(
    name: str = typer.Argument(..., help="Skill name to uninstall"),
) -> None:
    """Uninstall an installed skill."""
    from openharness.skills.hub import uninstall_skill

    try:
        msg = uninstall_skill(name)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    print(msg)


@skills_app.command("list")
def do_list() -> None:
    """List all installed skills."""
    from openharness.skills.lock import HubLockFile

    lock = HubLockFile()
    entries = lock.list_installed()

    if not entries:
        print("No skills installed via Hub.")
        return

    print(f"{len(entries)} skill(s) installed:")
    for entry in entries:
        updated = f", updated {entry.updated_at}" if entry.updated_at else ""
        print(
            f"  - {entry.name} [{entry.source}] "
            f"(hash: {entry.content_hash[:20]}...{updated})"
        )


@skills_app.command("audit")
def do_audit(
    name: Optional[str] = typer.Argument(None, help="Skill name to audit (show log if omitted)"),
) -> None:
    """Show the skills audit log or audit a specific skill."""
    from openharness.skills.hub import append_audit_log, ensure_hub_dirs

    if name:
        # Re-scan the installed skill
        from openharness.skills.guard import scan_skill
        from openharness.skills.loader import get_user_skills_dir
        from openharness.skills.lock import HubLockFile

        lock = HubLockFile()
        entry = lock.get_installed(name)
        if not entry:
            print(f"Error: Skill '{name}' is not installed.", file=sys.stderr)
            raise typer.Exit(1)

        skill_dir = get_user_skills_dir() / name
        if not skill_dir.is_dir():
            print(f"Error: Skill directory not found: {skill_dir}", file=sys.stderr)
            raise typer.Exit(1)

        result = scan_skill(
            skill_dir=skill_dir,
            skill_name=name,
            source=entry.source,
            trust_level=entry.trust_level,
        )
        print(f"Audit result for '{name}': {result.verdict}")
        print(f"  Findings: {len(result.findings)}")
        print(f"  Summary: {result.summary}")

        append_audit_log(
            action="audit",
            skill_name=name,
            details={
                "verdict": result.verdict,
                "findings_count": len(result.findings),
            },
        )
        return

    # Show audit log
    _, audit_dir = ensure_hub_dirs()
    log_path = audit_dir / "skills-audit.log"
    if not log_path.exists():
        print("No audit log entries found.")
        return

    try:
        text = log_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        print(f"Error reading audit log: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    if not text:
        print("No audit log entries found.")
        return

    lines = text.splitlines()
    recent = lines[-50:]
    print(f"Audit log ({len(lines)} total entries, showing last {len(recent)}):")
    for line in recent:
        print(f"  {line}")


# ---------------------------------------------------------------------------
# Tap commands
# ---------------------------------------------------------------------------


@tap_app.command("add")
def tap_add(
    repo: str = typer.Argument(..., help="GitHub repo in owner/repo format"),
) -> None:
    """Add a custom Tap source."""
    from openharness.skills.lock import TapsManager

    try:
        mgr = TapsManager()
        mgr.add(repo)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    print(f"Added tap: {repo}")


@tap_app.command("remove")
def tap_remove(
    repo: str = typer.Argument(..., help="GitHub repo to remove"),
) -> None:
    """Remove a custom Tap source."""
    from openharness.skills.lock import TapsManager

    try:
        mgr = TapsManager()
        mgr.remove(repo)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise typer.Exit(1)

    print(f"Removed tap: {repo}")


@tap_app.command("list")
def tap_list() -> None:
    """List all registered Tap sources."""
    from openharness.skills.lock import TapsManager

    mgr = TapsManager()
    taps = mgr.list_taps()

    if not taps:
        print("No taps registered.")
        return

    print(f"{len(taps)} tap(s) registered:")
    for t in taps:
        added = t.get("added_at", "unknown")
        print(f"  - {t['repo']} (added: {added})")
