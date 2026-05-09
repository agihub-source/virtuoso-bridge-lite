#!/bin/bash
# Print the lines to add to ~/.cdsinit so Virtuoso loads the AI Bridge menu.
# No pip install required — just run this script once and paste the output.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IL="$ROOT/src/virtuoso_bridge/mcp/resources/mcp_gui.il"

echo "=========================================="
echo "Add these lines to ~/.cdsinit:"
echo "=========================================="
echo ""
echo "RBAIProjectRoot = \"$ROOT\""
echo "load(\"$IL\")"
echo ""
echo "=========================================="
echo "Then install the Python dependencies (one-time):"
echo "=========================================="
echo ""
echo "pip install mcp pydantic python-dotenv pyyaml"
