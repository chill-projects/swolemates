import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { hydrateQueryCache, persistQueryCache } from "./api/queryPersistence";
import { App } from "./App";
import { getToken } from "./auth/authkit";
import "./index.css";
import { interceptLinkClicks } from "./lib/routing";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // This is a mutation-heavy, data-current app — the PRD is explicit that stale
      // food/workout data actively misleads. Refetch rather than serve stale.
      staleTime: 0,
      refetchOnWindowFocus: true,
    },
  },
});

// Turns every internal <a href> in the app into a pushState navigation, so a tab
// switch no longer reloads the document and cold-boots the session.
interceptLinkClicks();

// A reload keeps sessionStorage, so the identity layer can be painted from the last
// load instead of behind a full-screen loader. Only worth restoring while a token is
// there to go with it: without one this tab is starting a session from scratch.
if (getToken()) hydrateQueryCache(queryClient);
persistQueryCache(queryClient);

const root = document.getElementById("root");
if (!root) throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
