import { usePathname } from "../lib/routing";

interface NavItem {
  href: string;
  label: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Today" },
  { href: "/nutrition", label: "Nutrition" },
  { href: "/workouts/live", label: "Workout" },
  // Planned and Templates merged into one tab: the pattern sets which template runs
  // on which day, so they were never really two things.
  { href: "/plan", label: "Plan" },
  { href: "/partner", label: "Partner" },
  { href: "/profile", label: "Profile" },
];

// Old bookmarks still land on the merged tab, so Plan stays lit for them.
const PLAN_PATHS = ["/plan", "/planned", "/templates"];

/** Still plain anchors — real hrefs that cmd-click and copy properly — but the
 *  document-level handler in lib/routing turns an ordinary click into a pushState,
 *  so switching tabs no longer reloads the app.
 *  Renders into the top bar on desktop and as a fixed tab bar on phones; the split
 *  lives entirely in CSS (see `.nav-bar` in index.css). */
export function NavBar() {
  const pathname = usePathname();

  return (
    <nav className="nav-bar" aria-label="Main">
      {NAV_ITEMS.map((item) => {
        // "Today" is the home page, and anything unrecognized falls through to it
        // in App.tsx — so match it the same way rather than on an exact "/".
        const active =
          item.href === "/plan"
            ? PLAN_PATHS.includes(pathname)
            : item.href === "/"
              ? !NAV_ITEMS.some((other) => other.href !== "/" && other.href === pathname) &&
                !PLAN_PATHS.includes(pathname)
              : pathname === item.href;
        return (
          <a
            key={item.href}
            href={item.href}
            className={active ? "nav-bar-item active" : "nav-bar-item"}
            aria-current={active ? "page" : undefined}
          >
            <span className="nav-bar-dot" />
            <span>{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
