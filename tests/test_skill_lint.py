from __future__ import annotations

import json

from virtuoso_bridge.cli import main
from virtuoso_bridge.virtuoso.skill_lint import (
    SEVERITY_ERROR,
    SEVERITY_WARNING,
    lint_text,
    lint_file,
)
from virtuoso_bridge.virtuoso.skill_lint.sklint import (
    build_sklint_skill,
    parse_lnt,
)


# --- Layer 1: structural checker -------------------------------------------

def test_balanced_code_is_ok():
    report = lint_text('let((x) x = plus(1 2) printf("x=%d\\n" x))')
    assert report.ok
    assert report.errors == []


def test_missing_close_paren_flagged():
    report = lint_text("let((x) x = foo(1 2)")  # one '(' unclosed
    assert not report.ok
    codes = [f.code for f in report.errors]
    assert "paren" in codes
    # the earliest unclosed opener is the outer let(
    assert any("unclosed '('" in f.message for f in report.errors)


def test_extra_close_paren_flagged():
    report = lint_text("foo(1 2))")
    assert not report.ok
    assert any("unbalanced ')'" in f.message for f in report.errors)


def test_unterminated_string_flagged():
    report = lint_text('printf("hello)')
    assert not report.ok
    assert any(f.code == "string" for f in report.errors)


def test_unterminated_block_comment_flagged():
    report = lint_text("a = 1 /* open comment\nb = 2")
    assert not report.ok
    assert any(f.code == "comment" for f in report.errors)


def test_brackets_inside_string_ignored():
    # the unbalanced '(' lives inside a string literal -> not a real problem
    report = lint_text('printf("a ( b )")')
    assert report.ok


def test_parens_in_line_comment_ignored():
    report = lint_text("foo(1 2) ; trailing ) ) ) comment")
    assert report.ok


def test_super_bracket_closes_open_parens():
    # ']' closes both open '(' — valid SKILL, must not be flagged
    report = lint_text("a = foo(bar(x]")
    assert report.ok


def test_empty_input_is_warning_not_error():
    report = lint_text("   \n  ")
    assert report.ok  # warning only
    assert any(f.severity == SEVERITY_WARNING for f in report.findings)


def test_lint_file_sets_path(tmp_path):
    f = tmp_path / "snippet.il"
    f.write_text("foo(1 2)")
    report = lint_file(f)
    assert report.path == str(f)
    assert report.ok


# --- Layer 2: sklint pure helpers ------------------------------------------

def test_build_sklint_skill():
    skill = build_sklint_skill("/tmp/x.il", "/tmp/x.il.lnt")
    assert skill == 'sklint(?file "/tmp/x.il" ?outputFile "/tmp/x.il.lnt")'


def test_parse_lnt_classifies_severity_and_line():
    text = (
        "SKILL Lint Report\n"
        "----------------\n"
        "WARNING (SKILL-1001): undefined variable foo at line 12\n"
        "ERROR (SKILL-2002): syntax problem at line 5\n"
        "INFO: 2 issues found\n"
        "\n"
    )
    findings = parse_lnt(text)
    sevs = {f.severity for f in findings}
    assert SEVERITY_ERROR in sevs
    assert SEVERITY_WARNING in sevs
    by_sev = {f.severity: f for f in findings}
    assert by_sev[SEVERITY_WARNING].line == 12
    assert by_sev[SEVERITY_WARNING].code == "SKILL-1001"
    assert by_sev[SEVERITY_ERROR].line == 5
    assert all(f.source == "sklint" for f in findings)


def test_parse_lnt_ignores_non_finding_lines():
    assert parse_lnt("just a header\n=====\n") == []


# --- CLI -------------------------------------------------------------------

def test_cli_lint_clean_file_exits_0(tmp_path, capsys):
    f = tmp_path / "ok.il"
    f.write_text('printf("ok\\n")')
    rc = main(["lint", str(f)])
    assert rc == 0


def test_cli_lint_broken_file_exits_1(tmp_path, capsys):
    f = tmp_path / "bad.il"
    f.write_text("foo(1 2")  # unclosed
    rc = main(["lint", str(f)])
    assert rc == 1


def test_cli_lint_missing_file_exits_2(capsys):
    rc = main(["lint", "/no/such/file.il"])
    assert rc == 2


def test_cli_lint_json_output(tmp_path, capsys):
    f = tmp_path / "bad.il"
    f.write_text("foo(1 2")
    rc = main(["lint", str(f), "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 1
    assert payload["ok"] is False
    assert payload["error_count"] >= 1


def test_cli_lint_strict_fails_on_warning(tmp_path, capsys):
    f = tmp_path / "empty.il"
    f.write_text("   ")
    assert main(["lint", str(f)]) == 0          # warning only -> ok
    assert main(["lint", str(f), "--strict"]) == 1


# --- --lint guard on load / eval (blocks before any network) ---------------

def test_load_lint_guard_blocks_broken_file(tmp_path, capsys):
    f = tmp_path / "bad.il"
    f.write_text("foo(1 2")  # unclosed — must abort before connecting
    rc = main(["load", str(f), "--lint"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "structural errors" in err
    assert "not loading" in err


def test_eval_lint_guard_blocks_broken_snippet(capsys):
    rc = main(["eval", "foo(1 2", "--lint"])  # unclosed paren
    err = capsys.readouterr().err
    assert rc == 1
    assert "not evaluating" in err
