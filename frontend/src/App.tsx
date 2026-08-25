import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useRedeemInvite } from "./api/partner";
import { useProfile } from "./api/profile";
import { SignIn } from "./auth/SignIn";
import { bootstrapSession, completeLogin, fetchAuthConfig, login, useWhoami } from "./auth/authkit";
import { IOSInstallBanner } from "./components/IOSInstallBanner";
import { McpConnectInfo } from "./components/McpConnectInfo";
import { NavBar } from "./components/NavBar";
import { DashboardPage } from "./pages/DashboardPage";
import {
  InvitePreviewPage,
  clearPendingInviteCode,
  readPendingInviteCode,
  setInviteRedeemError,
} from "./pages/InvitePreviewPage";
import { NutritionPage } from "./pages/NutritionPage";
import { PartnerPage } from "./pages/PartnerPage";
import { PlannedPage } from "./pages/PlannedPage";
import { ProfileForm } from "./pages/ProfileForm";
import { TemplatesPage } from "./pages/TemplatesPage";
import { WorkoutLivePage } from "./pages/WorkoutLivePage";

/**
 * A real router lands once more than one feature needs a route. For now it gates the
 * single authenticated screen behind auth + onboarding.
 */
export function App() {
  const [returningFromLogin, setReturningFromLogin] = useState(
    () => window.location.pathname === "/callback",
  );
  const [loginError, setLoginError] = useState<string | null>(null);
  // The callback exchange must run exactly once — effect re-runs (query state changes
  // re-render constantly) and a spent OAuth code would make retries fail anyway.
  const exchangeStarted = useRef(false);
  // Resumes a session from the stored refresh token before whoami runs, so a returning
  // visitor with no live access token doesn't get bounced to sign-in for a tab-lifetime
  // reason that no longer applies. Skipped on /callback — completeLogin() below handles
  // that session directly.
  const [sessionReady, setSessionReady] = useState(() => window.location.pathname === "/callback");

  const queryClient = useQueryClient();
  const config = useQuery({ queryKey: ["authConfig"], queryFn: fetchAuthConfig, retry: false });
  const whoami = useWhoami(sessionReady);
  const redeemInvite = useRedeemInvite();

  useEffect(() => {
    if (sessionReady) return;
    bootstrapSession().finally(() => setSessionReady(true));
  }, [sessionReady]);

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

      // A code stashed by InvitePreviewPage before this login started (#5, Partner
      // v1) — completeLogin() always resets the URL to "/" on success, so this is
      // the only place left to finish the redeem and send the new user somewhere
      // that shows the result. Sent to /partner either way; a failure (already
      // linked, expired mid-flight) surfaces there as a one-time banner instead of
      // blocking sign-in itself.
      if (result === "ok") {
        const pendingCode = readPendingInviteCode();
        if (pendingCode) {
          clearPendingInviteCode();
          redeemInvite.mutate(pendingCode, {
            onError: (err) => setInviteRedeemError(err.message),
            onSettled: () => window.location.assign("/partner"),
          });
        }
      }
    }).catch((err: unknown) => {
      // A thrown exchange (network/CORS failure) previously left the app stuck on
      // "Signing in…" forever — the promise rejected and nothing reset the state.
      console.error("Login completion threw:", err);
      setLoginError("Sign-in didn’t complete. Details are in the browser console.");
      setReturningFromLogin(false);
    });
  }, [returningFromLogin, config.data, queryClient]);

  const onInviteRoute = window.location.pathname.startsWith("/invite/");
  const busy = config.isPending || !sessionReady || whoami.isPending || returningFromLogin;

  return (
    <main>
      <IOSInstallBanner />
      <header>
        <h1>
          <a href="/">Swolemates</a>
        </h1>
      </header>

      {onInviteRoute ? (
        <InvitePreviewPage
          code={window.location.pathname.slice("/invite/".length).split("/")[0] ?? ""}
          config={config.data ?? null}
        />
      ) : (
        <>
          {busy && <p className="muted">Signing in…</p>}
          {!busy && config.isError && (
            <p className="error">Couldn’t reach the server. Is the backend running?</p>
          )}
          {!busy && loginError && !whoami.data && <p className="error">{loginError}</p>}
          {!busy && config.data && !whoami.data && <SignIn config={config.data} />}
          {!busy && whoami.data && <AuthenticatedApp me={whoami.data} />}
        </>
      )}
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
  const onWorkoutsLiveRoute = window.location.pathname === "/workouts/live";
  const onTemplatesRoute = window.location.pathname === "/templates";
  const onPlannedRoute = window.location.pathname === "/planned";
  const onPartnerRoute = window.location.pathname === "/partner";
  const onNutritionRoute = window.location.pathname === "/nutrition";

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

  return (
    <>
      <NavBar />
      {onSettingsRoute ? (
        <>
          <h2>
            Profile settings <McpConnectInfo />
          </h2>
          <ProfileForm profile={profile.data} />
        </>
      ) : onPartnerRoute ? (
        <PartnerPage />
      ) : onWorkoutsLiveRoute ? (
        <WorkoutLivePage me={me} />
      ) : onTemplatesRoute ? (
        <TemplatesPage me={me} />
      ) : onPlannedRoute ? (
        <PlannedPage me={me} />
      ) : onNutritionRoute ? (
        <NutritionPage me={me} />
      ) : (
        // Home ("/", and anything unrecognized) — the dashboard, per the user's
        // request that "Swolemates" in the header link somewhere real.
        <DashboardPage />
      )}
    </>
  );
}
