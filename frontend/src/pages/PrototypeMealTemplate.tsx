import { useEffect, useState } from "react";

/**
 * PROTOTYPE — throwaway. Answers: should a meal template be a multi-item bundle
 * (a whole meal saved at once) or a single-item favorite (individual foods saved,
 * chained together to build a meal)? See ticket #4 (Nutrition v1) on the map (#1).
 *
 * Three variants of the meal-template flow, switchable via ?variant=, mounted at
 * /prototype/meal-template (see App.tsx). No persistence — state resets on reload.
 * Not part of the real app; delete this file and its App.tsx hook once the answer
 * is captured on the throwaway branch per the /prototype skill.
 */

type TrackableKey = "calories" | "protein_g" | "carbs_g" | "fat_g" | "fiber_g";

const TRACKABLES: { key: TrackableKey; label: string }[] = [
  { key: "calories", label: "Calories" },
  { key: "protein_g", label: "Protein (g)" },
  { key: "carbs_g", label: "Carbs (g)" },
  { key: "fat_g", label: "Fat (g)" },
  { key: "fiber_g", label: "Fiber (g)" },
];

interface Item {
  id: string;
  name: string;
  servingDescription: string;
  values: Record<TrackableKey, number>;
}

let nextId = 100;
function makeId() {
  return String(nextId++);
}

const SEED_ITEMS: Item[] = [
  {
    id: "1",
    name: "2 scrambled eggs",
    servingDescription: "2 large eggs",
    values: { calories: 180, protein_g: 12, carbs_g: 2, fat_g: 14, fiber_g: 0 },
  },
  {
    id: "2",
    name: "Whole wheat toast",
    servingDescription: "1 slice",
    values: { calories: 90, protein_g: 4, carbs_g: 16, fat_g: 1, fiber_g: 2 },
  },
  {
    id: "3",
    name: "Black coffee",
    servingDescription: "12 oz",
    values: { calories: 5, protein_g: 0, carbs_g: 0, fat_g: 0, fiber_g: 0 },
  },
];

function sumValues(items: Item[]): Record<TrackableKey, number> {
  const out = { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0, fiber_g: 0 };
  for (const item of items) {
    for (const t of TRACKABLES) out[t.key] += item.values[t.key];
  }
  return out;
}

function StatePanel({ label, data }: { label: string; data: unknown }) {
  return (
    <details style={{ marginTop: "1.5rem", fontSize: "0.75rem" }}>
      <summary className="muted">{label} (debug state)</summary>
      <pre
        style={{
          background: "rgba(127,127,127,0.1)",
          padding: "0.75rem",
          borderRadius: "0.375rem",
          overflowX: "auto",
        }}
      >
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  );
}

function ItemForm({
  item,
  onChange,
  onRemove,
}: {
  item: Item;
  onChange: (next: Item) => void;
  onRemove?: () => void;
}) {
  return (
    <div
      style={{
        border: "1px solid currentColor",
        borderRadius: "0.5rem",
        padding: "0.75rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.4rem",
      }}
    >
      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
        <input
          value={item.name}
          onChange={(e) => onChange({ ...item, name: e.target.value })}
          style={{ flex: 1, fontWeight: 600 }}
        />
        {onRemove && (
          <button type="button" onClick={onRemove} style={{ fontSize: "0.7rem" }}>
            Remove
          </button>
        )}
      </div>
      <input
        value={item.servingDescription}
        onChange={(e) => onChange({ ...item, servingDescription: e.target.value })}
        className="muted"
      />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: "0.4rem" }}>
        {TRACKABLES.map((t) => (
          <label key={t.key} style={{ fontSize: "0.65rem", display: "flex", flexDirection: "column", gap: "0.15rem" }}>
            {t.label}
            <input
              type="number"
              value={item.values[t.key]}
              onChange={(e) =>
                onChange({ ...item, values: { ...item.values, [t.key]: Number(e.target.value) } })
              }
            />
          </label>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant A — whole-meal bundle: save everything logged right now as one named
// template; templates list/expand as groups; logging a template writes all its
// items at once. Matches the decided data model 1:1 (one `logs` header, many
// `log_values` rows) extended to templates (one template, many template items).
// ---------------------------------------------------------------------------

interface MealTemplate {
  id: string;
  name: string;
  items: Item[];
}

function VariantA() {
  const [today, setToday] = useState<Item[]>(SEED_ITEMS);
  const [templates, setTemplates] = useState<MealTemplate[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loggedGroups, setLoggedGroups] = useState<{ id: string; loggedAt: string; items: Item[] }[]>([]);

  function saveAsTemplate() {
    const name = window.prompt("Template name?", "My usual breakfast");
    if (!name) return;
    setTemplates((prev) => [...prev, { id: makeId(), name, items: today.map((i) => ({ ...i, id: makeId() })) }]);
  }

  function logTemplate(t: MealTemplate) {
    setLoggedGroups((prev) => [
      { id: makeId(), loggedAt: new Date().toLocaleTimeString(), items: t.items.map((i) => ({ ...i, id: makeId() })) },
      ...prev,
    ]);
  }

  function toggle(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>A — Whole-meal bundle</h2>
      <p className="muted">
        Log a few items, then save the whole group as one template. Templates apply as a group.
      </p>

      <strong>Today&apos;s log</strong>
      {today.map((item) => (
        <ItemForm
          key={item.id}
          item={item}
          onChange={(next) => setToday((prev) => prev.map((i) => (i.id === next.id ? next : i)))}
          onRemove={() => setToday((prev) => prev.filter((i) => i.id !== item.id))}
        />
      ))}
      <button type="button" onClick={saveAsTemplate} disabled={today.length === 0}>
        Save these {today.length} item(s) as a template
      </button>

      <strong>Your templates</strong>
      {templates.length === 0 && <p className="muted">No templates yet.</p>}
      {templates.map((t) => (
        <div key={t.id} style={{ border: "1px dashed currentColor", borderRadius: "0.5rem", padding: "0.6rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <button type="button" onClick={() => toggle(t.id)} style={{ border: "none", padding: 0 }}>
              {expanded.has(t.id) ? "▾" : "▸"} <strong>{t.name}</strong>{" "}
              <span className="muted">({t.items.length} items)</span>
            </button>
            <button type="button" onClick={() => logTemplate(t)}>
              Log this template
            </button>
          </div>
          {expanded.has(t.id) && (
            <ul className="muted" style={{ marginTop: "0.4rem" }}>
              {t.items.map((i) => (
                <li key={i.id}>
                  {i.name} — {i.values.calories} cal
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}

      <strong>Logged from templates</strong>
      {loggedGroups.map((g) => (
        <div key={g.id} className="muted">
          {g.loggedAt}: {g.items.map((i) => i.name).join(", ")} (
          {sumValues(g.items).calories} cal total)
        </div>
      ))}

      <StatePanel label="Variant A state" data={{ today, templates, loggedGroups }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant B — single-item favorites: no grouping. Each item favorited alone;
// a "meal" is just several favorites tapped in a row. Simpler schema (one
// `templates` row = one item), clunkier for a compound meal.
// ---------------------------------------------------------------------------

function VariantB() {
  const [today, setToday] = useState<Item[]>(SEED_ITEMS);
  const [favorites, setFavorites] = useState<Item[]>([]);
  const [loggedFromFavorites, setLoggedFromFavorites] = useState<Item[]>([]);

  function favorite(item: Item) {
    setFavorites((prev) => [...prev, { ...item, id: makeId() }]);
  }

  function addFavoriteToToday(fav: Item) {
    const copy = { ...fav, id: makeId() };
    setToday((prev) => [...prev, copy]);
    setLoggedFromFavorites((prev) => [copy, ...prev]);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>B — Single-item favorites</h2>
      <p className="muted">Every item is favorited on its own. Build a meal by adding favorites one at a time.</p>

      <strong>Today&apos;s log</strong>
      {today.map((item) => (
        <div key={item.id} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <ItemForm
            item={item}
            onChange={(next) => setToday((prev) => prev.map((i) => (i.id === next.id ? next : i)))}
            onRemove={() => setToday((prev) => prev.filter((i) => i.id !== item.id))}
          />
          <button type="button" onClick={() => favorite(item)} title="Save as favorite">
            ☆
          </button>
        </div>
      ))}

      <strong>Favorites (flat list)</strong>
      {favorites.length === 0 && <p className="muted">No favorites yet — star an item above.</p>}
      <ul style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
        {favorites.map((f) => (
          <li key={f.id} style={{ display: "flex", justifyContent: "space-between" }}>
            <span>
              {f.name} <span className="muted">— {f.values.calories} cal</span>
            </span>
            <button type="button" onClick={() => addFavoriteToToday(f)}>
              + Add to today
            </button>
          </li>
        ))}
      </ul>

      <p className="muted">
        To log &quot;breakfast&quot; (3 items) here means tapping + three separate times — no single action logs
        the whole meal.
      </p>

      <StatePanel label="Variant B state" data={{ today, favorites, loggedFromFavorites }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Variant C — multi-item, but the primary affordance is a swipeable stack of
// whole-meal cards with an aggregate macro badge, not itemized forms. Same
// underlying bundle model as A, different information hierarchy: totals first,
// per-item edit is a secondary drill-down.
// ---------------------------------------------------------------------------

function VariantC() {
  const [templates, setTemplates] = useState<MealTemplate[]>([
    { id: "t1", name: "Usual breakfast", items: SEED_ITEMS },
  ]);
  const [openId, setOpenId] = useState<string | null>(null);
  const [loggedGroups, setLoggedGroups] = useState<{ id: string; loggedAt: string; name: string; items: Item[] }[]>(
    [],
  );

  function logTemplate(t: MealTemplate) {
    setLoggedGroups((prev) => [
      { id: makeId(), loggedAt: new Date().toLocaleTimeString(), name: t.name, items: t.items.map((i) => ({ ...i })) },
      ...prev,
    ]);
  }

  function bumpQty(t: MealTemplate, itemId: string, deltaPct: number) {
    setTemplates((prev) =>
      prev.map((tpl) =>
        tpl.id !== t.id
          ? tpl
          : {
              ...tpl,
              items: tpl.items.map((i) =>
                i.id !== itemId
                  ? i
                  : {
                      ...i,
                      values: Object.fromEntries(
                        TRACKABLES.map((tr) => [tr.key, Math.round(i.values[tr.key] * (1 + deltaPct))]),
                      ) as Record<TrackableKey, number>,
                    },
              ),
            },
      ),
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ fontSize: "1.1rem" }}>C — Swipeable meal stack, totals-first</h2>
      <p className="muted">
        Same multi-item bundle as A, but the primary view is a horizontal card stack with the meal&apos;s totals up
        front; per-item detail is a tap-to-expand, edited with quantity steppers instead of raw number fields.
      </p>

      <div style={{ display: "flex", gap: "0.75rem", overflowX: "auto", paddingBottom: "0.5rem" }}>
        {templates.map((t) => {
          const totals = sumValues(t.items);
          return (
            <div
              key={t.id}
              style={{
                minWidth: "13rem",
                border: "1px solid currentColor",
                borderRadius: "0.75rem",
                padding: "0.75rem",
                flexShrink: 0,
              }}
            >
              <strong>{t.name}</strong>
              <div style={{ fontSize: "1.4rem", margin: "0.3rem 0" }}>{totals.calories} cal</div>
              <div className="muted" style={{ fontSize: "0.7rem" }}>
                P {totals.protein_g}g · C {totals.carbs_g}g · F {totals.fat_g}g
              </div>
              <div style={{ display: "flex", gap: "0.4rem", marginTop: "0.5rem" }}>
                <button type="button" onClick={() => logTemplate(t)}>
                  Log whole meal
                </button>
                <button type="button" onClick={() => setOpenId(openId === t.id ? null : t.id)}>
                  {openId === t.id ? "Hide items" : "Items"}
                </button>
              </div>
              {openId === t.id && (
                <ul style={{ marginTop: "0.5rem", fontSize: "0.75rem", display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  {t.items.map((i) => (
                    <li key={i.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span>
                        {i.name} <span className="muted">({i.values.calories} cal)</span>
                      </span>
                      <span>
                        <button type="button" onClick={() => bumpQty(t, i.id, -0.1)} style={{ padding: "0.1rem 0.4rem" }}>
                          −
                        </button>
                        <button type="button" onClick={() => bumpQty(t, i.id, 0.1)} style={{ padding: "0.1rem 0.4rem" }}>
                          +
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>

      <strong>Logged</strong>
      {loggedGroups.map((g) => (
        <div key={g.id} style={{ border: "1px dashed currentColor", borderRadius: "0.5rem", padding: "0.6rem" }}>
          <div>
            {g.loggedAt}: <strong>{g.name}</strong>{" "}
            <span className="muted">
              ({sumValues(g.items).calories} cal · P {sumValues(g.items).protein_g}g · C{" "}
              {sumValues(g.items).carbs_g}g · F {sumValues(g.items).fat_g}g)
            </span>
          </div>
          <ul className="muted" style={{ marginTop: "0.4rem" }}>
            {g.items.map((i) => (
              <li key={i.id}>
                {i.name} — {i.values.calories} cal
              </li>
            ))}
          </ul>
        </div>
      ))}

      <StatePanel label="Variant C state" data={{ templates, loggedGroups }} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Switcher
// ---------------------------------------------------------------------------

const VARIANTS = [
  { key: "A", name: "Whole-meal bundle", Component: VariantA },
  { key: "B", name: "Single-item favorites", Component: VariantB },
  { key: "C", name: "Swipeable stack, totals-first", Component: VariantC },
] as const;

function PrototypeSwitcher({ current, onChange }: { current: string; onChange: (key: string) => void }) {
  const idx = VARIANTS.findIndex((v) => v.key === current);
  const active = VARIANTS[idx] ?? VARIANTS[0];

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement | null)?.isContentEditable) return;
      if (e.key === "ArrowLeft") onChange((VARIANTS[(idx - 1 + VARIANTS.length) % VARIANTS.length] ?? VARIANTS[0]).key);
      if (e.key === "ArrowRight") onChange((VARIANTS[(idx + 1) % VARIANTS.length] ?? VARIANTS[0]).key);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [idx, onChange]);

  return (
    <div
      style={{
        position: "fixed",
        bottom: "1rem",
        left: "50%",
        transform: "translateX(-50%)",
        background: "#222",
        color: "#fff",
        borderRadius: "999px",
        padding: "0.4rem 0.6rem",
        display: "flex",
        alignItems: "center",
        gap: "0.6rem",
        boxShadow: "0 2px 12px rgba(0,0,0,0.35)",
        fontSize: "0.8rem",
        zIndex: 1000,
      }}
    >
      <button
        type="button"
        onClick={() => onChange((VARIANTS[(idx - 1 + VARIANTS.length) % VARIANTS.length] ?? VARIANTS[0]).key)}
        style={{ color: "#fff", border: "none" }}
      >
        ←
      </button>
      <span>
        {active.key} — {active.name}
      </span>
      <button
        type="button"
        onClick={() => onChange((VARIANTS[(idx + 1) % VARIANTS.length] ?? VARIANTS[0]).key)}
        style={{ color: "#fff", border: "none" }}
      >
        →
      </button>
    </div>
  );
}

export function PrototypeMealTemplate() {
  const [variant, setVariant] = useState(() => new URLSearchParams(window.location.search).get("variant") ?? "A");

  function change(key: string) {
    setVariant(key);
    const url = new URL(window.location.href);
    url.searchParams.set("variant", key);
    window.history.replaceState(null, "", url);
  }

  const Active = VARIANTS.find((v) => v.key === variant)?.Component ?? VariantA;

  return (
    <main>
      <header>
        <h1>Meal template prototype</h1>
        <p className="muted">/prototype/meal-template — throwaway, ticket #4 on the map (#1). No persistence.</p>
      </header>
      <Active />
      {!import.meta.env.PROD && <PrototypeSwitcher current={variant} onChange={change} />}
    </main>
  );
}
