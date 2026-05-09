"""MCP tools — 11 tools wrapping VirtuosoClient and SpectreSimulator."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from .server import mcp, get_client, get_spectre
from . import log_writer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dump(obj: Any) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(), default=str)
    if isinstance(obj, (dict, list)):
        return json.dumps(obj, default=str)
    return str(obj)


def _log_call(tool: str, **kwargs: Any) -> float:
    args_summary = " ".join(f"{k}={v!r}" for k, v in kwargs.items() if v is not None)
    log_writer.append({
        "type": "tool_call",
        "tool": tool,
        "args_summary": args_summary,
        "display": f"[{time.strftime('%H:%M:%S')}] > {tool}  {args_summary}",
    })
    return time.time()


def _log_result(tool: str, t0: float, ok: bool = True, detail: str = "") -> None:
    elapsed = (time.time() - t0) * 1000
    status = "OK" if ok else "ERR"
    log_writer.append({
        "type": "tool_result",
        "tool": tool,
        "ok": ok,
        "elapsed_ms": elapsed,
        "display": f"[{time.strftime('%H:%M:%S')}]   {status} {detail}  {elapsed:.0f}ms",
    })


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def execute_skill(code: str) -> str:
    """Execute arbitrary SKILL code in Virtuoso and return the result."""
    client = get_client()
    t0 = _log_call("execute_skill", code=code[:80])
    result = await asyncio.to_thread(client.execute_skill, code)
    _log_result("execute_skill", t0)
    return _dump(result)


@mcp.tool()
async def list_windows() -> str:
    """List all currently open Virtuoso windows (lib, cell, view)."""
    client = get_client()
    t0 = _log_call("list_windows")
    windows = await asyncio.to_thread(client.list_windows)
    _log_result("list_windows", t0, detail=f"{len(windows)} window(s)")
    return json.dumps(windows)


@mcp.tool()
async def get_current_design() -> str:
    """Return the lib, cell, and view of the active Virtuoso cellview."""
    client = get_client()
    t0 = _log_call("get_current_design")
    lib, cell, view = await asyncio.to_thread(client.get_current_design)
    _log_result("get_current_design", t0, detail=f"{lib}/{cell}/{view}")
    return json.dumps({"lib": lib, "cell": cell, "view": view})


@mcp.tool()
async def open_cellview(lib: str, cell: str, view: str = "schematic") -> str:
    """Open a cellview in Virtuoso, reusing an existing window if already open."""
    from virtuoso_bridge.virtuoso.ops import bind_or_open_cell_view
    client = get_client()
    t0 = _log_call("open_cellview", lib=lib, cell=cell, view=view)
    skill_expr = "cv = " + bind_or_open_cell_view(lib, cell, view=view)
    result = await asyncio.to_thread(client.execute_skill, skill_expr)
    _log_result("open_cellview", t0, detail=f"{lib}/{cell}/{view}")
    return _dump(result)


@mcp.tool()
async def read_schematic(lib: str | None = None, cell: str | None = None) -> str:
    """
    Read schematic topology: instances, nets, pins, notes.

    If lib and cell are omitted, reads the currently active cellview.
    """
    from virtuoso_bridge.virtuoso.schematic.reader import read_schematic as _read
    client = get_client()
    t0 = _log_call("read_schematic", lib=lib, cell=cell)
    data = await asyncio.to_thread(_read, client, lib, cell)
    ninst = len(data.get("instances", []))
    nnets = len(data.get("nets", []))
    _log_result("read_schematic", t0, detail=f"{ninst} inst  {nnets} nets")
    return json.dumps(data, default=str)


@mcp.tool()
async def edit_schematic(
    lib: str,
    cell: str,
    commands: list[str],
    view: str = "schematic",
    timeout: int = 120,
) -> str:
    """
    Batch-edit a schematic: open cellview, run SKILL commands, schCheck, save.

    Each element of `commands` must be a SKILL expression string.
    The cellview is opened (or reused), commands are batched, then
    schCheck() and dbSave() are called automatically on exit.
    """
    from virtuoso_bridge.virtuoso.schematic.editor import SchematicEditor
    client = get_client()
    t0 = _log_call("edit_schematic", lib=lib, cell=cell, ncmds=len(commands))

    def _run() -> None:
        with SchematicEditor(client, lib, cell, view=view, timeout=timeout) as sch:
            for cmd in commands:
                sch.add(cmd)

    try:
        await asyncio.to_thread(_run)
        _log_result("edit_schematic", t0, ok=True)
        return "schematic saved"
    except Exception as exc:
        _log_result("edit_schematic", t0, ok=False, detail=str(exc))
        raise


@mcp.tool()
async def edit_layout(
    lib: str,
    cell: str,
    commands: list[str],
    view: str = "layout",
    timeout: int = 120,
) -> str:
    """
    Batch-edit a layout: open cellview, run SKILL commands, save.

    Each element of `commands` must be a SKILL expression string.
    The cellview is opened (or reused), commands are batched, then
    dbSave() is called automatically on exit.
    """
    from virtuoso_bridge.virtuoso.layout.editor import LayoutEditor
    client = get_client()
    t0 = _log_call("edit_layout", lib=lib, cell=cell, ncmds=len(commands))

    def _run() -> None:
        with LayoutEditor(client, lib, cell, view=view, timeout=timeout) as lay:
            for cmd in commands:
                lay.add(cmd)

    try:
        await asyncio.to_thread(_run)
        _log_result("edit_layout", t0, ok=True)
        return "layout saved"
    except Exception as exc:
        _log_result("edit_layout", t0, ok=False, detail=str(exc))
        raise


@mcp.tool()
async def save_cellview() -> str:
    """Save the currently active Virtuoso cellview."""
    from virtuoso_bridge.virtuoso.ops import save_current_cellview
    client = get_client()
    t0 = _log_call("save_cellview")
    result = await asyncio.to_thread(client.execute_skill, save_current_cellview())
    _log_result("save_cellview", t0)
    return _dump(result)


@mcp.tool()
async def screenshot(target: str = "ciw", output: str | None = None) -> str:
    """
    Take a screenshot of a Virtuoso window.

    Args:
        target: "ciw" for the CIW, a window index (e.g. "1"), or "all".
        output: local path to save the PNG. If omitted, a temp path is used.
    """
    client = get_client()
    t0 = _log_call("screenshot", target=target, output=output)
    out_path = Path(output) if output else None
    result = await asyncio.to_thread(client.screenshot, out_path, target=target)
    _log_result("screenshot", t0)
    return _dump(result)


@mcp.tool()
async def run_spectre(netlist: str, params: dict | None = None) -> str:
    """
    Run a Spectre simulation.

    Args:
        netlist: absolute path to the netlist file on the Virtuoso host.
        params: optional dict of overriding simulation parameters.
    """
    spectre = get_spectre()
    t0 = _log_call("run_spectre", netlist=netlist)
    result = await asyncio.to_thread(spectre.run_simulation, Path(netlist), params or {})
    _log_result("run_spectre", t0, ok=getattr(result, "success", True))
    return _dump(result)


@mcp.tool()
async def load_il(path: str) -> str:
    """Load a SKILL .il file in Virtuoso (equivalent to CIW `load("path")`)."""
    client = get_client()
    t0 = _log_call("load_il", path=path)
    result = await asyncio.to_thread(client.load_il, path)
    _log_result("load_il", t0)
    return _dump(result)
