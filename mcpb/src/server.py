#!/usr/bin/env python3
"""Palinex MCP server entry point for Claude Desktop .mcpb."""
from __future__ import annotations


def main() -> None:
    from palinex.mcp.server import main as _palinex_main
    _palinex_main()


if __name__ == "__main__":
    main()
