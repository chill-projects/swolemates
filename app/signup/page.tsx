import Link from "next/link";
import { signup } from "./actions";

export default async function SignupPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; checkEmail?: string }>;
}) {
  const { error, checkEmail } = await searchParams;

  return (
    <div className="mx-auto flex min-h-screen max-w-sm flex-col justify-center gap-4 px-4">
      <h1 className="font-display text-2xl font-semibold">Swolemates</h1>

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      {checkEmail && (
        <p className="rounded-xl bg-teal-pale px-3 py-2 text-sm text-teal">
          Account created — check your email to confirm before logging in.
        </p>
      )}

      <form action={signup} className="flex flex-col gap-3">
        <input
          name="displayName"
          type="text"
          required
          placeholder="Display name"
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
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
          minLength={6}
          placeholder="Password"
          className="rounded-xl border border-line bg-card px-3 py-2"
        />
        <button
          type="submit"
          className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
        >
          Create account
        </button>
      </form>

      <p className="text-sm text-ink-soft">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-teal">
          Log in
        </Link>
      </p>
    </div>
  );
}
