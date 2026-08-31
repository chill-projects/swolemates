import type { ComponentType } from "react";
import { usePathname } from "../lib/routing";
import {
  CalendarIcon,
  DumbbellIcon,
  HeartHandshakeIcon,
  NotebookIcon,
  SettingsIcon,
  UtensilsIcon,
  type IconProps,
} from "./icons";

interface NavItem {
  href: string;
  label: string;
  icon: ComponentType<IconProps>;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Today", icon: CalendarIcon },
  { href: "/nutrition", label: "Nutrition", icon: UtensilsIcon },
  { href: "/workouts/live", label: "Workout", icon: DumbbellIcon },
  // Planned and Templates merged into one tab: the pattern sets which template runs
  // on which day, so they were never really two things.
  { href: "/plan", label: "Plan", icon: NotebookIcon },
  { href: "/partner", label: "Partner", icon: HeartHandshakeIcon },
  { href: "/profile", label: "Profile", icon: SettingsIcon },
];

// Old bookmarks still land on the merged tab, so Plan stays lit for them.
const PLAN_PATHS = ["/plan", "/planned", "/templates"];

/** Still plain anchors — real hrefs that cmd-click and copy properly — but the
 *  document-level handler in lib/routing turns an ordinary click into a pushState,
 *  so switching tabs no longer reloads the app.
 *  Renders into the top bar on desktop (text labels, no icons) and as a fixed
 *  icon-only tab bar on phones (`.nav-bar-label` there is visually hidden, not
 *  removed, so the accessible name — and the desktop label — stay one string);
 *  the split lives entirely in CSS (see `.nav-bar` in index.css). Active state on
 *  phones is the icon's color (`.nav-bar-item.active`, `currentColor` on every
 *  icon's stroke) — no separate marker. */
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
        const Icon = item.icon;
        return (
          <a
            key={item.href}
            href={item.href}
            className={active ? "nav-bar-item active" : "nav-bar-item"}
            aria-current={active ? "page" : undefined}
          >
            <Icon className="nav-bar-icon" />
            <span className="nav-bar-label">{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
