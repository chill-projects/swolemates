"""Serves skills/swolemates/ at skill://swolemates/* via FastMCP's SkillProvider."""

from pathlib import Path

from fastmcp.server.providers.skills import SkillProvider

from app.mcp.server import mcp

mcp.add_provider(SkillProvider(Path(__file__).parent / "skills" / "swolemates"))
