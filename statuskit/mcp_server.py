"""STATUSKIT MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from statuskit.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-statuskit[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-statuskit[mcp]'")
        return 1
    app = FastMCP("statuskit")

    @app.tool()
    def statuskit_scan(target: str) -> str:
        """Self-hosted status page with incident timeline and subscribers. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
