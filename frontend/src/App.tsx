import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { useWhoami } from "./api/tmpx";
import { SignIn } from "./auth/SignIn";
import { completeLogin, fetchAuthConfig } from "./auth/authkit";
import { TmpxPage } from "./pages/TmpxPage";

/**
 * Phase 6 replaces this with a real router and the ported screens. For now it gates the
 * template slice behind auth, which is the thing the platform work has to prove.
 */
export function App() {
  const [returningFromLogin, setReturningFromLogin] = useState(
    () => window.location.pathname === "/callback",
  );

  const config = useQuery({ queryKey: ["authConfig"], queryFn: fetchAuthConfig, retry: false });
  const whoami = useWhoami();

  // Finish the OAuth redirect before deciding what to render, otherwise the callback
  // flashes the sign-in screen on its way through.
  useEffect(() => {
    if (!returningFromLogin || !config.data) return;
    completeLogin(config.data).finally(() => {
      setReturningFromLogin(false);
      whoami.refetch();
    });
  }, [returningFromLogin, config.data, whoami]);

  const busy = config.isPending || whoami.isPending || returningFromLogin;

  return (
    <main>
      <header>
        <h1>Swolemates</h1>
        <p className="muted">Template slice — delete once the first real feature lands.</p>
      </header>

      {busy && <p className="muted">Loading…</p>}
      {!busy && config.isError && (
        <p className="error">Couldn’t reach the server. Is the backend running?</p>
      )}
      {!busy && config.data && !whoami.data && <SignIn config={config.data} />}
      {!busy && whoami.data && <TmpxPage userSub={whoami.data.user_sub} />}
    </main>
  );
}
