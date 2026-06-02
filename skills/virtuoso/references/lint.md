# SKILL Lint

Catch broken SKILL **before** it round-trips to Virtuoso, where errors are
cryptic (a single missing `)` surfaces as an opaque CIW failure). Two layers,
both reachable from the CLI and the Python API.

| Layer | What it checks | Needs Virtuoso? | Entry |
|---|---|---|---|
| **1 — structural** (default) | balanced parens (incl. super-bracket `]`), terminated string literals, terminated block comments | No — pure Python, offline, instant | `virtuoso-bridge lint FILE.il` / `lint_text()` / `lint_file()` |
| **2 — Cadence `sklint`** (`--deep`) | undefined variables, suspicious usage, style — the real Cadence SKILL Lint | No running Virtuoso — just **SSH + a Cadence install** | `virtuoso-bridge lint FILE.il --deep` / `client.lint_il(path, deep=True)` |

Layer 2 leans on Cadence's own tooling the same way **SKILL Finder** uses the
native `.fnd` database: it locates the standalone `skill` interpreter on the
host (a sibling of the `virtuoso` binary) and drives `sklint` through it over
SSH. No CIW, no loaded bridge daemon.

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

If `--deep` is requested but no Cadence `skill` interpreter is reachable, the
deep pass is skipped with a note and the Layer-1 findings still stand (exit
code unaffected). Set `VB_CADENCE_CSHRC` if `virtuoso`/`skill` is not already
on the remote shell's PATH (same knob as Spectre and SKILL Finder).

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

## How Layer 2 works (native `skill` interpreter)

Cadence ships a standalone SKILL interpreter — `<install>/tools/dfII/bin/skill`,
a sibling of the `virtuoso` binary — and SKILL Lint runs in batch through it:

```bash
skill batchLint.il            # batchLint.il: sklint(?file "x.il" ?outputFile "x.lnt") + exit()
```

The bridge (mirroring SKILL Finder's discovery):

1. sources `VB_CADENCE_CSHRC`, runs `which virtuoso`, takes the sibling `skill`;
2. uploads the target `.il` + a generated batch script (SSH mode);
3. runs `skill <batch>.il` over the **SSH shell** — no CIW, no bridge daemon;
4. downloads the `.lnt` and parses it.

The `.lnt` format varies across Cadence releases, so parsing is **tolerant**:
lines carrying a severity keyword (`ERROR`/`WARNING`/`INFO`) become findings,
line numbers and `(SKILL-NNNN)` codes are extracted when present, and the full
raw `.lnt` text is always preserved on `report.sklint_raw`.

## Boundaries

- Layer 1 is **structural only** — it does not know SKILL semantics (undefined
  functions, type errors). Use `--deep` for that.
- `sklint` is **file-oriented**; inline snippets are written to a temp `.il`.
- Layer 2 needs SSH reachability + a Cadence install (and license env, via
  `VB_CADENCE_CSHRC` when not already on PATH). It does **not** need a running
  Virtuoso — but the native `skill` interpreter still has Cadence startup cost,
  so it is opt-in (`--deep`), not the default or the `--lint` guard.
- `sklint` availability and exact `.lnt` schema depend on the Cadence version.
