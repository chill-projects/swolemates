# Setup — who does what

The division of labor for getting services stood up, written so **Claude does most of
it**. Your part is the things Claude can't or won't do: creating accounts, clicking
OAuth consent screens, and payments.

**Railway and WorkOS are driven through their desktop Connectors — the only supported
path.** In the Claude desktop app, enable the **Railway** and **WorkOS** connectors for
your chat and sign in once through each one's OAuth screen. That's the entire per-person
setup; afterwards Claude reads logs, sets variables, redeploys, and edits WorkOS config
directly. (The Railway CLI and hand-rolled MCP configs were removed on purpose — one
tool, same loop for every collaborator.) GitHub still goes through the `gh` CLI:
`brew install gh && gh auth login`.

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
| Auth | ✅ wired — WorkOS "Swolemates" project, Production env `friendly-canyon-24.authkit.app`, password auth + CIMD + DCR on, redirects + resource indicators set, Railway running `ENVIRONMENT=production` |
| SPA login flow | 🔶 deployed, **untested against the real tenant** — the phase 3 gate below |

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
- **PR environments: ON** (project → Settings → General → "PR environments", may be
  labeled "Bot PR environments") — every PR gets a public HTTPS URL, which is how
  connectors get tested against real claude.ai before merge. Dashboard-only; the CLI
  and public API can't flip it.

> **Serverless stays OFF** (`sleepApplication: false`, pinned by `railway.json` — the
> dashboard toggle is locked by the file, so change it there if ever needed). Cold
> starts break claude.ai connector tool calls; the couple of dollars a month it would
> save isn't worth debugging OAuth against a sleeping server.

> `PUBLIC_URL` is the OAuth token audience. The app now refuses to boot in production if
> it's missing or localhost — if a deploy dies at startup with a config error, that's the
> guard doing its job, not a bug.

## 2. WorkOS AuthKit — ✅ done (via the WorkOS connector, 2026-07-29)

Configured entirely through the connector, no dashboard clicks: password auth on,
CIMD + DCR on, both redirect URIs set, resource indicators set (bare origin, trailing
slash, and `/mcp` variants — tokens carry `aud` matching `PUBLIC_URL`), everything
renamed to "Swolemates". Values live in Railway as `AUTHKIT_DOMAIN` and
`WORKOS_CLIENT_ID`.

**Phase 3 gate — the one remaining human step (~2 min each):**

1. **Browser:** open https://swolemates-production.up.railway.app, sign up, add an item.
2. **Connector:** add `https://swolemates-production.up.railway.app/mcp` to claude.ai as
   a custom connector, complete its login, ask Claude to call `whoami`.

Your WorkOS `sub` back from both = the riskiest part of the whole design is done. When
PR environments are used later, add each preview URL to Redirects (via the connector).

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
| `gh` | authenticated |
| Railway + WorkOS | **desktop Connectors, not CLIs** — enable both for your chat and sign in once each |

Fresh-machine bootstrap (i.e. Michelle's setup): `brew install uv node gh &&
brew install --cask orbstack`, then `gh auth login`, then enable the Railway and WorkOS
connectors in the Claude desktop app. Optional system Postgres instead of `make db`:
`brew install postgresql@17`, `createdb swolemates`, point `DATABASE_URL` at it in
`backend/.env`.

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

## Tooling decisions

- **Connectors only for Railway and WorkOS.** Both desktop connectors are enabled and
  proven (the entire WorkOS §2 configuration above was done through one). The Railway
  CLI was uninstalled and the hand-added WorkOS MCP entry removed — one supported path,
  so every collaborator's loop is identical.
- Operating preferences for agents working in this repo live in **AGENTS.md**, including
  the standing "act on Will's behalf" note and the connectors-only rule.
