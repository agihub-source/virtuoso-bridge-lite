"""Layer 2 — Cadence ``sklint`` via the native standalone ``skill`` interpreter.

Mirrors the SKILL Finder model: instead of routing through a running CIW
daemon, we locate Cadence's own tooling on the host and drive it directly
over SSH (the same pattern Spectre uses).  Cadence ships a standalone SKILL
interpreter — ``<install>/tools/dfII/bin/skill`` — a sibling of the
``virtuoso`` binary.  SKILL Lint runs in batch through it::

    skill batchLint.il          # batchLint.il calls sklint(?file ... ?outputFile ...)

So linting needs only **SSH + a Cadence install** — no running Virtuoso, no
loaded bridge daemon.

This module holds the pure, testable pieces (discovery script, batch builder,
run-command builder); orchestration (upload → run → download → parse) lives in
:meth:`VirtuosoClient.lint_il`, reusing the bridge's own transport.
"""

from __future__ import annotations

import os
import shlex
from pathlib import Path


def cadence_env_prefix(profile: str | None) -> str:
    """Shell snippet that loads the Cadence environment from VB_CADENCE_CSHRC.

    Same mechanism as SKILL Finder discovery and Spectre status: source the
    (optional) cshrc in a csh sub-shell and re-export PATH / license / CDS
    vars into the current shell.  A no-op when the cshrc is unset.
    """
    suffix = f"_{profile}" if profile else ""
    cadence_cshrc = (
        os.environ.get(f"VB_CADENCE_CSHRC{suffix}", "")
        or os.environ.get("VB_CADENCE_CSHRC", "")
    )
    quoted = shlex.quote(cadence_cshrc)
    return (
        'HOSTNAME=`hostname 2>/dev/null || echo localhost`; export HOSTNAME; '
        f'eval "$(csh -c \'source {quoted}; env\' 2>/dev/null '
        '| grep -E "^(PATH|LM_LICENSE_FILE|CDS)=" '
        '| sed \'s/^/export /\')" 2>/dev/null; '
    )


def discover_script(profile: str | None) -> str:
    """Build the shell script that prints the native ``skill`` binary path.

    Strategy (identical in spirit to SKILL Finder): load the Cadence env,
    ``which virtuoso``, then take its sibling ``skill`` in the same ``bin``
    directory.  Prints the path on success, ``NOTFOUND`` otherwise.
    """
    return (
        f"{cadence_env_prefix(profile)}"
        'v="$(which virtuoso 2>/dev/null)"; '
        'if [ -z "$v" ]; then echo NOTFOUND; exit 0; fi; '
        's="$(dirname "$v")/skill"; '
        'if [ -x "$s" ]; then echo "$s"; else echo NOTFOUND; fi'
    )


def parse_discover_output(stdout: str) -> str | None:
    """Extract the skill-binary path from :func:`discover_script` output."""
    path = (stdout or "").strip().splitlines()[-1].strip() if stdout.strip() else ""
    if not path or path == "NOTFOUND":
        return None
    return path


def discover_skill_binary(runner, profile: str | None = None) -> str | None:
    """Locate the native ``skill`` interpreter on the remote host via SSH."""
    r = runner.run_command(
        f"bash -c {shlex.quote(discover_script(profile))}", timeout=30
    )
    if getattr(r, "returncode", 1) != 0:
        return None
    return parse_discover_output(getattr(r, "stdout", ""))


def discover_skill_binary_local() -> str | None:
    """Locate the native ``skill`` interpreter on the local machine."""
    import shutil

    direct = shutil.which("skill")
    if direct:
        return direct
    virtuoso = shutil.which("virtuoso")
    if virtuoso:
        sib = Path(virtuoso).resolve().parent / "skill"
        if sib.is_file():
            return str(sib)
    return None


def build_batch_il(il_path: str, lnt_path: str) -> str:
    """SKILL batch script: lint *il_path* into *lnt_path*, then exit.

    The trailing ``exit()`` keeps the standalone interpreter from dropping
    into an interactive prompt after the file is read.
    """
    return (
        f'sklint(?file "{il_path}" ?outputFile "{lnt_path}")\n'
        "exit()\n"
    )


def build_run_command(skill_bin: str, batch_il: str, profile: str | None) -> str:
    """Shell command that runs the batch lint through the native interpreter."""
    return (
        f"{cadence_env_prefix(profile)}"
        f"{shlex.quote(skill_bin)} {shlex.quote(batch_il)}"
    )
