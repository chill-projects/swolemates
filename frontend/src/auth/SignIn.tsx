import { useState } from "react";

import { type AuthConfig, login } from "./authkit";

/**
 * Shown whenever the API says we're not authenticated.
 *
 * When AuthKit isn't wired up yet this explains exactly what's missing instead of
 * offering a button that can't work — the deployment is reachable long before WorkOS
 * exists, and a dead "Sign in" button is worse than an honest explanation.
 */
export function SignIn({ config }: { config: AuthConfig }) {
  const [error, setError] = useState<string | null>(null);

  if (!config.configured) {
    return (
      <section>
        <h2>Sign-in isn’t set up yet</h2>
        <p className="muted">
          This deployment is running with <code>ENVIRONMENT={config.environment}</code> and
          no WorkOS AuthKit credentials, so there’s no way to sign in and the API rejects
          every request.
        </p>
        <p className="muted">
          Set <code>AUTHKIT_DOMAIN</code> and <code>WORKOS_CLIENT_ID</code> on the service,
          then switch <code>ENVIRONMENT</code> to <code>production</code>. See{" "}
          <code>SETUP.md</code> §2.
        </p>
      </section>
    );
  }

  return (
    <section>
      <h2>Sign in</h2>
      <p className="muted">You’ll be sent to WorkOS and returned here.</p>
      {error && <p className="error">{error}</p>}
      <button
        type="button"
        onClick={() => {
          login(config).catch(() => setError("Couldn’t start the login flow."));
        }}
      >
        Sign in
      </button>
    </section>
  );
}
