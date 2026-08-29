import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { useRedeemInvite } from "./api/partner";
import { useProfile } from "./api/profile";
import { SignIn } from "./auth/SignIn";
import {
  bootstrapSession,
  completeLogin,
  fetchAuthConfig,
  getToken,
  isTokenFresh,
  login,
  useWhoami,
  WhoamiError,
} from "./auth/authkit";
import { isShellBusy, resolveAuthState } from "./auth/sessionState";
import { IOSInstallBanner } from "./components/IOSInstallBanner";
import { navigate, usePathname } from "./lib/routing";
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
import { PlanPage } from "./pages/PlanPage";
import { ProfileForm } from "./pages/ProfileForm";
import { ProfilePage } from "./pages/ProfilePage";
import { WorkoutLivePage } from "./pages/WorkoutLivePage";

/**
 * Routing is still a pathname switch, but a reactive one (see lib/routing) — the shell
 * stays mounted across a tab change, so `config`/`whoami` and the query cache survive
 * it and there's no cold-boot gap to paper over.
 */
export function App() {
  const pathname = usePathname();
  const [returningFromLogin, setReturningFromLogin] = useState(pathname === "/callback");
  const [loginError, setLoginError] = useState<string | null>(null);
  // The callback exchange must run exactly once — effect re-runs (query state changes
  // re-render constantly) and a spent OAuth code would make retries fail anyway.
  const exchangeStarted = useRef(false);
  // Resumes a session from the stored refresh token before whoami runs, so a returning
  // visitor with no live access token doesn't get bounced to sign-in for a tab-lifetime
  // reason that no longer applies. Skipped on /callback — completeLogin() below handles
  // that session directly.
  const [sessionReady, setSessionReady] = useState(pathname === "/callback");

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
      // reset, not invalidate: whoami already ran (and 401'd) on the bare /callback
      // mount before there was a token. Resetting puts it back to `pending` so the
      // shell shows "Signing in…" through the refetch instead of flashing SignIn.
      void queryClient.resetQueries({ queryKey: ["whoami"] });
      setReturningFromLogin(false);

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
            onSettled: () => navigate("/partner"),
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

  const onInviteRoute = pathname.startsWith("/invite/");

  // Read the token live rather than latching it at mount, so it lapses with the token
  // instead of outliving it. See auth/sessionState for why it counts at all.
  const authState = resolveAuthState({
    hasWhoami: Boolean(whoami.data),
    whoamiSaysAnonymous: whoami.error instanceof WhoamiError && whoami.error.kind === "anonymous",
    tokenLooksLive: isTokenFresh(getToken()),
  });
  const busy = isShellBusy({
    authState,
    returningFromLogin,
    checksPending: config.isPending || !sessionReady || whoami.isPending,
  });

  return (
    <>
      <IOSInstallBanner />
      <header className="app-bar">
        <div className="app-bar-inner">
          <a className="app-brand" href="/">
            {/* Decorative: the wordmark right beside it already names the app, so a
                screen reader shouldn't read the logo out as well. Same file the PWA
                and the browser tab use, so the mark only ever changes in one place. */}
            <img className="app-brand-mark" src="/icon-192.png" alt="" width={28} height={28} />
            Swolemates
          </a>
          {/* The nav only exists once there's an onboarded account behind it — the
              top bar carries just the wordmark until then. */}
          {authState === "authenticated" && <OnboardedNav />}
        </div>
      </header>

      <main className="app-main">
        {/* Pages own their own padding, so that a full-bleed hero band can run
            edge to edge across the content column. Everything else gets wrapped. */}
        {!onInviteRoute && !busy && authState === "authenticated" ? (
          <AuthenticatedApp />
        ) : (
          <div className="page-body">
            {onInviteRoute ? (
              <InvitePreviewPage
                code={pathname.slice("/invite/".length).split("/")[0] ?? ""}
                config={config.data ?? null}
              />
            ) : (
              <>
                {busy && <p className="muted">Signing in…</p>}
                {!busy && (config.isError || authState === "unknown") && (
                  <p className="error">
                    Couldn’t reach the server.{" "}
                    <button
                      type="button"
                      onClick={() => {
                        void config.refetch();
                        void whoami.refetch();
                      }}
                    >
                      Retry
                    </button>
                  </p>
                )}
                {!busy && loginError && authState !== "authenticated" && (
                  <p className="error">{loginError}</p>
                )}
                {!busy && config.data && authState === "anonymous" && (
                  <SignIn config={config.data} />
                )}
              </>
            )}
          </div>
        )}
      </main>
    </>
  );
}

/** The nav lives in the top bar, but whether to show it depends on onboarding —
 *  which is `AuthenticatedApp`'s call, a level down. Both read the same cached
 *  profile query, so asking here costs nothing extra. */
function OnboardedNav() {
  const profile = useProfile();
  return profile.data?.onboarding_completed_at ? <NavBar /> : null;
}

/**
 * Gates the rest of the app behind onboarding (#9): a fresh account sees the welcome
 * form until it completes once, ever. `/profile` reaches the same form afterward as
 * plain settings — no router yet, same bare-pathname pattern used for `/callback`.
 */
function AuthenticatedApp() {
  const profile = useProfile();
  const pathname = usePathname();
  const onSettingsRoute = pathname === "/profile";
  const onWorkoutsLiveRoute = pathname === "/workouts/live";
  // /templates and /planned were separate tabs before they merged into Plan; both
  // still resolve here so existing links and bookmarks keep working.
  const onPlanRoute = ["/plan", "/templates", "/planned"].includes(pathname);
  const onPartnerRoute = pathname === "/partner";
  const onNutritionRoute = pathname === "/nutrition";

  if (profile.isPending) {
    return (
      <div className="page-body">
        <p className="muted">Loading your profile…</p>
      </div>
    );
  }
  if (profile.isError) {
    return (
      <div className="page-body">
        <p className="error">Couldn’t load your profile.</p>
      </div>
    );
  }

  if (!profile.data.onboarding_completed_at) {
    return (
      <div className="page-body">
        <h2>Welcome to Swolemates</h2>
        <p className="muted">
          A couple of quick preferences, then you're in — nothing else to set up.
        </p>
        <ProfileForm profile={profile.data} completeOnboardingOnSave />
      </div>
    );
  }

  // Nutrition, Workout and the dashboard open with a full-bleed hero band, so they
  // lay themselves out. The rest are plain stacks inside .page-body's padding.
  if (onWorkoutsLiveRoute) return <WorkoutLivePage />;
  if (onNutritionRoute) return <NutritionPage />;
  if (onPlanRoute) return <PlanPage />;
  if (onSettingsRoute) return <ProfilePage profile={profile.data} />;
  if (onPartnerRoute) {
    return (
      <div className="page-body">
        <PartnerPage />
      </div>
    );
  }
  // Home ("/", and anything unrecognized) — the dashboard, per the user's
  // request that "Swolemates" in the header link somewhere real.
  return <DashboardPage />;
}
