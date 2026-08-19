import type { ReactNode } from "react";

import {
  CalendarIcon,
  DumbbellIcon,
  HeartHandshakeIcon,
  LayoutTemplateIcon,
  SettingsIcon,
  UtensilsIcon,
} from "./icons";

interface NavItem {
  href: string;
  label: string;
  Icon: (props: { className?: string }) => ReactNode;
}

// No Dashboard entry: it's the home page now (the "Swolemates" wordmark links
// there), not a nav-bar destination.
const NAV_ITEMS: NavItem[] = [
  { href: "/nutrition", label: "Nutrition", Icon: UtensilsIcon },
  { href: "/workouts/live", label: "Workout", Icon: DumbbellIcon },
  { href: "/templates", label: "Templates", Icon: LayoutTemplateIcon },
  { href: "/planned", label: "Planned", Icon: CalendarIcon },
  { href: "/partner", label: "Partner", Icon: HeartHandshakeIcon },
  { href: "/profile", label: "Profile", Icon: SettingsIcon },
];

/** Plain anchors, not client-side routing — App.tsx reads `window.location.pathname`
 *  once per load, so a normal navigation (full reload) is what actually works today. */
export function NavBar() {
  const pathname = window.location.pathname;

  return (
    <nav className="nav-bar" aria-label="Main">
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <a
            key={item.href}
            href={item.href}
            className={active ? "nav-bar-item active" : "nav-bar-item"}
            aria-current={active ? "page" : undefined}
          >
            <item.Icon className="nav-bar-icon" />
            <span>{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
