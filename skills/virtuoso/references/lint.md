# SKILL Lint

Catch broken SKILL **before** it round-trips to Virtuoso, where errors are
cryptic (a single missing `)` surfaces as an opaque CIW failure). Two layers,
both reachable from the CLI and the Python API.

| Layer | What it checks | Needs Virtuoso? | Entry |
|---|---|---|---|
| **1 — structural** (default) | balanced parens (incl. super-bracket `]`), terminated string literals, terminated block comments | No — pure Python, offline, instant | `virtuoso-bridge lint FILE.il` / `lint_text()` / `lint_file()` |
| **2 — Cadence `sklint`** (`--deep`) | undefined variables, suspicious usage, style — the real Cadence SKILL Lint | Yes — runs on the live daemon | `virtuoso-bridge lint FILE.il --deep` / `client.lint_il(path, deep=True)` |

Layer 1 is intentionally **conservative**: it only reports problems it is
confident about, so it never false-positives on valid SKILL — including the
super-bracket form `foo(bar(x]` (where `]` closes both open `(`).

## CLI

```bash
# Layer 1 — offline structural check
virtuoso-bridge lint myscript.il
#   myscript.il:
#     12:4: ERROR: [paren] unclosed '(' — missing matching ')' (structural)
#     -> 1 error(s), 0 warning(s)        # exit 1

# Layer 2 — also run Cadence sklint on the daemon
virtuoso-bridge lint myscript.il --deep

# Machine-readable
virtuoso-bridge lint myscript.il --json

# Treat warnings as failures too
virtuoso-bridge lint myscript.il --strict
```

Exit codes: `0` clean · `1` error-severity findings (or any finding with
`--strict`) · `2` file not found.

If `--deep` is requested but no daemon is reachable, the deep pass is skipped
with a note and the Layer-1 findings still stand (exit code unaffected).

## Pre-send guard on `load` / `eval`

Add `--lint` to run the Layer-1 structural check first and **refuse to send**
on structural errors — a cheap guard against shipping a broken paren to the
CIW:

```bash
virtuoso-bridge load myscript.il --lint     # lints the file, aborts on errors
virtuoso-bridge eval 'foo(bar(1 2)' --lint  # lints the snippet (pre-progn-wrap)
```

Findings print to **stderr** so stdout stays a clean `VirtuosoResult` JSON
contract. Only error-severity findings block; warnings are advisory. Re-run
without `--lint` to send anyway.

## Python API

```python
from virtuoso_bridge.virtuoso.skill_lint import lint_text, lint_file

report = lint_text('let((x) x = foo(1 2)')   # missing ')'
if not report.ok:                            # ok == no error-severity findings
    print(report.format())
    for f in report.errors:                  # LintFinding: severity/message/line/column/code/source
        ...

report.to_dict()    # JSON-friendly: {path, ok, error_count, warning_count, findings, notes, sklint_raw}
```

Deep (semantic) lint via the live daemon:

```python
client = VirtuosoClient.from_env()
report = client.lint_il("myscript.il", deep=True)
# Layer-1 findings + parsed sklint findings (source="sklint");
# report.sklint_raw holds the full .lnt text; report.notes explains any skip.
```

## How Layer 2 works (`sklint`)

Cadence ships SKILL Lint as a CIW-callable function. The bridge calls it on
the daemon and parses the output file:

```skill
sklint(?file "design.il" ?outputFile "design.il.lnt")
```

The bridge uploads the `.il` (SSH mode), runs the call via `execute_skill`,
downloads the `.lnt`, and parses it into structured findings. The `.lnt`
format varies across Cadence releases, so parsing is **tolerant**: lines
carrying a severity keyword (`ERROR`/`WARNING`/`INFO`) become findings, line
numbers and `(SKILL-NNNN)` codes are extracted when present, and the full raw
`.lnt` text is always preserved on `report.sklint_raw`.

## Boundaries

- Layer 1 is **structural only** — it does not know SKILL semantics (undefined
  functions, type errors). Use `--deep` for that.
- `sklint` is **file-oriented** and runs in the single-threaded CIW; it needs a
  running Virtuoso and briefly occupies the SKILL channel.
- `sklint` availability and exact `.lnt` schema depend on the Cadence version.
