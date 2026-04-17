"""Security scanner for Skills Hub.

Ported from hermes-agent ``tools/skills_guard.py``.

Provides:
- ``Finding`` / ``ScanResult`` / ``ThreatPattern`` — data containers.
- ``scan_file()`` — scan a single file for threat patterns.
- ``scan_skill()`` — scan an entire skill directory.
- ``should_allow_install()`` — gate install based on scan verdict.
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILES = 50
MAX_FILE_SIZE = 500 * 1024  # 500 KB
_TEXT_EXTENSIONS = frozenset({
    ".md", ".txt", ".py", ".js", ".ts", ".json", ".yaml", ".yml",
    ".toml", ".cfg", ".ini", ".sh", ".bash", ".zsh", ".fish",
    ".html", ".css", ".xml", ".csv", ".rst", ".tex",
})


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single security finding from a scan."""

    pattern_id: str
    severity: str  # "high" | "medium" | "low"
    category: str
    file: str
    line: int
    match: str
    description: str


@dataclass
class ScanResult:
    """Result of scanning an entire skill directory."""

    skill_name: str
    source: str
    trust_level: str
    verdict: str  # "pass" | "fail" | "warn"
    findings: list[Finding] = field(default_factory=list)
    scanned_at: str = ""
    summary: str = ""


@dataclass
class ThreatPattern:
    """A compiled regex threat pattern."""

    id: str
    pattern: re.Pattern[str]
    severity: str  # "high" | "medium" | "low"
    category: str
    description: str


# ---------------------------------------------------------------------------
# Threat pattern definitions
# ---------------------------------------------------------------------------

def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


THREAT_PATTERNS: list[ThreatPattern] = [
    # --- Data exfiltration ---
    ThreatPattern(
        id="EXFIL-001",
        pattern=_compile(r"curl\s+.*-[dX]\s+.*POST"),
        severity="high",
        category="exfiltration",
        description="HTTP POST via curl — potential data exfiltration",
    ),
    ThreatPattern(
        id="EXFIL-002",
        pattern=_compile(r"requests\.post\s*\("),
        severity="high",
        category="exfiltration",
        description="Python requests.post — potential data exfiltration",
    ),
    ThreatPattern(
        id="EXFIL-003",
        pattern=_compile(r"wget\s+.*--post"),
        severity="high",
        category="exfiltration",
        description="wget POST — potential data exfiltration",
    ),

    # --- Command injection ---
    ThreatPattern(
        id="INJECT-001",
        pattern=_compile(r"subprocess\.(call|run|Popen)\s*\("),
        severity="high",
        category="injection",
        description="subprocess invocation — potential command injection",
    ),
    ThreatPattern(
        id="INJECT-002",
        pattern=_compile(r"os\.system\s*\("),
        severity="high",
        category="injection",
        description="os.system call — potential command injection",
    ),
    ThreatPattern(
        id="INJECT-003",
        pattern=_compile(r"eval\s*\("),
        severity="high",
        category="injection",
        description="eval() call — potential code injection",
    ),
    ThreatPattern(
        id="INJECT-004",
        pattern=_compile(r"exec\s*\("),
        severity="high",
        category="injection",
        description="exec() call — potential code injection",
    ),

    # --- Destructive operations ---
    ThreatPattern(
        id="DESTR-001",
        pattern=_compile(r"shutil\.rmtree\s*\("),
        severity="high",
        category="destructive",
        description="Recursive directory removal — destructive operation",
    ),
    ThreatPattern(
        id="DESTR-002",
        pattern=_compile(r"os\.remove\s*\(|os\.unlink\s*\("),
        severity="medium",
        category="destructive",
        description="File deletion — potentially destructive",
    ),
    ThreatPattern(
        id="DESTR-003",
        pattern=_compile(r"rm\s+-rf\s+/"),
        severity="high",
        category="destructive",
        description="rm -rf on root — highly destructive",
    ),

    # --- Persistence / backdoors ---
    ThreatPattern(
        id="PERSIST-001",
        pattern=_compile(r"crontab|/etc/cron"),
        severity="high",
        category="persistence",
        description="Cron job manipulation — persistence backdoor",
    ),
    ThreatPattern(
        id="PERSIST-002",
        pattern=_compile(r"\.bashrc|\.bash_profile|\.zshrc|\.profile"),
        severity="medium",
        category="persistence",
        description="Shell profile modification — persistence risk",
    ),
    ThreatPattern(
        id="PERSIST-003",
        pattern=_compile(r"systemctl\s+(enable|start)|launchctl\s+load"),
        severity="high",
        category="persistence",
        description="Service registration — persistence backdoor",
    ),

    # --- Network access ---
    ThreatPattern(
        id="NET-001",
        pattern=_compile(r"socket\.socket\s*\("),
        severity="medium",
        category="network",
        description="Raw socket creation — network access",
    ),
    ThreatPattern(
        id="NET-002",
        pattern=_compile(r"http\.server|SimpleHTTPServer|BaseHTTPServer"),
        severity="high",
        category="network",
        description="HTTP server creation — opens network listener",
    ),
    ThreatPattern(
        id="NET-003",
        pattern=_compile(r"reverse.shell|bind.shell|nc\s+-[el]"),
        severity="high",
        category="network",
        description="Reverse/bind shell pattern — network backdoor",
    ),

    # --- Code obfuscation ---
    ThreatPattern(
        id="OBFUSC-001",
        pattern=_compile(r"base64\.(b64decode|decodebytes)\s*\("),
        severity="medium",
        category="obfuscation",
        description="Base64 decoding — potential code obfuscation",
    ),
    ThreatPattern(
        id="OBFUSC-002",
        pattern=_compile(r"\\x[0-9a-f]{2}(?:\\x[0-9a-f]{2}){3,}"),
        severity="medium",
        category="obfuscation",
        description="Hex-encoded string — potential obfuscation",
    ),
    ThreatPattern(
        id="OBFUSC-003",
        pattern=_compile(r"compile\s*\(\s*['\"]"),
        severity="medium",
        category="obfuscation",
        description="Dynamic code compilation — obfuscation risk",
    ),

    # --- Path traversal ---
    ThreatPattern(
        id="TRAV-001",
        pattern=_compile(r"\.\./\.\./"),
        severity="high",
        category="traversal",
        description="Path traversal sequence — directory escape",
    ),
    ThreatPattern(
        id="TRAV-002",
        pattern=_compile(r"open\s*\(\s*['\"]/(etc|proc|sys|dev)/"),
        severity="high",
        category="traversal",
        description="Access to sensitive system paths",
    ),

    # --- Mining ---
    ThreatPattern(
        id="MINE-001",
        pattern=_compile(r"stratum\+tcp://|xmrig|cryptonight|coinhive"),
        severity="high",
        category="mining",
        description="Cryptocurrency mining indicators",
    ),
    ThreatPattern(
        id="MINE-002",
        pattern=_compile(r"hashrate|mining.pool|nonce.*difficulty"),
        severity="medium",
        category="mining",
        description="Mining-related terminology",
    ),

    # --- Supply chain attacks ---
    ThreatPattern(
        id="SUPPLY-001",
        pattern=_compile(r"pip\s+install\s+(?!-r\b)"),
        severity="high",
        category="supply_chain",
        description="Dynamic pip install — supply chain risk",
    ),
    ThreatPattern(
        id="SUPPLY-002",
        pattern=_compile(r"npm\s+install|yarn\s+add"),
        severity="high",
        category="supply_chain",
        description="Dynamic npm/yarn install — supply chain risk",
    ),
    ThreatPattern(
        id="SUPPLY-003",
        pattern=_compile(r"__import__\s*\("),
        severity="medium",
        category="supply_chain",
        description="Dynamic import — potential supply chain vector",
    ),

    # --- Privilege escalation ---
    ThreatPattern(
        id="PRIV-001",
        pattern=_compile(r"sudo\s+"),
        severity="high",
        category="privilege_escalation",
        description="sudo invocation — privilege escalation",
    ),
    ThreatPattern(
        id="PRIV-002",
        pattern=_compile(r"chmod\s+[0-7]*[67][0-7]{2}|chmod\s+\+s"),
        severity="high",
        category="privilege_escalation",
        description="Dangerous chmod — privilege escalation",
    ),
    ThreatPattern(
        id="PRIV-003",
        pattern=_compile(r"setuid|setgid|os\.setuid|os\.setgid"),
        severity="high",
        category="privilege_escalation",
        description="Set UID/GID — privilege escalation",
    ),

    # --- Credential exposure ---
    ThreatPattern(
        id="CRED-001",
        pattern=_compile(
            r"(?:password|passwd|secret|api_key|apikey|token|auth)"
            r"\s*[=:]\s*['\"][^'\"]{8,}"
        ),
        severity="medium",
        category="credential_exposure",
        description="Hardcoded credential pattern",
    ),
    ThreatPattern(
        id="CRED-002",
        pattern=_compile(r"AWS_SECRET_ACCESS_KEY|AZURE_CLIENT_SECRET|GCP_SERVICE_ACCOUNT"),
        severity="high",
        category="credential_exposure",
        description="Cloud credential variable reference",
    ),
    ThreatPattern(
        id="CRED-003",
        pattern=_compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----"),
        severity="high",
        category="credential_exposure",
        description="Embedded private key",
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_binary(path: Path) -> bool:
    """Heuristic: read first 8 KB and look for null bytes."""
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" in chunk
    except OSError:
        return False


def _has_invisible_unicode(text: str) -> bool:
    """Detect invisible Unicode characters (zero-width, bidi overrides, etc.)."""
    for ch in text:
        cat = unicodedata.category(ch)
        # Cf = format chars (ZWJ, ZWNJ, bidi overrides, etc.)
        # Exclude common whitespace (\n, \r, \t) which are Cc
        if cat == "Cf":
            return True
    return False


def _symlink_escapes(link: Path, skill_dir: Path) -> bool:
    """Return True if *link* resolves to a target outside *skill_dir*."""
    try:
        resolved = link.resolve()
        skill_resolved = skill_dir.resolve()
        return not str(resolved).startswith(str(skill_resolved) + os.sep) and resolved != skill_resolved
    except OSError:
        return True  # broken symlink — treat as escape


# ---------------------------------------------------------------------------
# Core scan functions
# ---------------------------------------------------------------------------


def scan_file(path: Path, patterns: list[ThreatPattern] | None = None) -> list[Finding]:
    """Scan a single file for threat patterns.

    Parameters
    ----------
    path:
        File to scan.
    patterns:
        Threat patterns to check against.  Defaults to ``THREAT_PATTERNS``.

    Returns
    -------
    list[Finding]
        All findings for this file.
    """
    if patterns is None:
        patterns = THREAT_PATTERNS

    findings: list[Finding] = []

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("Cannot read %s: %s", path, exc)
        return findings

    for line_no, line in enumerate(text.splitlines(), start=1):
        for tp in patterns:
            m = tp.pattern.search(line)
            if m:
                findings.append(
                    Finding(
                        pattern_id=tp.id,
                        severity=tp.severity,
                        category=tp.category,
                        file=str(path),
                        line=line_no,
                        match=m.group()[:120],  # truncate long matches
                        description=tp.description,
                    )
                )

    return findings


def scan_skill(
    skill_dir: Path,
    skill_name: str,
    source: str,
    trust_level: str,
) -> ScanResult:
    """Scan an entire skill directory for security threats.

    Performs both structural checks (file count, size, binary, symlinks,
    invisible Unicode) and pattern-based content scanning.

    Parameters
    ----------
    skill_dir:
        Root directory of the skill to scan.
    skill_name:
        Human-readable skill name (for the report).
    source:
        Where the skill came from (e.g. ``"github"``).
    trust_level:
        Trust classification (``"builtin"`` / ``"trusted"`` / ``"community"``).

    Returns
    -------
    ScanResult
        Aggregated scan result with verdict.
    """
    findings: list[Finding] = []
    scanned_at = datetime.now(timezone.utc).isoformat()

    # Collect all files (non-recursive walk to respect symlinks carefully)
    all_files: list[Path] = []
    try:
        for root, _dirs, files in os.walk(skill_dir, followlinks=False):
            for fname in files:
                all_files.append(Path(root) / fname)
    except OSError as exc:
        logger.warning("Cannot walk skill dir %s: %s", skill_dir, exc)
        return ScanResult(
            skill_name=skill_name,
            source=source,
            trust_level=trust_level,
            verdict="fail",
            findings=[
                Finding(
                    pattern_id="STRUCT-ERR",
                    severity="high",
                    category="structural",
                    file=str(skill_dir),
                    line=0,
                    match="",
                    description=f"Cannot walk skill directory: {exc}",
                )
            ],
            scanned_at=scanned_at,
            summary="Scan failed: cannot read skill directory",
        )

    # --- Structural check: file count ---
    if len(all_files) > MAX_FILES:
        findings.append(
            Finding(
                pattern_id="STRUCT-001",
                severity="high",
                category="structural",
                file=str(skill_dir),
                line=0,
                match=f"{len(all_files)} files",
                description=f"Skill contains {len(all_files)} files, exceeding limit of {MAX_FILES}",
            )
        )

    for fpath in all_files:
        rel = str(fpath.relative_to(skill_dir))

        # --- Structural check: symlink escape ---
        if fpath.is_symlink() and _symlink_escapes(fpath, skill_dir):
            findings.append(
                Finding(
                    pattern_id="STRUCT-002",
                    severity="high",
                    category="structural",
                    file=rel,
                    line=0,
                    match=str(fpath),
                    description="Symlink points outside skill directory",
                )
            )
            continue  # don't follow escaped symlinks

        # --- Structural check: file size ---
        try:
            size = fpath.stat().st_size
        except OSError:
            size = 0

        if size > MAX_FILE_SIZE:
            findings.append(
                Finding(
                    pattern_id="STRUCT-003",
                    severity="high",
                    category="structural",
                    file=rel,
                    line=0,
                    match=f"{size} bytes",
                    description=f"File exceeds size limit of {MAX_FILE_SIZE} bytes",
                )
            )
            continue

        # --- Structural check: binary file ---
        if _is_binary(fpath):
            findings.append(
                Finding(
                    pattern_id="STRUCT-004",
                    severity="high",
                    category="structural",
                    file=rel,
                    line=0,
                    match="binary content",
                    description="Binary file detected in skill directory",
                )
            )
            continue

        # --- Structural check: invisible Unicode ---
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        if _has_invisible_unicode(text):
            findings.append(
                Finding(
                    pattern_id="STRUCT-005",
                    severity="medium",
                    category="structural",
                    file=rel,
                    line=0,
                    match="invisible unicode",
                    description="File contains invisible Unicode characters (potential obfuscation)",
                )
            )

        # --- Pattern scan ---
        file_findings = scan_file(fpath)
        findings.extend(file_findings)

    # --- Determine verdict ---
    verdict = _compute_verdict(findings)

    # --- Build summary ---
    high_count = sum(1 for f in findings if f.severity == "high")
    medium_count = sum(1 for f in findings if f.severity == "medium")
    low_count = sum(1 for f in findings if f.severity == "low")
    summary = (
        f"Scanned {len(all_files)} files: "
        f"{high_count} high, {medium_count} medium, {low_count} low severity findings"
    )

    return ScanResult(
        skill_name=skill_name,
        source=source,
        trust_level=trust_level,
        verdict=verdict,
        findings=findings,
        scanned_at=scanned_at,
        summary=summary,
    )


def _compute_verdict(findings: list[Finding]) -> str:
    """Derive verdict from findings list.

    - ``"fail"`` if any high-severity finding.
    - ``"warn"`` if any medium-severity finding.
    - ``"pass"`` otherwise.
    """
    for f in findings:
        if f.severity == "high":
            return "fail"
    for f in findings:
        if f.severity == "medium":
            return "warn"
    return "pass"


def should_allow_install(scan_result: ScanResult) -> tuple[bool, str]:
    """Decide whether a skill should be installed based on its scan result.

    Returns
    -------
    tuple[bool, str]
        ``(allowed, reason)`` — *allowed* is ``True`` only when the
        verdict is ``"pass"`` or ``"warn"``.  High-severity findings
        block installation.
    """
    if scan_result.verdict == "fail":
        high_findings = [f for f in scan_result.findings if f.severity == "high"]
        descriptions = "; ".join(f.description for f in high_findings[:5])
        return (
            False,
            f"Blocked: {len(high_findings)} high-severity finding(s) — {descriptions}",
        )

    if scan_result.verdict == "warn":
        return (
            True,
            f"Warning: {scan_result.summary}. Proceed with caution.",
        )

    return (True, "Scan passed with no findings.")
