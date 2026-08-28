import { useEffect, useRef, useState } from "react";

import { type GoalInput, useGoals, useLogWeight, useSetGoals } from "../api/nutrition";
import {
  useCalculateTargets,
  useTdeeEstimate,
  useUpdateProfile,
  useWeightHistory,
} from "../api/profile";
import type { components } from "../api/generated";
import { useWhoami } from "../auth/authkit";
import { McpConnectInfo } from "../components/McpConnectInfo";
import { Card, PageHero } from "../components/ui";
import { detectedTimezone } from "../lib/datetime";
import {
  ACTIVITY_OPTIONS,
  GOAL_OPTIONS,
  LBS_PER_KG,
  TARGET_KEYS,
  type TargetKey,
  distributeMacros,
  redistributeOtherMacros,
  timezoneOptions,
  type ActivityLevel,
  type BiologicalSex,
  type GoalType,
  type MacroKey,
  type WeightUnit,
} from "./profileTargets";

type Profile = components["schemas"]["ProfileOut"];

const TARGET_LABELS: Record<TargetKey, { label: string; unit: string; note: string }> = {
  calories: { label: "Calories", unit: "kcal", note: "carbs, fat and fiber follow this" },
  protein_g: { label: "Protein", unit: "g", note: "anchored to bodyweight" },
  carbs_g: { label: "Carbs", unit: "g", note: "" },
  fat_g: { label: "Fat", unit: "g", note: "" },
  fiber_g: { label: "Fiber", unit: "g", note: "outside the calorie total" },
};

function formatWeight(lbs: number, unit: WeightUnit): string {
  const value = unit === "kg" ? lbs / LBS_PER_KG : lbs;
  return value.toFixed(1);
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * Profile (6a) — the long single form, split into the three things that actually
 * behave differently: what the app knows about you (auto-saves, feeds the estimate),
 * what the coach should remember, and the targets everything else measures against.
 */
export function ProfilePage({ profile }: { profile: Profile }) {
  const whoami = useWhoami();
  const updateProfile = useUpdateProfile();
  const tdee = useTdeeEstimate();
  const weights = useWeightHistory();
  const logWeight = useLogWeight();
  const goals = useGoals();
  const setGoals = useSetGoals();
  const calculateTargets = useCalculateTargets();

  const [weightUnit, setWeightUnit] = useState<WeightUnit>(profile.weight_unit);
  const [weightInput, setWeightInput] = useState("");
  const [coachNotes, setCoachNotes] = useState(profile.coach_notes ?? "");
  const detectedTz = detectedTimezone();
  const timezone = profile.timezone ?? detectedTz;

  const history = weights.data ?? [];
  const latest = history[history.length - 1];
  const first = history[0];
  const change =
    latest && first && history.length > 1
      ? Number(latest.weight_lbs) - Number(first.weight_lbs)
      : null;

  /** Every "About you" control writes on change — the band's estimate is derived from
   *  these, so a separate Save would leave the two visibly out of step. */
  function patch(body: Parameters<typeof updateProfile.mutate>[0]) {
    updateProfile.mutate(body);
  }

  function handleLogWeight() {
    const value = Number(weightInput);
    if (!value) return;
    const lbs = weightUnit === "kg" ? value * LBS_PER_KG : value;
    logWeight.mutate(lbs, {
      onSuccess: () => {
        setWeightInput("");
        void weights.refetch();
        void tdee.refetch();
      },
    });
  }

  // Targets are seeded once from whichever arrives first — saved goals or a fresh
  // calculation — then left alone; re-seeding on every refetch would clobber edits.
  const [targets, setTargets] = useState<Record<TargetKey, string>>({
    calories: "",
    protein_g: "",
    carbs_g: "",
    fat_g: "",
    fiber_g: "",
  });
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current || !goals.data || goals.data.length === 0) return;
    seeded.current = true;
    const byKey = Object.fromEntries(goals.data.map((g) => [g.trackable_key, g.target_value]));
    setTargets((t) => ({
      ...t,
      ...Object.fromEntries(
        TARGET_KEYS.filter((k) => byKey[k] != null).map((k) => [k, String(byKey[k])]),
      ),
    }));
  }, [goals.data]);

  function handleTargetChange(key: TargetKey, value: string) {
    if (key === "fiber_g") {
      setTargets((t) => ({ ...t, fiber_g: value }));
      return;
    }
    if (key === "calories") {
      const protein = Number(targets.protein_g);
      const calories = Number(value);
      if (value && calories && protein) {
        const { carbs, fat, fiber } = distributeMacros(calories, protein);
        setTargets((t) => ({
          ...t,
          calories: value,
          carbs_g: String(carbs),
          fat_g: String(fat),
          fiber_g: String(fiber),
        }));
      } else {
        setTargets((t) => ({ ...t, calories: value }));
      }
      return;
    }
    const calories = Number(targets.calories);
    const next = Number(value);
    if (!value || !next || !calories) {
      setTargets((t) => ({ ...t, [key]: value }));
      return;
    }
    const current: Record<MacroKey, number> = {
      protein_g: Number(targets.protein_g) || 0,
      carbs_g: Number(targets.carbs_g) || 0,
      fat_g: Number(targets.fat_g) || 0,
    };
    const updated = redistributeOtherMacros(key as MacroKey, next, current, calories);
    setTargets((t) => ({
      ...t,
      protein_g: String(updated.protein_g),
      carbs_g: String(updated.carbs_g),
      fat_g: String(updated.fat_g),
    }));
  }

  function handleSaveTargets() {
    const body: GoalInput[] = TARGET_KEYS.filter((k) => targets[k] !== "").map((k) => ({
      trackable_key: k,
      target_value: Number(targets[k]),
    }));
    if (body.length > 0) setGoals.mutate(body);
  }

  function handleRecalculate() {
    calculateTargets.mutate(undefined, {
      onSuccess: (data) => {
        if (!data) return;
        seeded.current = true;
        setTargets({
          calories: String(data.calories),
          protein_g: String(data.protein_g),
          carbs_g: String(data.carbs_g),
          fat_g: String(data.fat_g),
          fiber_g: String(data.fiber_g),
        });
      },
    });
  }

  const totalHeightIn = profile.height_in ? Math.round(Number(profile.height_in)) : null;

  return (
    <>
      <PageHero
        eyebrow={whoami.data?.display_name ?? whoami.data?.email ?? "Your profile"}
        title="Six numbers set every target in the app."
        lead="Weight, sex, age, height, activity and goal produce your TDEE. Everything below is editable afterwards — the estimate is a starting point, not a rule."
        aside={
          <div className="profile-figures">
            <div>
              <div className="profile-figure profile-figure--teal">
                {tdee.data?.tdee ? tdee.data.tdee.toLocaleString() : "—"}
              </div>
              <div className="profile-figure-label">est. TDEE · kcal/day</div>
            </div>
            <div className="profile-figure-divider">
              <div className="profile-figure">
                {latest ? formatWeight(Number(latest.weight_lbs), weightUnit) : "—"}
              </div>
              <div className="profile-figure-label">
                {latest ? `${weightUnit} · logged ${shortDate(latest.logged_at)}` : "no weight yet"}
              </div>
            </div>
          </div>
        }
      />

      <div className="page-body">
        {tdee.data && tdee.data.missing.length > 0 && (
          <p className="muted">
            Add {tdee.data.missing.join(", ")} below and the estimate fills in.
          </p>
        )}

        <div className="page-grid page-grid--split">
          <div className="page-grid">
            <Card
              title="Today's weight"
              meta={
                <span className="card-meta">
                  {change === null
                    ? "log a few to see a trend"
                    : `${change > 0 ? "+" : "−"}${formatWeight(Math.abs(change), weightUnit)} ${weightUnit} over ${history.length} weigh-ins`}
                </span>
              }
            >
              <div className="weight-row">
                <input
                  className="weight-input"
                  type="number"
                  inputMode="decimal"
                  value={weightInput}
                  onChange={(e) => setWeightInput(e.target.value)}
                  placeholder={weightUnit === "kg" ? "68.0" : "150.0"}
                  aria-label={`Today's weight in ${weightUnit}`}
                />
                <div className="unit-toggle" role="group" aria-label="Weight unit">
                  {(["kg", "lbs"] as const).map((u) => (
                    <button
                      key={u}
                      type="button"
                      aria-pressed={weightUnit === u}
                      onClick={() => {
                        setWeightUnit(u);
                        patch({ weight_unit: u });
                      }}
                    >
                      {u}
                    </button>
                  ))}
                </div>
                <button
                  type="button"
                  className="btn--primary"
                  onClick={handleLogWeight}
                  disabled={!weightInput || logWeight.isPending}
                >
                  Log
                </button>
              </div>
              {logWeight.isError && <p className="error">{logWeight.error.message}</p>}
              <WeightTrend history={history} unit={weightUnit} />
            </Card>

            <Card
              title="About you"
              meta={<span className="card-meta">feeds the TDEE estimate</span>}
            >
              <div className="setting-rows">
                <SettingRow label="Sex">
                  <select
                    value={profile.sex ?? ""}
                    onChange={(e) => patch({ sex: (e.target.value || null) as BiologicalSex })}
                  >
                    <option value="">—</option>
                    <option value="female">Female</option>
                    <option value="male">Male</option>
                  </select>
                </SettingRow>

                <SettingRow label="Age">
                  <input
                    type="number"
                    defaultValue={profile.age ?? ""}
                    onBlur={(e) => patch({ age: e.target.value ? Number(e.target.value) : null })}
                    aria-label="Age"
                  />
                </SettingRow>

                <SettingRow label="Height">
                  <span className="height-pair">
                    <input
                      type="number"
                      defaultValue={totalHeightIn ? Math.floor(totalHeightIn / 12) : ""}
                      onBlur={(e) =>
                        patch({
                          height_in:
                            (Number(e.target.value) || 0) * 12 + ((totalHeightIn ?? 0) % 12),
                        })
                      }
                      aria-label="Height, feet"
                    />
                    <span className="unit">ft</span>
                    <input
                      type="number"
                      defaultValue={totalHeightIn ? totalHeightIn % 12 : ""}
                      onBlur={(e) =>
                        patch({
                          height_in:
                            Math.floor((totalHeightIn ?? 0) / 12) * 12 + (Number(e.target.value) || 0),
                        })
                      }
                      aria-label="Height, inches"
                    />
                    <span className="unit">in</span>
                  </span>
                </SettingRow>

                <SettingRow label="Activity level">
                  <select
                    value={profile.activity_level ?? ""}
                    onChange={(e) =>
                      patch({ activity_level: (e.target.value || null) as ActivityLevel })
                    }
                  >
                    <option value="">—</option>
                    {ACTIVITY_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </SettingRow>

                <SettingRow label="Goal">
                  <select
                    value={profile.goal_type ?? ""}
                    onChange={(e) => patch({ goal_type: (e.target.value || null) as GoalType })}
                  >
                    <option value="">—</option>
                    {GOAL_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                </SettingRow>

                <SettingRow label="Timezone">
                  <select value={timezone} onChange={(e) => patch({ timezone: e.target.value })}>
                    {timezoneOptions(timezone).map((z) => (
                      <option key={z} value={z}>
                        {z}
                      </option>
                    ))}
                  </select>
                </SettingRow>
              </div>
              <p className="card-note">
                {timezone === detectedTz
                  ? "Timezone detected from your browser — sets which day meals and workouts land on."
                  : `Overriding your browser's ${detectedTz}.`}
              </p>
            </Card>
          </div>

          <div className="page-grid">
            <Card
              title="Daily targets"
              meta={
                <button type="button" className="btn-small" onClick={handleRecalculate}>
                  {calculateTargets.isPending ? "Calculating…" : "Recalculate from stats"}
                </button>
              }
            >
              {calculateTargets.isError && (
                <p className="error">{calculateTargets.error.message}</p>
              )}
              <div className="target-rows">
                {TARGET_KEYS.map((key) => (
                  <div key={key} className="target-row">
                    <div className="row-main">
                      <div className="row-name">{TARGET_LABELS[key].label}</div>
                      {TARGET_LABELS[key].note && (
                        <div className="row-detail">{TARGET_LABELS[key].note}</div>
                      )}
                    </div>
                    <label
                      className={key === "calories" ? "target-value target-value--lead" : "target-value"}
                    >
                      <input
                        type="number"
                        value={targets[key]}
                        onChange={(e) => handleTargetChange(key, e.target.value)}
                        aria-label={`${TARGET_LABELS[key].label} target`}
                      />
                      <span className="unit">{TARGET_LABELS[key].unit}</span>
                    </label>
                  </div>
                ))}
              </div>
              <div className="card-foot">
                <span className="card-meta">
                  Edit calories and carbs, fat and fiber follow. Edit a macro and the other two
                  split the difference.
                </span>
                <button
                  type="button"
                  className="btn-teal"
                  onClick={handleSaveTargets}
                  disabled={setGoals.isPending}
                >
                  {setGoals.isPending ? "Saving…" : "Save targets"}
                </button>
              </div>
            </Card>

            <Card
              title="Coach notes"
              meta={<span className="card-meta">read before every plan</span>}
            >
              <textarea
                className="coach-notes"
                value={coachNotes}
                onChange={(e) => setCoachNotes(e.target.value)}
                placeholder="e.g. bad left knee — no deep lunges. Dumbbells up to 24 kg at home."
                aria-label="Coach notes"
              />
              <div className="card-foot">
                <span className="card-meta">
                  {coachNotes === (profile.coach_notes ?? "")
                    ? "Claude reads this before writing a plan"
                    : "Unsaved changes"}
                </span>
                <button
                  type="button"
                  onClick={() => patch({ coach_notes: coachNotes })}
                  disabled={coachNotes === (profile.coach_notes ?? "") || updateProfile.isPending}
                >
                  Save notes
                </button>
              </div>
            </Card>

            <Card title="Connect Claude">
              <p className="card-note">
                Log meals and workouts by chatting instead. <McpConnectInfo />
              </p>
            </Card>
          </div>
        </div>
      </div>
    </>
  );
}

function SettingRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="setting-row">
      <span className="setting-label">{label}</span>
      <span className="setting-control">{children}</span>
    </label>
  );
}

/** Four most recent weigh-ins as bars, scaled between the lightest and heaviest so
 *  small real changes stay visible — a zero-based axis would flatten them to nothing. */
function WeightTrend({
  history,
  unit,
}: {
  history: components["schemas"]["WeightEntryOut"][];
  unit: WeightUnit;
}) {
  const points = history.slice(-4);
  if (points.length < 2) return null;

  const values = points.map((p) => Number(p.weight_lbs));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;

  return (
    <div className="weight-trend">
      {points.map((p, i) => (
        <div key={p.logged_at} className="weight-trend-col">
          <div className="weight-trend-value">
            {formatWeight(values[i]!, unit)} {unit}
          </div>
          <div className="weight-trend-track">
            <div
              className="weight-trend-bar"
              style={{ height: `${20 + ((values[i]! - min) / span) * 80}%` }}
            />
          </div>
          <div className="weight-trend-date">{shortDate(p.logged_at)}</div>
        </div>
      ))}
    </div>
  );
}
