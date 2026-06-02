"""Layer 2 — Cadence ``sklint`` integration.

The real Cadence SKILL Lint program is exposed as a SKILL function callable
from the CIW::

    sklint(?file "design.il" ?outputFile "design.il.lnt")

It examines SKILL for issues that normal testing misses (undefined
variables, suspicious usage, style) and writes its findings to the
``?outputFile``.  This module holds the two **pure** pieces — building the
SKILL call and parsing the ``.lnt`` output — so they are testable without a
running Virtuoso.  Orchestration (upload → execute_skill → download →
parse) lives in :meth:`VirtuosoClient.lint_il`.
"""

from __future__ import annotations

import re

from . import LintFinding, SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING


def build_sklint_skill(remote_il: str, remote_lnt: str) -> str:
    """Return the SKILL expression that lints *remote_il* into *remote_lnt*.

    Both paths are emitted verbatim inside double quotes; callers pass
    already-resolved POSIX paths (no embedded quotes), matching how the
    rest of the bridge builds ``load("...")`` commands.
    """
    return f'sklint(?file "{remote_il}" ?outputFile "{remote_lnt}")'


# sklint emits free-form text whose exact shape varies across Cadence
# releases.  Rather than over-fit one version's layout, classify each line by
# the severity keyword it carries and pull a line number when one is present;
# the full raw text is always preserved on the report for transparency.
_SEVERITY_KEYWORDS = (
    (SEVERITY_ERROR, re.compile(r"\bERROR\b", re.IGNORECASE)),
    (SEVERITY_WARNING, re.compile(r"\b(WARN(?:ING)?)\b", re.IGNORECASE)),
    (SEVERITY_INFO, re.compile(r"\b(INFO|NOTE|HINT)\b", re.IGNORECASE)),
)
# e.g. "... at line 42", "line 42:", "design.il:42:", "(line 42)"
_LINE_RE = re.compile(r"(?:\bline[\s:]*|:)(\d+)\b", re.IGNORECASE)
# e.g. "(SKILL-1234)" or "SKILL Lint warning W123"
_CODE_RE = re.compile(r"\(([A-Z][A-Z0-9]+-\d+)\)|\b([WE]\d{2,})\b")


def parse_lnt(text: str) -> list[LintFinding]:
    """Parse Cadence ``.lnt`` output into structured findings.

    Tolerant by design: any line carrying a severity keyword becomes a
    finding; lines without one are ignored (they are headers / summaries /
    blank).  Severity defaults to WARNING when a line looks like a finding
    but the keyword is ambiguous.
    """
    findings: list[LintFinding] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        severity = None
        for sev, pat in _SEVERITY_KEYWORDS:
            if pat.search(line):
                severity = sev
                break
        if severity is None:
            continue  # not a finding line (header, summary, separator, ...)

        line_no: int | None = None
        m = _LINE_RE.search(line)
        if m:
            line_no = int(m.group(1))

        code = ""
        cm = _CODE_RE.search(line)
        if cm:
            code = cm.group(1) or cm.group(2) or ""

        findings.append(LintFinding(
            severity=severity,
            message=line,
            line=line_no,
            code=code,
            source="sklint",
        ))
    return findings
