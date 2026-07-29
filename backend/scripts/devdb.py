#!/usr/bin/env python
"""Local Postgres for the dev loop, with no Docker and no system install.

`pgserver` ships real PostgreSQL binaries as a Python package and runs them against a
data directory in the repo. Same engine as production, so date/window/JSONB semantics
and Alembic migrations behave the same locally as they do on Railway.

Run it through the Makefile, not directly — pgserver publishes no cp313 wheel, so this
executes in a throwaway 3.12 environment that uv builds on demand:

    make db        # boot it, print the URL
    make db-stop   # shut it down

If you'd rather run Postgres another way (Docker, Homebrew, Neon, a Railway dev
instance), set DATABASE_URL and nothing in this file is used.
"""

import pathlib
import sys

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / ".pgdata"
DB_NAME = "swolemates"


def _server(*, keep_running: bool):
    import pgserver

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # cleanup_mode=None leaves the postmaster up after this process exits, which is the
    # whole point — `make db` should outlive the command that started it.
    return pgserver.get_server(DATA_DIR, cleanup_mode=None if keep_running else "stop")


def _url(srv) -> str:
    # pgserver hands back a unix-socket URI for the default `postgres` database.
    # Point it at our own database and the psycopg 3 driver.
    uri = srv.get_uri(database=DB_NAME)
    return uri.replace("postgresql://", "postgresql+psycopg://", 1)


def start() -> str:
    srv = _server(keep_running=True)
    existing = srv.psql(f"SELECT 1 FROM pg_database WHERE datname = '{DB_NAME}'")
    if "(0 rows)" in existing:
        srv.psql(f'CREATE DATABASE "{DB_NAME}"')
    return _url(srv)


def stop() -> None:
    _server(keep_running=False).cleanup()


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd in ("start", "url"):
        url = start()
        print(url)
    elif cmd == "stop":
        stop()
        print("stopped", file=sys.stderr)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
