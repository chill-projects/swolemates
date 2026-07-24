import { completeOnboarding } from "./actions";

export default async function OnboardingPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string }>;
}) {
  const { error } = await searchParams;

  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 px-4">
      <h1 className="font-display text-2xl font-semibold">
        Let&apos;s get set up
      </h1>
      <p className="text-sm text-ink-soft">
        This is saved once — you can update it later in settings.
      </p>

      {error && (
        <p className="rounded-xl bg-coral-pale px-3 py-2 text-sm text-red">
          {error}
        </p>
      )}

      <form action={completeOnboarding} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Primary goal
          </span>
          <input
            name="goal"
            type="text"
            required
            placeholder="e.g. build muscle, lose weight, run a 5K"
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Secondary goal (optional)
          </span>
          <input
            name="secondaryGoal"
            type="text"
            placeholder="e.g. also want to get stronger"
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          <span className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
            Current routine
          </span>
          <textarea
            name="currentRoutine"
            rows={4}
            placeholder="Describe what you're currently doing, with sets/reps if relevant"
            className="rounded-xl border border-line bg-card px-3 py-2"
          />
        </label>

        <button
          type="submit"
          className="rounded-full bg-teal px-4 py-2.5 font-medium text-white"
        >
          Continue
        </button>
      </form>
    </div>
  );
}
