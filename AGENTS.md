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
docs/legacy/   # the deleted Next.js app, kept as porting reference. Never compiled.
```

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
- **`docs/legacy/` is reference material**, not live code. Port files out of it; don't
  import from it.

## Dev loop

`make dev` runs Postgres + `uvicorn --reload` + `vite dev` together. `make test` is what
CI runs. See `README.md` for the full list and `SETUP.md` for one-time account setup.

## Operating notes for agents

Will's standing preference: **act on his behalf whenever possible** rather than handing
back instructions. This machine has authenticated CLIs — use them directly:

- `gh` — logged in as `wfstevens`. Push, open PRs, watch CI (`gh run list/view`), read
  job logs. The repo is `chill-projects/swolemates` (shared, public).
- `railway` — logged in and linked to the `swolemates` project. Pull build/deploy logs
  (`railway logs -b|-d <deployment-id>`), list deployments, set variables
  (`railway variables --set`), redeploy (`railway deployment redeploy -y --from-source`).
  Debug deploys yourself from logs; don't ask Will to read the dashboard.
- `docker` via OrbStack — run `open -a OrbStack` first; the CLI is only on PATH while
  it's running.

Still ask first for: creating billable resources (new Railway services/databases),
anything interactive-auth (`railway login/link`, OAuth consents), and account signup —
those are Will's. Committing and pushing follow the normal rules (ask unless told).

Live deploy: https://swolemates-production.up.railway.app · Railway "production"
environment. `ENVIRONMENT=test` there until WorkOS AuthKit is wired (see `SETUP.md` §2).
