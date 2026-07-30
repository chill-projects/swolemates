# Swolemates

Calorie/macro tracking and workout logging for two people, reachable two ways: a web app
and a Claude connector, sharing one database and one service layer.

- **What it does** → [PRD.md](PRD.md)
- **How the platform is put together** → [docs/design.md](docs/design.md)
- **Accounts and services to set up** → [SETUP.md](SETUP.md)
- **Conventions for working in here** → [AGENTS.md](AGENTS.md)

## Getting started

No accounts needed. `make db` runs a real PostgreSQL locally — no Docker, no install.

```bash
make setup && make db && make seed && make dev
```

Then open http://localhost:5173.

## The dev loop

```bash
make dev            # backend (:8000) + Vite (:5173) + component-bundle watch; all reload on save
make test           # everything CI runs: ruff, pytest, tsc, vitest
make types          # regenerate the typed API client after changing a route
make migrate m="…"  # autogenerate a migration after changing a model
make apps           # one-shot build of the ui:// component bundles
make apps-dev       # preview components in FastMCP's dev UI (:8080) without the full app
make seed-reset     # wipe and re-seed local sample data
make db-reset       # throw the local database away and rebuild it from migrations
make inspector      # MCP Inspector, pointed at http://localhost:8000/mcp
make               # list every target
```

Locally you are `DEV_USER_SUB` (`dev_user_00000000`) on both front doors — no OAuth round
trip per request. That bypass is inert anywhere except `ENVIRONMENT=local`, and there's a
test asserting it.

### Adding a feature

The whole point of the layout is that a feature is one vertical slice. `tmpx` is a
complete, working copy of that slice — start by copying it:

| Step | File |
|---|---|
| 1. Table | `backend/app/models/tmpx.py` → then `make migrate m="…"` |
| 2. Logic + authz | `backend/app/services/tmpx.py` |
| 3. REST | `backend/app/api/tmpx.py` → then `make types` |
| 4. MCP tools | `backend/app/mcp/tmpx_tools.py` |
| 5. SPA | `frontend/src/api/tmpx.ts`, `frontend/src/pages/TmpxPage.tsx` |
| 6. Tests | `backend/tests/test_tmpx.py` |

Steps 3 and 4 are both thin wrappers over step 2. If you find yourself writing a
permission check in a router or a tool, it belongs in the service instead — otherwise it
only applies to one of the two front doors.

Delete `tmpx` once the first real feature lands.

## Deploying

`git push` → GitHub Actions → Railway builds the image, runs `alembic upgrade head` as a
pre-deploy step, waits for `/health`, then swaps traffic over. No deploy YAML.

Pull requests get their own public HTTPS URL, which is how you test a change as a real
claude.ai connector before merging.
