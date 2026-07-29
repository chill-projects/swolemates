import { TmpxPage } from "./pages/TmpxPage";

/**
 * Phase 6 replaces this with a real router and the ported screens. For now it renders
 * the template slice, which is the thing the platform work has to prove.
 */
export function App() {
  return (
    <main>
      <header>
        <h1>Swolemates</h1>
        <p className="muted">Template slice — delete once the first real feature lands.</p>
      </header>
      <TmpxPage />
    </main>
  );
}
