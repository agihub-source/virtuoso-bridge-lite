"""MCP server: FastMCP + VirtuosoClient lifespan."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from virtuoso_bridge import VirtuosoClient

try:
    from virtuoso_bridge.spectre import SpectreSimulator
    _HAS_SPECTRE = True
except Exception:
    SpectreSimulator = None  # type: ignore[assignment,misc]
    _HAS_SPECTRE = False

from . import log_writer

_client: VirtuosoClient | None = None
_spectre: object | None = None


def get_client() -> VirtuosoClient:
    if _client is None:
        raise RuntimeError("VirtuosoClient not initialized — server not started")
    return _client


def get_spectre():
    if _spectre is None:
        raise RuntimeError("SpectreSimulator not available")
    return _spectre


@asynccontextmanager
async def lifespan(server):
    global _client, _spectre
    _client = VirtuosoClient.local()
    if _HAS_SPECTRE:
        _spectre = SpectreSimulator.local(work_dir=Path("/tmp/vb_spectre"))
    log_writer.append({"type": "server_start", "display": "[server] MCP server started"})
    try:
        yield
    finally:
        log_writer.append({"type": "server_stop", "display": "[server] MCP server stopped"})
        _client.close()
        if _spectre is not None and hasattr(_spectre, "close"):
            _spectre.close()
        _client = None
        _spectre = None


mcp = FastMCP("virtuoso-bridge", lifespan=lifespan)

# Import tools last — triggers @mcp.tool() decorator registration
from . import tools as _tools_module  # noqa: F401, E402


def run(port: int = 8765, log_path: str = "/tmp/vb_mcp_log.jsonl") -> None:
    log_writer.init(log_path)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
