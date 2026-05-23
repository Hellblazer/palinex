# SPDX-License-Identifier: Apache-2.0
"""palinex MCP server — exposes ``render_surface`` for Claude Code (or any
MCP host) to wrap a2ui v0.9 payloads as inline UI resources.

Entry point: ``python -m palinex.mcp`` (or, with [mcp] extra installed,
the FastMCP server starts via the stdio transport).
"""
from __future__ import annotations

from palinex.mcp.server import mcp, render_surface

__all__ = ["mcp", "render_surface"]
