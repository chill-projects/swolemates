"""The `swolemates` skill — standing guidance for how a connected model helps users.

Served over MCP via FastMCP's SkillProvider: the skill body at
skill://swolemates/SKILL.md plus a skill://swolemates/_manifest file listing. Unlike the
`coach` prompt (user-invoked, full coaching persona), the skill is discoverable by any
host that reads skills up front and covers the whole surface: which tool fits which
task, look-before-asking, logging etiquette, boundaries. Guidance only — permissions and
behavior stay in the service layer.
"""

from pathlib import Path

from fastmcp.server.providers.skills import SkillProvider

from app.mcp.server import mcp

mcp.add_provider(SkillProvider(Path(__file__).parent / "skills" / "swolemates"))
