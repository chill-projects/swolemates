---
name: swolemates
description: Proven workflows for developing Swolemates - operating Railway/WorkOS via connectors, and debugging sign-in, 401, token, or claude.ai connector failures. Use for any Swolemates ops or auth debugging.
---

# Swolemates workflows

Architecture and rules: `AGENTS.md`. Auth model + symptom→cause table: `docs/auth.md`.

## Operating rules (each one earned)

- Railway and WorkOS: desktop connectors only. CLIs were removed; don't reinstall.
  Missing tools → ask for the connector, don't work around.
- After any WorkOS mutation, re-verify with the matching query — mutations can "fail"
  by returning a typename (wrong target: application vs environment), not an error.
- `/oauth2/*` accepts Connect-application client IDs only; the environment client ID
  silently doesn't work there.
- Config changes (Railway variables) restart without a rebuild — prefer them over
  deploys for diagnostics. `LOG_LEVEL=DEBUG` enables auth forensics; set back to INFO.
- Never log tokens or full claims (they carry email/name). Never type credentials,
  even in the browser pane.

## Debugging auth

Failures mask forward — check in this order, one deliberate sign-in per experiment:

1. **Backend**: Railway connector `get-logs`, `types: ["deploy"]`, `filter: "rejected"`.
   With `LOG_LEVEL=DEBUG` the log names the token's actual aud/iss vs expected.
   In `["http"]` logs: a 401 in ~30ms = token present but rejected; ~3ms = no token sent.
2. **WorkOS**: connector `query environmentEvents` — did login itself succeed?
   Config truth: `authkitSettings`, `authkitOauthResources`, `redirectUris`, `corsConfig`.
3. **Browser console**: the SPA logs each exchange failure with the response body.
   CORS blocks are visible only here; the server never sees them.
4. **The token**: decode with `jwt.decode(t, options={"verify_signature": False})` and
   read aud/iss/exp yourself.

Silent failure = browser-side. Loud failure = server-side. Both silent = the request
never happened (check discovery/redirects).
