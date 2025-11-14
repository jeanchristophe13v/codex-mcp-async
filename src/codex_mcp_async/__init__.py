"""
Codex MCP Async Package

Asynchronous MCP wrapper for OpenAI Codex CLI with context filtering.
Enables Claude Code to call Codex (GPT-5) asynchronously, saving 95% context tokens.
"""

__version__ = "0.2.1"
__author__ = "jeanchristophe13v"
__email__ = ""
__description__ = "Asynchronous MCP wrapper for OpenAI Codex CLI with context filtering"

from .server import main

__all__ = ["main"]