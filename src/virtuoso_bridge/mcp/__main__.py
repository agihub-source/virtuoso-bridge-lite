import argparse
from .server import run

p = argparse.ArgumentParser(description="virtuoso-bridge MCP server")
p.add_argument("--port", type=int, default=8765)
p.add_argument("--log-path", default="/tmp/vb_mcp_log.jsonl")
args = p.parse_args()
run(port=args.port, log_path=args.log_path)
