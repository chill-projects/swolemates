import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { ConsistencyCalendar } from "@/components/ui/ConsistencyCalendar";
import { TodaySummary } from "@/components/ui/TodaySummary";
import {
  computeStreak,
  dateKeyFromDate,
  type DayTotals,
  type NutritionTargets,
} from "@/lib/tdee";

export default async function DashboardPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: profile } = await supabase
    .from("profiles")
    .select(
      "display_name, calorie_target, protein_target, carb_target, fat_target, fiber_target, goal_type",
    )
    .eq("id", user!.id)
    .single();

  const targets: NutritionTargets | null =
    profile?.calorie_target && profile?.protein_target
      ? {
          calories: profile.calorie_target,
          protein: profile.protein_target,
          carbs: profile.carb_target ?? 0,
          fat: profile.fat_target ?? 0,
          fiber: profile.fiber_target ?? 0,
        }
      : null;

  // Bounded to a window comfortably covering the visible calendar month plus
  // any realistic streak length — avoids pulling all-time food_logs history
  // just to render one month + a streak count.
  const since = new Date();
  since.setDate(since.getDate() - 40);

  const { data: allFood } = await supabase
    .from("food_logs")
    .select("calories, protein_g, carbs_g, fat_g, fiber_g, logged_at")
    .eq("user_id", user!.id)
    .gte("logged_at", since.toISOString());

  const dailyTotals: Record<string, DayTotals> = {};
  for (const log of allFood ?? []) {
    const key = dateKeyFromDate(new Date(log.logged_at));
    const existing = dailyTotals[key] ?? {
      calories: 0,
      protein: 0,
      carbs: 0,
      fat: 0,
      fiber: 0,
    };
    dailyTotals[key] = {
      calories: existing.calories + log.calories,
      protein: existing.protein + log.protein_g,
      carbs: existing.carbs + log.carbs_g,
      fat: existing.fat + log.fat_g,
      fiber: existing.fiber + (log.fiber_g ?? 0),
    };
  }

  const streakDays = computeStreak(new Set(Object.keys(dailyTotals)));

  const now = new Date();
  const todayTotals = dailyTotals[dateKeyFromDate(now)] ?? {
    calories: 0,
    protein: 0,
    carbs: 0,
    fat: 0,
    fiber: 0,
  };

  const todayLabel = now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <div className="flex items-baseline justify-between">
        <span className="font-mono text-xs tracking-wide text-ink-soft uppercase">
          {todayLabel}
        </span>
      </div>

      <h1 className="font-display text-2xl font-semibold">
        Hey, {profile?.display_name ?? user?.email}
      </h1>

      <TodaySummary totals={todayTotals} targets={targets} />

      <div className="grid grid-cols-3 gap-3">
        <Link href="/workouts/new">
          <Card className="text-center hover:border-teal">
            <div className="font-display text-lg font-semibold">🏋️</div>
            <div className="mt-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Log workout
            </div>
          </Card>
        </Link>
        <Link href="/food/log">
          <Card className="text-center hover:border-teal">
            <div className="font-display text-lg font-semibold">🍽️</div>
            <div className="mt-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Log food
            </div>
          </Card>
        </Link>
        <Link href="/partner">
          <Card className="text-center hover:border-teal">
            <div className="font-display text-lg font-semibold">🤝</div>
            <div className="mt-1 font-mono text-[11px] tracking-wide text-ink-soft uppercase">
              Partner
            </div>
          </Card>
        </Link>
      </div>

      <Card>
        <ConsistencyCalendar
          year={now.getFullYear()}
          month={now.getMonth()}
          dailyTotals={dailyTotals}
          streakDays={streakDays}
          targets={targets}
          goalType={profile?.goal_type ?? null}
        />
        {!targets ? (
          <p className="mt-3 text-sm text-ink-soft">
            <Link href="/settings/targets" className="font-medium text-teal">
              Set daily targets
            </Link>{" "}
            to see hit/miss coloring instead of just logged days.
          </p>
        ) : (
          <Link
            href="/settings/targets"
            className="mt-3 inline-block font-mono text-[11px] tracking-wide text-teal uppercase"
          >
            Edit targets
          </Link>
        )}
      </Card>
    </div>
  );
}
