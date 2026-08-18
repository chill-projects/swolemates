import { useState } from "react";

import { useInvitePreview, useRedeemInvite } from "../api/partner";
import { type AuthConfig, login, useWhoami } from "../auth/authkit";

const PENDING_INVITE_KEY = "swolemates.pending_invite_code";
const REDEEM_ERROR_KEY = "swolemates.invite_redeem_error";

export function readPendingInviteCode(): string | null {
  return sessionStorage.getItem(PENDING_INVITE_KEY);
}

export function clearPendingInviteCode(): void {
  sessionStorage.removeItem(PENDING_INVITE_KEY);
}

export function setInviteRedeemError(message: string): void {
  sessionStorage.setItem(REDEEM_ERROR_KEY, message);
}

/** Read once and clear — a one-time banner for the /partner page after a post-login
 * auto-redeem attempt fails (already linked, invite expired mid-flight, etc). The
 * redirect there is a full page load, so this is the only way to carry the message. */
export function takeInviteRedeemError(): string | null {
  const message = sessionStorage.getItem(REDEEM_ERROR_KEY);
  if (message) sessionStorage.removeItem(REDEEM_ERROR_KEY);
  return message;
}

/**
 * Unauthenticated by design (#5, resolved) — reachable with no session at all, so an
 * invitee can see who invited them before signing up. Not authenticated: stashes the
 * code in sessionStorage (App.tsx's login effect has no way to carry an arbitrary
 * payload through the OAuth round-trip otherwise) and starts the normal login flow.
 * Already authenticated (someone opens the link in a second tab, or a returning
 * user): redeems directly instead.
 */
export function InvitePreviewPage({ code, config }: { code: string; config: AuthConfig | null }) {
  const preview = useInvitePreview(code);
  const whoami = useWhoami();
  const redeem = useRedeemInvite();
  const [loginError, setLoginError] = useState<string | null>(null);

  if (preview.isPending || whoami.isPending) return <p className="muted">Loading invite…</p>;

  if (preview.isError || !preview.data?.valid) {
    return (
      <section>
        <h2>This invite isn’t valid</h2>
        <p className="muted">It may have expired or already been used.</p>
      </section>
    );
  }

  const name = preview.data.inviter_display_name ?? "Someone";

  return (
    <section>
      <h2>{name} invited you to Swolemates</h2>
      <p className="muted">Accept to link up as accountability partners.</p>
      {loginError && <p className="error">{loginError}</p>}
      {redeem.isError && <p className="error">{redeem.error.message}</p>}
      {whoami.data ? (
        <button
          type="button"
          disabled={redeem.isPending}
          onClick={() => {
            redeem.mutate(code, { onSuccess: () => window.location.assign("/partner") });
          }}
        >
          {redeem.isPending ? "Linking…" : "Accept invite"}
        </button>
      ) : (
        <button
          type="button"
          disabled={!config?.configured}
          onClick={() => {
            if (!config) return;
            sessionStorage.setItem(PENDING_INVITE_KEY, code);
            login(config).catch(() => setLoginError("Couldn’t start the login flow."));
          }}
        >
          Sign in to accept
        </button>
      )}
    </section>
  );
}
