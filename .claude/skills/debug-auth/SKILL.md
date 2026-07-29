---
name: debug-auth
description: Debug sign-in, token, or connector failures by correlating all four log sources — Railway backend logs, WorkOS auth events, the browser console/network tab, and the JWT itself. Use whenever auth "doesn't work", a 401 is unexplained, the SPA bounces to sign-in, or the claude.ai connector fails setup.
---

# Debugging auth across the stack

Auth failures span four systems, and each one only sees its own slice. Never debug from
a single log source — correlate. `docs/auth.md` has the architecture and the full
symptom→cause table; this skill is the *how to look*.

## The four log sources and how to read each

**1. Backend (Railway connector — required, do not ask the user to read the dashboard):**

- `get-logs` with `types: ["deploy"]`, `filter: "rejected"` — our auth code logs every
  rejected bearer token as `rejected bearer token: <reason> (token aud=… iss=…,
  expected aud=…)`. This line names both sides of any mismatch.
- `types: ["http"]` shows request timing/status: a `/api/whoami` 401 in ~30ms did real
  JWT verification (token present, rejected); ~3ms means no token was attached at all.
- IDs: project `72140275-2407-479d-8020-d5c11bc9bdd7`, service
  `9d7a5b85-3893-49fd-a927-864d9f13ae34`, environment
  `6595364b-4980-4f60-99ca-a415ae5daeb3`.

**2. WorkOS (WorkOS connector — `query`/`mutate`/`list_operations`):**

- `environmentEvents` — did the login itself succeed? Shows
  `authentication.password_succeeded`, `user.created`, email verification, with client
  id and user agent. If these are absent, the user never got past the login page.
- `authkitSettings`, `authkitOauthResources`, `redirectUris`, `corsConfig` — the
  configuration that must agree with our env vars. Verify, don't assume.
- Environment: WorkOS project "Swolemates", Production env
  `environment_01KYQSBZDC5NQ1AT8NPGVPRAA0`.

**3. Browser (Claude's browser pane, or ask the user for console/network output):**

- The SPA logs every token-exchange failure with status + response body
  (`Token exchange failed: …`). CORS blocks are visible ONLY here — the server never
  sees them. A red `token` request with no readable response = missing CORS origin.
- The pane can drive a real sign-in for E2E verification when an AuthKit session
  already exists — but never type credentials.

**4. The token itself (decode, don't guess):**

```bash
python3 -c "import jwt,sys; print(jwt.decode(sys.argv[1], options={'verify_signature': False}))" '<token>'
```

Read `aud`, `iss`, `exp` and compare against `PUBLIC_URL` and `AUTHKIT_DOMAIN`.

## Rules of thumb

- Failures mask forward: validate in order (config → redirect → exchange → backend
  verification). A broken early link makes every later link look broken.
- Silent failure = browser-side (CORS, thrown fetch). Loud failure = server-side (our
  logs name the check). Both silent = the request never happened; look at discovery.
- One deliberate sign-in per experiment; don't burn authorization codes on brute-force
  probing.
- After any WorkOS config mutation, re-verify with the corresponding query — some
  mutations target applications vs environments and fail with a typename, not an error.
