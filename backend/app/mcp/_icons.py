"""The app's mark, shared by everything MCP declares an icon on.

Kept separate from server.py for the same reason _resources.py is: the tool modules
that register the ui:// components import app.mcp.server to get the decorator, and
server.py imports them back at startup, so anything they both need lives in a leaf
module rather than in either end of that cycle.

Declaring nothing is what made Claude render Railway's logo: with no icons a host
falls back to whatever it can derive from the hostname, which on *.up.railway.app is
Railway. These are the same PNGs the browser tab and the web manifest use, served from
PUBLIC_URL by the SPA static handler — one file per size, so the mark only ever changes
in one place.

URLs rather than data: URIs deliberately: the transport is stateless, so a client is
free to re-`initialize` (and re-list) on every request, and inlining ~14 kB of base64
into each of those responses is real weight for an image the client caches after one
fetch. Both paths are public — an icon is fetched before the OAuth handshake, so an
authenticated URL would render as a broken image.
"""

from mcp.types import Icon

from app.config import get_settings


def app_icons() -> list[Icon]:
    """The Swolemates mark, at the two sizes the frontend ships as its own icons."""
    origin = get_settings().public_url.rstrip("/")
    return [
        Icon(src=f"{origin}/icon-192.png", mimeType="image/png", sizes=["192x192"]),
        Icon(src=f"{origin}/icon-512.png", mimeType="image/png", sizes=["512x512"]),
    ]
