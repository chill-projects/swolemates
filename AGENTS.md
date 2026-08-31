# Swolemates

One backend container, two front doors: a web SPA and a Claude connector (remote MCP),
sharing one database and one service layer. See `docs/design.md` for the full design and
`PRD.md` for the product requirements.

## Your training data is out of date here

Three things in this stack changed after your training cutoff. Read the docs before
writing code against them — do not work from memory:

- **FastMCP 3.x** (`https://gofastmcp.com`) — the server API, `http_app()` mounting, and
  the AuthKit provider.
- **MCP spec 2026-07-28** — stateless Streamable HTTP; sessions were dropped.
- **MCP Apps / ext-apps** (`ui://` resources, `_meta.ui.*`) — the interactive component
  format for both Claude and the SPA.

`uv` and Alembic behave as you'd expect. FastAPI and SQLAlchemy 2.x do too.

## Layout

```
backend/app/
  main.py      # mounts /api, /mcp, SPA static; /health
  api/         # REST routers — thin, no business logic
  mcp/         # FastMCP tools + ui:// resources — thin, no business logic
  services/    # shared logic + authz. The only place permissions live.
  models/      # SQLAlchemy — the schema source of truth
  alembic/     # migrations, run once via Railway pre-deploy
frontend/src/
  api/         # generated client (do not hand-edit) + TanStack Query hooks
  mcp-apps/    # component bundles that render in Claude AND the SPA
```

The pre-rewrite Next.js app used to sit in `docs/legacy/` as porting reference. Porting
is done, so it's gone — a "ported from `docs/legacy/...`" comment is a pointer into git
history now, not a path on disk.

## Rules

- **Routers and tools contain no logic.** Both transports call the same service function.
  A permission check that lives in a router is a bug — it won't apply to the MCP path.
- **Every query filters by `user_id`** (the WorkOS `sub`) inside the service layer. No
  ad-hoc queries in routers or tools. This keeps a later move to DB-enforced isolation
  cheap; see the deferred decision in `docs/design.md` §4.
- **Tools are task-shaped, not a REST mirror.** `log_workout`, not `create_workout_row`.
  Every tool that returns UI also returns plain text for non-UI hosts.
- **Migrations must be backward-compatible.** Blue-green means old and new code run
  against the same schema for a few seconds. Never drop or rename in the same deploy
  that stops using a column.
- **Don't hand-edit `frontend/src/api/generated.ts`.** Run `make types`. CI fails if it
  drifts from the OpenAPI schema.

## Dev loop

`make dev` runs Postgres + `uvicorn --reload` + `vite dev` together. `make test` is what
CI runs. See `README.md` for the full list and `SETUP.md` for one-time account setup.

## Operating notes for agents

Will's standing preference: **act on his behalf whenever possible** rather than handing
back instructions.

**Railway and WorkOS are managed through their desktop Connectors — only.** Enable the
Railway and WorkOS connectors for your chat (Claude desktop → connectors); their tools
cover deployments, logs, variables, redeploys (Railway) and the full dashboard API
(WorkOS `query`/`mutate`/`list_operations`). The Railway CLI and ad-hoc WorkOS MCP
configs were deliberately uninstalled — don't reinstall them; if a connector tool is
missing from the session, ask to have the connector enabled rather than reaching for a
CLI. This keeps every collaborator on the identical loop.

Other tooling on this machine:

- `gh` — authenticated. Push, open PRs, watch CI (`gh run list/view`), read job logs.
  The repo is `chill-projects/swolemates` (shared, public).
- `docker` via OrbStack — run `open -a OrbStack` first; the CLI is only on PATH while
  it's running.

Still ask first for: creating billable resources (new Railway services/databases),
anything interactive-auth (connector enablement, OAuth consents), and account signup —
those are the humans'. Committing and pushing follow the normal rules (ask unless told).

Live deploy: https://swolemates-production.up.railway.app · Railway "production"
environment, wired to WorkOS AuthKit (`friendly-canyon-24.authkit.app`, environment
"Production" in the Swolemates WorkOS project).
