# Setup — who does what

The division of labor for getting services stood up, written so **Claude does most of
it**. Claude has authenticated CLIs for GitHub (`gh`) and Railway (`railway`) on this
machine and acts on your behalf with them by default — see the operating notes in
[AGENTS.md](AGENTS.md). Your part is the things Claude can't or won't do: creating
accounts, clicking OAuth consent screens, and payments.

**Nothing here is needed to run the app locally** — `make setup && make db && make dev`
works with no accounts at all.

---

## Current state (2026-07-29)

| Piece | State |
|---|---|
| Live deploy | ✅ https://swolemates-production.up.railway.app — `/health` and `/health/ready` green |
| Railway project | ✅ `swolemates` (app service + Postgres), CLI linked, `railway.json` respected |
| Pre-deploy migrations | ✅ verified — `alembic upgrade head` ran in-container on deploy |
| GitHub | ✅ `chill-projects/swolemates` (public), CI green on `main` (4 jobs incl. docker/amd64) |
| Container image | ✅ builds + runs on arm64 (local) and amd64 (CI), non-root, ~190 MB |
| Auth | ⬜ **the current blocker** — `ENVIRONMENT=test` disables the dev bypass, so the live SPA gets 401s and shows "Couldn't load items." WorkOS doesn't exist yet. |
| SPA login flow | 🔶 written (`frontend/src/auth/`), not yet deployed or tested against a real AuthKit tenant |

---

## What Claude does (given one sentence of instruction)

Already proven in this repo — ask and it happens:

- **Railway:** read build/deploy logs, set service variables, trigger redeploys, check
  deployment status, wire `DATABASE_URL=${{Postgres.DATABASE_URL}}` references. Adding
  billable services (databases, replicas) it will propose first, since that's your money.
- **GitHub:** push, open PRs, watch CI runs, read job logs, set up branch protection.
- **Docker:** build and smoke-test images against OrbStack (`open -a OrbStack` first).
- **Code:** everything in `make test`, migrations, the typed-client regen (`make types`).

After you finish the WorkOS section below, Claude also: sets the Railway variables,
flips `ENVIRONMENT` to `production`, redeploys, and verifies the token path end to end.

## What only you can do

1. **Create accounts** (Claude doesn't create accounts or accept ToS): WorkOS is the only
   one left.
2. **Interactive CLI auth**, if it ever needs re-doing: `railway login`, `railway link`,
   `gh auth login`.
3. **Click through OAuth consents** — the claude.ai connector login in phase 3.
4. **Approve spend**: new Railway services, plan changes.

---

## 1. Railway — ✅ done

Project `swolemates`, app service + Postgres, domain generated, variables set
(`DATABASE_URL` by reference, `PUBLIC_URL`, `ENVIRONMENT=test` until WorkOS exists).

Still worth doing in the dashboard when convenient (Claude can't reach these switches —
no CLI/API equivalent):

- **Wait for CI: ON** (app service → Settings) — blocks deploys on red GitHub checks.
- **Serverless/sleeping: OFF** — cold starts break Claude tool calls. Off is the default;
  just don't turn it on.
- **PR environments: ON** (project → Settings → Environments) — every PR gets a public
  HTTPS URL, which is how connectors get tested against real claude.ai before merge.

> `PUBLIC_URL` is the OAuth token audience. The app now refuses to boot in production if
> it's missing or localhost — if a deploy dies at startup with a config error, that's the
> guard doing its job, not a bug.

## 2. WorkOS AuthKit — ⬜ your move (~15 min of dashboard clicks)

Free to 1M MAU. This is the phase 3 blocker; everything else waits on it.

1. Sign up at [workos.com](https://workos.com), create an organization.
2. **AuthKit → enable.** Note the domain: `https://<something>.authkit.app`.
3. **Authentication → enable Email + Password** (Google sign-in optional, free).
4. **Redirects** — add all three:
   - `http://localhost:5173/callback`
   - `https://swolemates-production.up.railway.app/callback`
   - the PR-environment pattern once you know it (or add per-PR later)
5. **Applications → Dynamic Client Registration: enable.** Claude registers as an OAuth
   client via DCR; clients must use `token_endpoint_auth_method: "none"`.
6. Copy the **Client ID**.

Then hand Claude the AuthKit domain + client ID and say "wire up WorkOS". Claude sets
the Railway variables, flips `ENVIRONMENT=production`, redeploys, and verifies.

**Phase 3 gate (you, ~2 min):** add
`https://swolemates-production.up.railway.app/mcp` to claude.ai as a custom connector,
complete the login, call `whoami`. Your WorkOS `sub` back = the riskiest part of the
whole design is done.

## 3. GitHub — ✅ done, one option open

CI runs on every push; no secrets needed (CI brings its own Postgres). If you want
`main` protected now that the project is shared, say "set up branch protection" —
requiring the four checks before merge is one `gh api` call.

## 4. Food-estimation API key — phase 6, not yet

Photo food logging needs a vision model key: `ANTHROPIC_API_KEY`
([console.anthropic.com](https://console.anthropic.com), matches the PRD) or
`GEMINI_API_KEY` ([aistudio.google.com](https://aistudio.google.com), matches what the
legacy code in `docs/legacy/logic/food-estimate.route.ts` actually did). Pennies at
two-user volume. Create whichever when phase 6 starts; Claude wires it.

---

## Local tooling — ✅ all present

| Tool | Notes |
|---|---|
| `uv` 0.6.6 | Python deps + toolchain |
| `node` 24 / npm 10.9 | frontend build |
| Postgres | none needed — `make db` runs a real Postgres 16 via `pgserver` |
| OrbStack 2.2.1 | `docker` is only on PATH while OrbStack runs: `open -a OrbStack` |
| `gh` | authenticated as `wfstevens` |
| `railway` 5.30.1 | logged in, linked to the `swolemates` project |

Fresh-machine bootstrap: `brew install uv node gh railway && brew install --cask orbstack`,
then `gh auth login`, `railway login`, `railway link`. Optional system Postgres instead of
`make db`: `brew install postgresql@17`, `createdb swolemates`, point `DATABASE_URL` at it
in `backend/.env`.

---

## Environment variables

| Variable | Local | Railway | Who sets it |
|---|---|---|---|
| `ENVIRONMENT` | `local` (via `make db`) | `test` now → `production` after WorkOS | Claude |
| `DATABASE_URL` | written by `make db` | `${{Postgres.DATABASE_URL}}` reference | Claude |
| `PUBLIC_URL` | `http://localhost:8000` | the Railway domain | Claude |
| `AUTHKIT_DOMAIN` | blank | after §2 | Claude, from your dashboard values |
| `WORKOS_CLIENT_ID` | blank | after §2 | Claude, from your dashboard values |
| `DEV_USER_SUB` | `dev_user_00000000` | — (inert outside local) | default |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | phase 6 | phase 6 | Claude, from your key |

Production refuses to boot without the AuthKit pair and a non-localhost `PUBLIC_URL` —
a misconfigured deploy fails its healthcheck instead of serving an open MCP endpoint.

---

## Tooling gaps noticed while setting this up

- **`railway setup agent`** installs Railway's official agent skills + MCP server
  (deploy/logs/status/docs tools). Not yet run — it edits local editor/MCP config, so
  run it yourself or ask Claude to (it may hit a permission prompt). Until then the
  plain CLI covers everything we've needed.
- **No Railway connector exists in the MCP registry** — the CLI (or the official MCP
  server above) is the way in.
- Operating preferences for agents working in this repo live in **AGENTS.md**, including
  the standing "act on Will's behalf with the linked CLIs" note.
