class NotFoundError(Exception):
    """Raised when a row doesn't exist *or* belongs to someone else.

    Deliberately not distinguished — telling a caller that an id exists but isn't theirs
    leaks the existence of other users' rows. Shared across every service module (#3/#4
    architecture review) so the MCP tool adapter (app/mcp/_adapter.py) can catch one
    type regardless of which domain raised it.
    """
