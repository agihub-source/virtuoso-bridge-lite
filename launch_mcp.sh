#!/bin/bash
# Start the MCP server directly without pip install.
# Usage: ./launch_mcp.sh [--port 8765] [--log-path /tmp/vb_mcp_log.jsonl]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="$SCRIPT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m virtuoso_bridge.mcp "$@"
