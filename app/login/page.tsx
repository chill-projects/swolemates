import Link from "next/link";
import { login } from "./actions";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
      <h1 className="font-display text-2xl font-semibold">Swolemates</h1>

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <form action={login} className="flex flex-col gap-3">
        <input
          name="email"
          type="email"
          required
          placeholder="Email"
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
        <input
          name="password"
          type="password"
          required
          placeholder="Password"
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
        <button
          type="submit"
          className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
        >
          Log in
        </button>
      </form>

      <p className="text-sm text-ink-soft">
        No account?{" "}
        <Link href="/signup" className="font-medium text-teal">
          Sign up
        </Link>
      </p>
    </div>
  );
}
