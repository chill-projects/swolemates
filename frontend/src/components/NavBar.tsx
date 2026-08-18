interface NavItem {
  href: string;
  label: string;
  icon: string;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Nutrition", icon: "🍽️" },
  { href: "/workouts/live", label: "Workout", icon: "🏋️" },
  { href: "/templates", label: "Templates", icon: "📋" },
  { href: "/planned", label: "Planned", icon: "🗓️" },
  { href: "/profile", label: "Profile", icon: "⚙️" },
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
            <span className="nav-bar-icon" aria-hidden="true">
              {item.icon}
            </span>
            <span>{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}
