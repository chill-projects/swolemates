"""ui:// resource URIs shared across tool modules.

Kept separate from nutrition_tools.py (which owns the resource registration and bundle
path) so a second tool module — food_facts_tools.py, associating search_food_facts with
the same nutrition UI — can reference the URI without importing nutrition_tools.py
directly: that module imports app.mcp.server, and server.py imports both tool modules
at startup, so a direct cross-import here would be circular.
"""

NUTRITION_UI_URI = "ui://swolemates/nutrition-day.html"
