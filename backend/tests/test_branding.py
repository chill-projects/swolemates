"""The app's mark is declared in three places that can drift apart.

`frontend/public/` holds the files, `frontend/index.html` and the web manifest point the
browser tab at them, and MCP's `serverInfo.icons` points Claude at them over HTTP. A
rename on any one side degrades silently: the fetcher gets a miss and renders whatever
mark it can derive from the hostname instead — which on *.up.railway.app is Railway's.
Nothing fails, so pin the sides together here.
"""

import pathlib
from urllib.parse import urlsplit

from app.config import get_settings
from app.main import ROOT_ASSETS
from app.mcp._icons import app_icons
from app.mcp.server import mcp

FRONTEND_PUBLIC = pathlib.Path(__file__).resolve().parents[2] / "frontend" / "public"


def test_mcp_advertises_icons_and_a_website() -> None:
    """Without these, `initialize` gives Claude nothing to render the connector with."""
    origin = get_settings().public_url.rstrip("/")

    assert mcp.website_url == origin
    assert mcp.icons, "serverInfo.icons is empty — Claude falls back to a hostname mark"
    assert {icon.sizes and icon.sizes[0] for icon in mcp.icons} == {"192x192", "512x512"}


def test_mcp_icons_are_absolute_urls_on_the_public_origin() -> None:
    """A relative src has no origin to resolve against on the client, and an icon is
    fetched before the OAuth handshake, so it has to live outside the /mcp mount."""
    origin = get_settings().public_url.rstrip("/")

    for icon in mcp.icons:
        assert icon.src.startswith(f"{origin}/"), icon.src
        assert not urlsplit(icon.src).path.startswith("/mcp"), icon.src


def test_mcp_icons_name_files_the_frontend_actually_ships() -> None:
    """The rename guard: these paths are served out of the SPA build, whose inputs are
    frontend/public. A file renamed there and not here 404s in Claude only."""
    for icon in mcp.icons:
        name = urlsplit(icon.src).path.lstrip("/")
        assert (FRONTEND_PUBLIC / name).is_file(), f"{name} is not in frontend/public"


def test_mcp_icon_paths_are_guarded_against_the_spa_catch_all() -> None:
    """ROOT_ASSETS is what stops a missing icon being answered with index.html at 200 —
    a success the fetcher then renders as a fallback mark. Every advertised icon needs
    to be in it, or the guard doesn't cover the path Claude fetches."""
    for icon in mcp.icons:
        assert urlsplit(icon.src).path.lstrip("/") in ROOT_ASSETS, icon.src


async def test_every_ui_component_carries_the_app_mark() -> None:
    """The ui:// resources are the MCP Apps Claude renders as embedded components, and
    each gets its own icon in the host's UI — the server's icons don't cover them. A
    component registered without one falls back the same way the connector did."""
    components = [r for r in await mcp.list_resources() if str(r.uri).startswith("ui://")]

    assert components, "no ui:// components registered"
    for resource in components:
        assert [icon.src for icon in resource.icons or []] == [icon.src for icon in app_icons()], (
            resource.uri
        )
