import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useProfile } from "./api/profile";
import { useWhoami } from "./api/tmpx";
import { SignIn } from "./auth/SignIn";
import { completeLogin, fetchAuthConfig, login } from "./auth/authkit";
import { ProfileForm } from "./pages/ProfileForm";
import { TmpxPage } from "./pages/TmpxPage";

/**
 * Phase 6 replaces this with a real router and the ported screens. For now it gates the
 * template slice behind auth, which is the thing the platform work has to prove.
 */
export function App() {
  const [returningFromLogin, setReturningFromLogin] = useState(
    () => window.location.pathname === "/callback",
  );
  const [loginError, setLoginError] = useState<string | null>(null);
  // The callback exchange must run exactly once — effect re-runs (query state changes
  // re-render constantly) and a spent OAuth code would make retries fail anyway.
  const exchangeStarted = useRef(false);

  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["authConfig"], queryFn: fetchAuthConfig, retry: false });
  const whoami = useWhoami();

  useEffect(() => {
    if (!returningFromLogin || !config.data || exchangeStarted.current) return;
    exchangeStarted.current = true;
    const authConfig = config.data;

    completeLogin(authConfig).then((result) => {
      if (result === "restart") {
        // Verifier was minted in another tab (email-verification flow). AuthKit already
        // has a session, so restarting completes without re-prompting for credentials.
        login(authConfig).catch(() => {
          setLoginError("Couldn’t restart the login flow.");
          setReturningFromLogin(false);
        });
        return;
      }
      if (result === "failed") {
        setLoginError("Sign-in didn’t complete. Details are in the browser console.");
      }
      setReturningFromLogin(false);
      queryClient.invalidateQueries({ queryKey: ["whoami"] });
    }).catch((err: unknown) => {
      // A thrown exchange (network/CORS failure) previously left the app stuck on
      // "Signing in…" forever — the promise rejected and nothing reset the state.
      console.error("Login completion threw:", err);
      setLoginError("Sign-in didn’t complete. Details are in the browser console.");
      setReturningFromLogin(false);
    });
  }, [returningFromLogin, config.data, queryClient]);

  const busy = config.isPending || whoami.isPending || returningFromLogin;

  return (
    <main>
      <header>
        <h1>Swolemates</h1>
        <p className="muted">Template slice — delete once the first real feature lands.</p>
      </header>

      {busy && <p className="muted">Signing in…</p>}
      {!busy && config.isError && (
        <p className="error">Couldn’t reach the server. Is the backend running?</p>
      )}
      {!busy && loginError && !whoami.data && <p className="error">{loginError}</p>}
      {!busy && config.data && !whoami.data && <SignIn config={config.data} />}
      {!busy && whoami.data && <AuthenticatedApp me={whoami.data} />}
    </main>
  );
}

/**
 * Gates the rest of the app behind onboarding (#9): a fresh account sees the welcome
 * form until it completes once, ever. `/profile` reaches the same form afterward as
 * plain settings — no router yet, same bare-pathname pattern used for `/callback`.
 */
function AuthenticatedApp({
  me,
}: {
  me: { user_sub: string; email: string | null; display_name: string | null };
}) {
  const profile = useProfile();
  const onSettingsRoute = window.location.pathname === "/profile";

  if (profile.isPending) return <p className="muted">Loading your profile…</p>;
  if (profile.isError) return <p className="error">Couldn’t load your profile.</p>;

  if (!profile.data.onboarding_completed_at) {
    return (
      <>
        <h2>Welcome to Swolemates</h2>
        <p className="muted">
          A couple of quick preferences, then you're in — nothing else to set up.
        </p>
        <ProfileForm profile={profile.data} completeOnboardingOnSave />
      </>
    );
  }

  if (onSettingsRoute) {
    return (
      <>
        <h2>Profile settings</h2>
        <ProfileForm profile={profile.data} />
      </>
    );
  }

  return <TmpxPage me={me} />;
}
