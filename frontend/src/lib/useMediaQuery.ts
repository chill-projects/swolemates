import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query from React.
 *
 * The meal plan needs this rather than a CSS-only switch because the two layouts
 * aren't the same markup rearranged — the phone shows one day at a time and holds a
 * selected-day state the week grid has no use for. Rendering both and hiding one would
 * mean two copies of that state drifting apart.
 *
 * Returns false where `matchMedia` doesn't exist (thumbnail capture, some embedded
 * viewers). The wide layout is the safer default: it shows everything, just tightly.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() =>
    typeof matchMedia === "function" ? matchMedia(query).matches : false,
  );

  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const list = matchMedia(query);
    setMatches(list.matches);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}
