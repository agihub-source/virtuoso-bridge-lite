import sys
import importlib.resources


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        pkg = importlib.resources.files("virtuoso_bridge.mcp.resources")
        path = pkg.joinpath("mcp_gui.il")
        print(f'load("{path}")')
        print()
        print("Add the line above to ~/.cdsinit so the AI Bridge menu loads automatically.")
    else:
        print("Usage: virtuoso-bridge-mcp init")
        print()
        print("Commands:")
        print("  init   Print the SKILL load() line to add to ~/.cdsinit")
