import Link from "next/link";
import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/Card";
import { ConfidenceBadge } from "@/components/ui/ConfidenceBadge";
import type { Json } from "@/lib/supabase/database.types";

type ConfidenceLevel = "low" | "medium" | "high";

// food_logs.confidence is a generic jsonb column — only photo_ai entries
// populate it, as a per-field map (e.g. { calories: "low", ... }). Surface
// the single worst level as one badge on the list.
function worstConfidence(confidence: Json | null): ConfidenceLevel | null {
  if (!confidence || typeof confidence !== "object" || Array.isArray(confidence)) {
    return null;
  }
  const levels = Object.values(confidence);
  if (levels.includes("low")) return "low";
  if (levels.includes("medium")) return "medium";
  if (levels.includes("high")) return "high";
  return null;
}

export default async function FoodPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const { data: logs } = await supabase
    .from("food_logs")
    .select(
      "id, name, serving_description, calories, protein_g, carbs_g, fat_g, fiber_g, meal_type, logged_at, confidence",
    )
    .eq("user_id", user!.id)
    .order("logged_at", { ascending: false });

  return (
    <div className="mx-auto flex max-w-lg flex-col gap-4 px-4 py-8">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-2xl font-semibold">Food log</h1>
        <Link
          href="/food/log"
          className="rounded-full bg-teal px-4 py-2 text-sm font-medium text-white"
        >
          Log food
        </Link>
      </div>

      {!logs || logs.length === 0 ? (
        <Card className="border-dashed text-center text-sm text-ink-soft">
          <div className="mb-1 font-display text-lg text-ink">No meals yet</div>
          Log your first meal to get started.
        </Card>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {logs.map((log) => {
            const confidence = worstConfidence(log.confidence);

            return (
              <li key={log.id}>
                <Card>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="font-mono text-[11px] tracking-wide text-ink-soft uppercase">
                        {new Date(log.logged_at).toLocaleString(undefined, {
                          hour: "numeric",
                          minute: "2-digit",
                          month: "short",
                          day: "numeric",
                        })}
                        {log.meal_type ? ` · ${log.meal_type}` : ""}
                      </div>
                      <div className="mt-0.5 text-[15px] font-semibold">
                        {log.name}
                      </div>
                    </div>
                    <div className="font-display text-xl font-semibold whitespace-nowrap">
                      {Math.round(log.calories)}
                      <span className="ml-1 font-mono text-xs font-normal text-ink-soft">
                        cal
                      </span>
                    </div>
                  </div>
                  <div className="mt-2 flex gap-3.5 font-mono text-xs text-ink-soft">
                    <span>P {Math.round(log.protein_g)}g</span>
                    <span>C {Math.round(log.carbs_g)}g</span>
                    <span>F {Math.round(log.fat_g)}g</span>
                    {log.fiber_g !== null && (
                      <span>Fiber {Math.round(log.fiber_g)}g</span>
                    )}
                  </div>
                  {confidence && (
                    <div className="mt-2">
                      <ConfidenceBadge level={confidence} />
                    </div>
                  )}
                </Card>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
