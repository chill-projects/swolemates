import Link from "next/link";
import { IOSInstallBanner } from "@/components/IOSInstallBanner";
import { signOut } from "./actions";

const navLinkClass =
  "font-mono text-xs tracking-wide text-ink-soft uppercase hover:text-teal";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col">
      <IOSInstallBanner />
      <nav className="flex items-baseline justify-between border-b border-line bg-card px-4 py-3">
        <div className="flex items-baseline gap-4">
          <Link href="/dashboard" className="font-display text-base font-semibold text-ink">
            Swolemates
          </Link>
          <Link href="/workouts" className={navLinkClass}>
            Workouts
          </Link>
          <Link href="/food" className={navLinkClass}>
            Food
          </Link>
          <Link href="/partner" className={navLinkClass}>
            Partner
          </Link>
        </div>
        <form action={signOut} className="contents">
          <button type="submit" className={navLinkClass}>
            Sign out
          </button>
        </form>
      </nav>
      <main className="flex-1">{children}</main>
    </div>
  );
}
