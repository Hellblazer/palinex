# SPDX-License-Identifier: Apache-2.0
"""Entry point for ``python -m palinex.mcp``.

Starts the FastMCP server over stdio. Used by the Claude Code plugin's
.mcp.json to bring up palinex's render_surface tool at session boot.
"""
from __future__ import annotations

from palinex.mcp.server import main

if __name__ == "__main__":
    main()
