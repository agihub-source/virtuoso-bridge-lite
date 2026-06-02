"""SKILL Lint — pre-flight checks for SKILL code before it round-trips to Virtuoso.

Two layers, both reachable from :class:`~virtuoso_bridge.VirtuosoClient` and
the ``virtuoso-bridge lint`` CLI command:

* **Layer 1 — local structural lint** (this module): pure-Python, offline,
  instant.  Catches the failures that produce the most cryptic Virtuoso
  errors — unbalanced parentheses, unterminated strings, unterminated block
  comments — *before* the code is ever sent.  No running Virtuoso required.

* **Layer 2 — Cadence ``sklint``** (:mod:`.sklint`): routes the file through
  the real Cadence SKILL Lint program on the live daemon for semantic checks
  (undefined variables, suspicious usage, style).  Opt-in via ``deep=True``;
  degrades to Layer 1 when no daemon is available.

Usage::

    from virtuoso_bridge.virtuoso.skill_lint import lint_text, lint_file

    report = lint_text('let((x) x = foo(1 2)')   # missing ')'
    if not report.ok:
        print(report.format())

The local checker is intentionally **conservative**: it only reports problems
it is confident about, so it never cries wolf on valid SKILL (including the
super-bracket ``]`` form, e.g. ``foo(bar(x]``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Severity levels, ordered by increasing seriousness.
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"


@dataclass
class LintFinding:
    """A single lint result."""

    severity: str
    message: str
    line: int | None = None
    column: int | None = None
    code: str = ""
    source: str = "structural"  # "structural" (Layer 1) or "sklint" (Layer 2)

    def to_dict(self) -> dict:
        return {
            "severity": self.severity,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "source": self.source,
        }

    def format(self) -> str:
        loc = ""
        if self.line is not None:
            loc = f"{self.line}:{self.column}: " if self.column is not None else f"{self.line}: "
        code = f"[{self.code}] " if self.code else ""
        return f"{loc}{self.severity.upper()}: {code}{self.message} ({self.source})"


@dataclass
class LintReport:
    """Aggregate of lint findings for one piece of SKILL."""

    findings: list[LintFinding] = field(default_factory=list)
    path: str | None = None
    sklint_raw: str | None = None  # full .lnt text, when Layer 2 ran
    notes: list[str] = field(default_factory=list)  # e.g. "sklint skipped: no daemon"

    @property
    def errors(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_ERROR]

    @property
    def warnings(self) -> list[LintFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_WARNING]

    @property
    def ok(self) -> bool:
        """True when there are no error-severity findings."""
        return not self.errors

    def add(self, finding: LintFinding) -> None:
        self.findings.append(finding)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "findings": [f.to_dict() for f in self.findings],
            "notes": self.notes,
            "sklint_raw": self.sklint_raw,
        }

    def format(self) -> str:
        if not self.findings and not self.notes:
            head = f"{self.path}: " if self.path else ""
            return f"{head}OK — no lint findings"
        lines: list[str] = []
        if self.path:
            lines.append(f"{self.path}:")
        for f in self.findings:
            lines.append(f"  {f.format()}")
        for n in self.notes:
            lines.append(f"  note: {n}")
        lines.append(
            f"  -> {len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Layer 1: local structural checker
# ---------------------------------------------------------------------------

def lint_text(code: str) -> LintReport:
    """Run local structural lint on a SKILL string.

    Detects, with high confidence (no false positives on valid SKILL):

    * unterminated string literals (``"`` …),
    * unterminated block comments (``/* `` …),
    * unbalanced round brackets — extra ``)`` or unclosed ``(`` — while
      honouring SKILL's super-bracket ``]`` (which closes all open ``(``
      back to the matching ``[``).

    Returns a :class:`LintReport`.
    """
    report = LintReport()

    if not code.strip():
        report.add(LintFinding(SEVERITY_WARNING, "empty SKILL input", code="empty"))
        return report

    # Stack of (char, line, col) for open '(' and '['.
    stack: list[tuple[str, int, int]] = []
    state = "normal"  # normal | string | line_comment | block_comment
    line = 1
    col = 0
    string_start: tuple[int, int] | None = None
    block_start: tuple[int, int] | None = None
    i = 0
    n = len(code)

    while i < n:
        ch = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if ch == "\n":
            line += 1
            col = 0
            if state == "line_comment":
                state = "normal"
            i += 1
            continue
        col += 1

        if state == "string":
            if ch == "\\":  # skip escaped char (\" \\ \n ...)
                i += 2
                col += 1
                continue
            if ch == '"':
                state = "normal"
                string_start = None
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "normal"
                block_start = None
                i += 2
                col += 1
                continue
            i += 1
            continue

        if state == "line_comment":
            i += 1
            continue

        # --- normal state ---
        if ch == '"':
            state = "string"
            string_start = (line, col)
            i += 1
            continue
        if ch == ";":
            state = "line_comment"
            i += 1
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            block_start = (line, col)
            i += 2
            col += 1
            continue
        if ch == "(" or ch == "[":
            stack.append((ch, line, col))
        elif ch == ")":
            if not stack:
                report.add(LintFinding(
                    SEVERITY_ERROR, "unbalanced ')' — no matching '('",
                    line=line, column=col, code="paren"))
            elif stack[-1][0] == "[":
                report.add(LintFinding(
                    SEVERITY_ERROR, "')' closing a '[' — bracket mismatch",
                    line=line, column=col, code="paren"))
                stack.pop()
            else:
                stack.pop()
        elif ch == "]":
            # Super-right-bracket: close back to (and including) the nearest
            # '['; if there is no '[', it closes all currently open '('.
            if not stack:
                report.add(LintFinding(
                    SEVERITY_ERROR, "unbalanced ']' — nothing open to close",
                    line=line, column=col, code="paren"))
            else:
                while stack and stack[-1][0] != "[":
                    stack.pop()
                if stack:  # pop the matching '['
                    stack.pop()
        i += 1

    if state == "string" and string_start is not None:
        report.add(LintFinding(
            SEVERITY_ERROR, "unterminated string literal",
            line=string_start[0], column=string_start[1], code="string"))
    if state == "block_comment" and block_start is not None:
        report.add(LintFinding(
            SEVERITY_ERROR, "unterminated block comment '/* ... */'",
            line=block_start[0], column=block_start[1], code="comment"))

    for opener, oline, ocol in stack:
        report.add(LintFinding(
            SEVERITY_ERROR,
            f"unclosed '{opener}' — missing matching "
            f"'{')' if opener == '(' else ']'}'",
            line=oline, column=ocol, code="paren"))

    return report


def lint_file(path: str | Path) -> LintReport:
    """Run local structural lint on a ``.il`` file. Sets ``report.path``."""
    p = Path(path)
    report = lint_text(p.read_text(encoding="utf-8", errors="replace"))
    report.path = str(p)
    return report
