# Setup — accounts and services

Work through these at your leisure. **Nothing here is needed to run the app locally** —
`make setup && make db && make dev` works today with no accounts at all.

Each item says what it unblocks and which environment variables it produces. Items are
ordered by when you'll actually need them.

---

## 0. Local tooling — mostly done

| Tool | Status | Notes |
|---|---|---|
| `uv` | ✅ installed (0.6.6) | Python deps + the Python toolchain |
| `node` / `npm` | ✅ installed (24 / 10.9) | Frontend build |
| PostgreSQL | ✅ no install needed | `make db` runs a real Postgres 16 via `pgserver`, no Docker |
| Docker | ❌ not installed | **Optional.** Only needed for `make build`. CI builds the image on every push either way — see the follow-up at the bottom of this file. |

### Homebrew

Everything below is optional on this machine — `uv` and `node` are already installed and
the dev database needs nothing. This is here for a fresh machine, or when you want the
local Docker check.

```bash
# Container runtime — pick one. OrbStack is much lighter on macOS.
brew install --cask orbstack
brew install --cask docker          # Docker Desktop, if you'd rather

# Only needed on a fresh machine
brew install uv node
```

After installing OrbStack, launch it once so it can set up the Docker socket, then:

```bash
make build
```

**Alternative Postgres.** `make db` needs nothing installed, but if you'd rather run a
system Postgres — say you want `psql` on your PATH, or a database that survives a repo
wipe:

```bash
brew install postgresql@17
brew services start postgresql@17
createdb swolemates
```

Then put the URL in `backend/.env` and `make db` is bypassed entirely:

```
DATABASE_URL=postgresql+psycopg://$(whoami)@localhost:5432/swolemates
```

Nothing in the app cares which of the two you use.

---

## 1. Railway — hosting + production Postgres

**Unblocks:** phase 2. Deploying at all.
**Cost:** ~$5–10/mo (Hobby plan, $5 credit included).

1. Sign up at [railway.com](https://railway.com) with your GitHub account.
2. **New Project → Deploy from GitHub repo →** `michelle-zhuang1/swolemates`.
   Railway reads `railway.json`, so the Dockerfile, pre-deploy migration, and healthcheck
   are already configured — don't re-enter them in the UI.
3. In the project, **New → Database → Add PostgreSQL**. Railway injects `DATABASE_URL`
   into the app service automatically. Don't set it by hand.
4. On the app service, **Settings** and confirm:
   - **Serverless / sleeping: OFF.** Cold starts break Claude tool calls — the connector
     times out before the container wakes.
   - **Wait for CI: ON.** Deploys only after GitHub Actions is green.
   - **Pre-deploy command:** should already read `alembic upgrade head` from
     `railway.json`. It must use the **unpooled** database URL so migrations aren't run
     through PgBouncer.
   - **Healthcheck path:** `/health`.
5. **Settings → Networking → Generate Domain.** Copy the resulting HTTPS URL.
6. **Variables** on the app service, add:
   ```
   ENVIRONMENT=production
   PUBLIC_URL=https://<the domain from step 5>
   ```
7. **Settings → Environments → enable PR environments.** Each pull request gets its own
   public HTTPS URL, which is how you test a connector against real claude.ai without
   touching production.

> `PUBLIC_URL` is the OAuth token audience. If it doesn't exactly match the URL Claude
> connects to, every token is rejected and the failure looks like a login loop. Set it
> once, correctly, and don't change it casually.

---

## 2. WorkOS AuthKit — login for both front doors

**Unblocks:** phase 3, the auth spike. This is the riskiest part of the whole plan, which
is why it comes before any real features.
**Cost:** free up to 1M monthly active users.

1. Sign up at [workos.com](https://workos.com) and create an organization.
2. **AuthKit → enable it.** Note the AuthKit domain — it looks like
   `https://your-project-12345.authkit.app`.
3. **Authentication → enable Email + Password** (matches the PRD). Add Google sign-in too
   if you want it; it costs nothing and skips password reset support entirely.
4. **AuthKit → Redirects.** Add:
   - `http://localhost:5173/callback` — local SPA
   - `https://<your Railway domain>/callback` — production SPA
5. **Applications → Dynamic Client Registration: enable.** Claude registers itself as an
   OAuth client this way; without DCR the connector cannot complete setup.
   Registered clients need `token_endpoint_auth_method: "none"` — Claude is a public
   client and has no secret to present.
6. Copy the **Client ID** from the dashboard.
7. Add to Railway variables:
   ```
   AUTHKIT_DOMAIN=https://your-project-12345.authkit.app
   WORKOS_CLIENT_ID=client_01ABC...
   ```
8. For local testing against real WorkOS, put the same two values in `backend/.env` and
   change `ENVIRONMENT=local` to `ENVIRONMENT=test` — that turns off the `DEV_USER_SUB`
   bypass so you're exercising the real token path.

**Gate for phase 3:** open a PR, get its Railway preview URL, add
`https://<preview>/mcp` to claude.ai as a custom connector, complete the login, and call
`whoami`. If it returns your WorkOS `sub`, the risky part is done.

---

## 3. GitHub — CI

**Unblocks:** the CI gate on deploys. Mostly automatic.

1. Actions are enabled by default; `.github/workflows/ci.yml` runs on the first push.
2. Optional but recommended — **Settings → Branches → add a rule for `main`:** require
   the `backend`, `frontend`, and `generated-client` checks to pass before merge.
3. No secrets are needed. CI runs its own throwaway Postgres and never touches WorkOS or
   Railway.

---

## 4. Food-estimation API key — phase 6 only

**Unblocks:** the photo-based food logging port. Not needed before then.

The deleted Next app used Google Gemini (`@google/genai`) even though the PRD specifies
Claude. Pick one when you get there:

- **Anthropic** — [console.anthropic.com](https://console.anthropic.com) → API key →
  `ANTHROPIC_API_KEY`. Matches PRD §4. Vision + structured JSON in one request.
- **Google** — [aistudio.google.com](https://aistudio.google.com) → API key →
  `GEMINI_API_KEY`. Matches what the code actually did, so the prompt and schema in
  `docs/legacy/logic/food-estimate.route.ts` port across unchanged.

Either way it's pennies a month at two-user volume.

---

## Environment variables, all together

| Variable | Local | Railway | Source |
|---|---|---|---|
| `ENVIRONMENT` | `local` (auto) | `production` | you |
| `DATABASE_URL` | written by `make db` | injected | Railway Postgres |
| `PUBLIC_URL` | `http://localhost:8000` | your Railway domain | you |
| `AUTHKIT_DOMAIN` | blank | required | WorkOS |
| `WORKOS_CLIENT_ID` | blank | required | WorkOS |
| `DEV_USER_SUB` | `dev_user_00000000` | — | ignored outside local |
| `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | phase 6 | phase 6 | you |

The app refuses to start with `ENVIRONMENT=production` unless `AUTHKIT_DOMAIN`,
`WORKOS_CLIENT_ID` and `PUBLIC_URL` are all set, so a misconfigured deploy fails the
healthcheck instead of silently serving an unauthenticated MCP endpoint.

---

## Follow-ups

### Verify the container image actually builds

**Status:** unverified. Docker isn't installed on this machine, so `Dockerfile` has never
been built anywhere.

It's a two-stage build (Node builds the SPA → copied into a Python image) and the parts
most likely to be wrong are the `npm run build -- --outDir dist` override, the
`uv sync --locked` layer, and the non-root `USER app` switch. None of that is exercised
by `make test`.

Three ways to close it, cheapest first:

1. **Push the branch.** `.github/workflows/ci.yml` has a `docker` job that builds the
   image on every push. Costs nothing and needs no local install — this alone answers
   the question.
2. **Let Railway build it.** Railway builds from the Dockerfile on first deploy, so a
   broken image shows up there. Slower feedback than CI, and a failure is entangled with
   whatever else is new on a first deploy.
3. **Build locally.** Install OrbStack (see §0) and run `make build`. Worth doing only if
   you end up iterating on the Dockerfile often enough that CI round-trips get annoying.

Option 1 happens automatically the moment the branch is pushed, so this may well resolve
itself before anyone acts on it.
