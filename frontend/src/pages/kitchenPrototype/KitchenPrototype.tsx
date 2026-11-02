/**
 * PROTOTYPE - throwaway. Never merge to main.
 *
 * Question: should "Needs eating" stay a list you maintain, or become a view derived
 * from the Kitchen? Four variants of the Plan tab, switchable via `?variant=`:
 *   0 - Today's tray, unchanged, holding a full Kitchen (the baseline)
 *   A - Derived: leftovers plus anything close to its Estimated Expiry
 *   B - Maintained: nothing needs eating until someone flags it
 *   C - Dropped: no such concept; the Kitchen sorts by date, the picker stays short
 *
 * Round 2, after feedback that A's separate sections were noisy. Food types stay, every
 * food shows a good-by date, and whatever goes off first rises to the top:
 *   D - One list under food type headings, soonest first inside each
 *   E - The same, as B's compact chips with the date inside each chip
 *   F - One list with a toggle between food types and soonest first
 *
 * Round 3, after E won but the user wanted B's starred section back:
 *   G - E's chips, with a starred "To use up" area on top. Tap a chip to star it.
 *
 * Round 4, after "it's the look of the screen". Same chips and behavior as G, three
 * visual treatments:
 *   H - Tidy grid: equal-width chips on one surface
 *   I - Side labels: quiet white chips with a color stripe, food types in a left column
 *   J - App hero: To use up in a band like the app's heroes, color only as a dot
 *
 * Round 5, after J won:
 *   K - J with the band in the site's own hero colors. Chips lose their × and tap-to-star;
 *       tapping a chip opens a box to star, move, change the date or remove.
 * Only K and J are on the switcher. The rest still open via `?variant=`.
 *
 * Fake data, in memory only. Reloading resets everything. Mounted before auth, in dev
 * builds only (see main.tsx), so it needs no backend: `npm run dev`, then
 * /prototype/kitchen.
 */
import { useEffect, useMemo, useState } from "react";

import { NavBar } from "../../components/NavBar";
import { Card } from "../../components/ui";
import "./kitchenPrototype.css";

// ---------------------------------------------------------------------------- data

type Place = "fridge" | "freezer" | "pantry";

type Food = {
  id: string;
  name: string;
  type: string;
  place: Place;
  qty?: string;
  /** Days from today until the Estimated Expiry. Null means no estimate. */
  days: number | null;
  /** Purchases held behind this one row (Q14). */
  purchases?: number;
  kcal?: number;
  protein?: number;
  flagged?: boolean;
};

const TYPES = ["Leftovers", "Produce", "Dairy & eggs", "Meat & fish", "Bakery", "Pantry", "Frozen", "Other"];

const SEED: Food[] = [
  { id: "l1", name: "Chicken curry", type: "Leftovers", place: "fridge", qty: "half", days: 2, kcal: 390, protein: 24 },
  { id: "l2", name: "Turkey chili", type: "Leftovers", place: "fridge", qty: "about 3 servings", days: 3, kcal: 410, protein: 36, flagged: true },
  { id: "l3", name: "Fried rice", type: "Leftovers", place: "fridge", qty: "a little", days: -1, kcal: 260, protein: 9 },
  { id: "p1", name: "Avocados", type: "Produce", place: "fridge", qty: "2", days: 1 },
  { id: "p2", name: "Spinach", type: "Produce", place: "fridge", qty: "1 bag", days: 2, flagged: true },
  { id: "p3", name: "Bananas", type: "Produce", place: "pantry", qty: "1 bunch", days: 3 },
  { id: "p4", name: "Cilantro", type: "Produce", place: "fridge", qty: "1 bunch", days: -3 },
  { id: "p5", name: "Bell peppers", type: "Produce", place: "fridge", qty: "3", days: 6 },
  { id: "p6", name: "Lemons", type: "Produce", place: "fridge", qty: "4", days: 13 },
  { id: "p7", name: "Carrots", type: "Produce", place: "fridge", qty: "1 lb", days: 14 },
  { id: "p8", name: "Yellow onions", type: "Produce", place: "pantry", qty: "3 lb", days: 30 },
  { id: "p9", name: "Garlic", type: "Produce", place: "pantry", qty: "1 head", days: 45 },
  { id: "d1", name: "Whole milk", type: "Dairy & eggs", place: "fridge", qty: "1 gal", days: 5, purchases: 2 },
  { id: "d2", name: "Greek yogurt", type: "Dairy & eggs", place: "fridge", qty: "32 oz", days: 9 },
  { id: "d3", name: "Cheddar", type: "Dairy & eggs", place: "fridge", qty: "8 oz", days: 21 },
  { id: "d4", name: "Eggs", type: "Dairy & eggs", place: "fridge", qty: "18", days: 24 },
  { id: "d5", name: "Butter", type: "Dairy & eggs", place: "fridge", qty: "1 lb", days: 40 },
  { id: "m1", name: "Chicken thighs", type: "Meat & fish", place: "fridge", qty: "2 lb", days: 1 },
  { id: "m2", name: "Salmon fillets", type: "Meat & fish", place: "freezer", qty: "4", days: 60 },
  { id: "m3", name: "Ground turkey", type: "Meat & fish", place: "freezer", qty: "1 lb", days: 90 },
  { id: "b1", name: "Sourdough", type: "Bakery", place: "pantry", qty: "1 loaf", days: 2 },
  { id: "b2", name: "Tortillas", type: "Bakery", place: "fridge", qty: "1 pack", days: 12 },
  { id: "t1", name: "Peanut butter", type: "Pantry", place: "pantry", qty: "1 jar", days: 120 },
  { id: "t2", name: "Oats", type: "Pantry", place: "pantry", qty: "42 oz", days: 200 },
  { id: "t3", name: "Olive oil", type: "Pantry", place: "pantry", qty: "1 bottle", days: 280 },
  { id: "t4", name: "Pasta", type: "Pantry", place: "pantry", qty: "2 boxes", days: 300 },
  { id: "t5", name: "Rice", type: "Pantry", place: "pantry", qty: "5 lb", days: 365 },
  { id: "t6", name: "Black beans", type: "Pantry", place: "pantry", qty: "3 cans", days: 400 },
  { id: "f1", name: "Frozen peas", type: "Frozen", place: "freezer", qty: "1 bag", days: 180 },
  { id: "o1", name: "Homemade chili crisp", type: "Other", place: "fridge", qty: "1 jar", days: null },
];

const SAVED_MEALS = [
  "Chicken rice bowl",
  "Salmon and greens",
  "Overnight oats",
  "Turkey taco bowl",
  "Protein smoothie",
  "Egg scramble",
  "Pasta with meat sauce",
  "Greek yogurt parfait",
];

const SLOTS = ["breakfast", "lunch", "dinner", "snack"];
const USE_SOON_DAYS = 3;

// ------------------------------------------------------------------------- helpers

const dateIn = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
};

const isLeftover = (f: Food) => f.type === "Leftovers";
const isCheck = (f: Food) => f.days !== null && f.days < 0;
const isSoon = (f: Food) => f.days !== null && f.days >= 0 && f.days <= USE_SOON_DAYS;

/** What a row says about its date. Worded as an estimate, never a safety claim. */
function dateLabel(f: Food): string {
  if (f.days === null) return "no estimate";
  if (f.days < 0) return "probably gone, check";
  if (f.days === 0) return "good until today";
  if (f.days === 1) return "good until tomorrow";
  return `good until ${dateIn(f.days)}`;
}

const byDate = (a: Food, b: Food) => (a.days ?? 99999) - (b.days ?? 99999);
const matches = (f: Food, q: string) => f.name.toLowerCase().includes(q.trim().toLowerCase());

// ------------------------------------------------------------------------ the page

const VARIANTS = [
  { key: "K", name: "Site colors, tap a chip for options" },
  { key: "J", name: "Previous look, for comparison" },
];

type View = "week" | "kitchen";
type Planned = { name: string; macros?: string; leftoverId?: string; logged?: boolean };

const readParam = (key: string) => new URLSearchParams(window.location.search).get(key);

export function KitchenPrototype() {
  const [variant, setVariantState] = useState(() => readParam("variant") ?? "K");
  const [view, setViewState] = useState<View>(() => (readParam("view") === "week" ? "week" : "kitchen"));
  const [foods, setFoods] = useState(SEED);
  const [plan, setPlan] = useState<Record<string, Planned>>({
    lunch: { name: "Chicken rice bowl", macros: "610 kcal · 48 g" },
  });
  const [openSlot, setOpenSlot] = useState<string | null>(null);
  const [lastRemoved, setLastRemoved] = useState<Food | null>(null);

  const syncUrl = (v: string, w: View) =>
    window.history.replaceState(null, "", `?variant=${v}&view=${w}`);
  const setVariant = (v: string) => {
    setVariantState(v);
    syncUrl(v, view);
  };
  const setView = (w: View) => {
    setViewState(w);
    setOpenSlot(null);
    syncUrl(variant, w);
  };

  const remove = (id: string) => {
    setLastRemoved(foods.find((f) => f.id === id) ?? null);
    setFoods(foods.filter((f) => f.id !== id));
  };
  const toggleFlag = (id: string) =>
    setFoods(foods.map((f) => (f.id === id ? { ...f, flagged: !f.flagged } : f)));

  const update = (id: string, patch: Partial<Food>) =>
    setFoods(foods.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const add = (food: Food) => setFoods([...foods, food]);

  const ctx: Ctx = { foods, remove, toggleFlag, update, add };
  const Screen = { "0": KitchenBaseline, A: KitchenDerived, B: KitchenMaintained, C: KitchenSorted, D: KitchenTypeList, E: KitchenTypeChips, F: KitchenToggle, G: KitchenStarredChips, H: LookH, I: LookI, J: LookJ, K: KitchenWithBox }[variant] ?? KitchenWithBox;
  const Picker = { "0": PickerBaseline, A: PickerDerived, B: PickerMaintained, C: PickerSorted, D: PickerDerived, E: PickerDerived, F: PickerSorted, G: PickerStarred, H: PickerStarred, I: PickerStarred, J: PickerStarred, K: PickerStarred }[variant] ?? PickerStarred;

  return (
    <>
      <header className="app-bar">
        <div className="app-bar-inner">
          <a className="app-brand" href="/prototype/kitchen">
            Swolemates
          </a>
          <NavBar />
        </div>
      </header>

      <main className="app-main">
        <div className="page-body kp-page">
          <div className="kp-switch" role="tablist" aria-label="Plan view">
            {(["week", "kitchen"] as View[]).map((w) => (
              <button key={w} type="button" role="tab" aria-selected={view === w} onClick={() => setView(w)}>
                {w === "week" ? "Week" : "Kitchen"}
              </button>
            ))}
          </div>

          {view === "kitchen" ? (
            <Screen {...ctx} />
          ) : (
            <Card title="Today's meals" meta={<span className="card-meta">tap a slot to open the picker</span>}>
              <div className="kp-slots">
                {SLOTS.map((slot) => {
                  const meal = plan[slot];
                  return (
                    <button
                      key={slot}
                      type="button"
                      className={
                        (meal ? `meal-slot meal-slot--wide meal-slot--${slot}` : "meal-slot meal-slot--wide meal-slot--empty") +
                        (openSlot === slot ? " is-open" : "")
                      }
                      onClick={() => setOpenSlot(openSlot === slot ? null : slot)}
                    >
                      <span className="meal-slot-kind">{slot}</span>
                      <span className="meal-slot-name">{meal ? meal.name : "+ add"}</span>
                      {meal?.macros && <span className="meal-slot-macros">{meal.macros}</span>}
                      {meal?.logged && <span className="meal-slot-logged">logged</span>}
                    </button>
                  );
                })}
              </div>

              {openSlot && (
                <div className="meal-picker">
                  <div className="meal-picker-head">
                    <strong>Today · {openSlot}</strong>
                    <button type="button" className="meal-picker-close" onClick={() => setOpenSlot(null)}>
                      Close
                    </button>
                  </div>

                  {plan[openSlot] && !plan[openSlot].logged && (
                    <div className="meal-picker-actions">
                      <button
                        type="button"
                        onClick={() => {
                          // Q15: logging a planned Leftover removes it from the Kitchen.
                          const planned = plan[openSlot];
                          if (planned?.leftoverId) remove(planned.leftoverId);
                          setPlan({ ...plan, [openSlot]: { ...planned!, logged: true } });
                          setOpenSlot(null);
                        }}
                      >
                        Log it
                      </button>
                    </div>
                  )}

                  <Picker
                    {...ctx}
                    onPick={(meal) => {
                      setPlan({ ...plan, [openSlot]: meal });
                      setOpenSlot(null);
                    }}
                    goToKitchen={() => setView("kitchen")}
                  />
                </div>
              )}
            </Card>
          )}
        </div>
      </main>

      <PrototypeSwitcher
        current={variant}
        onChange={setVariant}
        state={`${foods.length} foods · ${foods.filter(isSoon).length} soon · ${foods.filter(isCheck).length} check · ${foods.filter((f) => f.flagged).length} starred${lastRemoved ? ` · removed ${lastRemoved.name}` : ""}`}
        undo={
          lastRemoved
            ? () => {
                setFoods([...foods, lastRemoved]);
                setLastRemoved(null);
              }
            : undefined
        }
      />
    </>
  );
}

type Ctx = {
  foods: Food[];
  remove: (id: string) => void;
  toggleFlag: (id: string) => void;
  update: (id: string, patch: Partial<Food>) => void;
  add: (food: Food) => void;
};
type PickerProps = Ctx & { onPick: (meal: Planned) => void; goToKitchen: () => void };

// --------------------------------------------------------------------- shared bits

function Search({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <input
      type="search"
      className="kp-search"
      placeholder="Do we have…"
      aria-label="Search the Kitchen"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function FoodRow({ food, onRemove, extra }: { food: Food; onRemove: () => void; extra?: React.ReactNode }) {
  return (
    <li className={"kp-row" + (isCheck(food) ? " is-check" : "")}>
      <span className="kp-row-main">
        <span className="kp-row-name">{food.name}</span>
        <span className="kp-row-detail">
          {[food.qty, food.place, dateLabel(food)].filter(Boolean).join(" · ")}
        </span>
      </span>
      {extra}
      <button type="button" className="kp-remove" aria-label={`Remove ${food.name}`} onClick={onRemove}>
        ×
      </button>
    </li>
  );
}

function LeftoverOption({ food, onPick }: { food: Food; onPick: (m: Planned) => void }) {
  return (
    <li className="is-leftover">
      <button
        type="button"
        onClick={() =>
          onPick({ name: food.name, macros: `${food.kcal} kcal · ${food.protein} g`, leftoverId: food.id })
        }
      >
        <span className="mo-name">{food.name}</span>
        <span className="mo-macros">
          {food.kcal} kcal · {isCheck(food) ? "check first" : dateLabel(food)}
        </span>
      </button>
    </li>
  );
}

function SavedMeals({ onPick }: { onPick: (m: Planned) => void }) {
  return (
    <>
      <p className="meal-picker-group">Saved meals</p>
      <ul className="meal-options">
        {SAVED_MEALS.map((name) => (
          <li key={name}>
            <button type="button" onClick={() => onPick({ name, macros: "550 kcal · 40 g" })}>
              <span className="mo-name">{name}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}

function SomethingElse({ onPick }: { onPick: (m: Planned) => void }) {
  const [quick, setQuick] = useState("");
  return (
    <>
      <p className="meal-picker-group">Something else</p>
      <div className="meal-quick">
        <input
          type="text"
          value={quick}
          placeholder="e.g. dinner at Mum's"
          aria-label="Name this meal"
          onChange={(e) => setQuick(e.target.value)}
        />
        <button type="button" disabled={!quick.trim()} onClick={() => onPick({ name: quick.trim() })}>
          Add
        </button>
      </div>
    </>
  );
}

// ------------------------------------------------- 0: today's tray, full Kitchen

function KitchenBaseline({ foods, remove }: Ctx) {
  return (
    <Card title="Needs eating" meta={<span className="card-meta">today's tray, unchanged</span>}>
      <ul className="kitchen-list">
        {foods.map((item) => (
          <li key={item.id} className={isLeftover(item) ? "is-leftover" : undefined}>
            <span className="k-name">
              {item.name}
              <span className="k-detail">
                {isLeftover(item) ? `${item.kcal} kcal · ${item.protein} g` : "no meal uses it yet"}
              </span>
            </span>
            <button type="button" className="k-remove" aria-label={`Remove ${item.name}`} onClick={() => remove(item.id)}>
              ×
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function PickerBaseline({ foods, onPick }: PickerProps) {
  return (
    <>
      <p className="meal-picker-group">Needs eating</p>
      <ul className="meal-options">
        {foods.filter(isLeftover).map((f) => (
          <LeftoverOption key={f.id} food={f} onPick={onPick} />
        ))}
      </ul>
      {foods
        .filter((f) => !isLeftover(f))
        .map((f) => (
          <div key={f.id}>
            <p className="meal-picker-group">
              To use up <b>{f.name.toLowerCase()}</b>
            </p>
            <ul className="meal-options">
              <li className="muted meal-options-empty">No saved meal uses it yet.</li>
            </ul>
          </div>
        ))}
      <SavedMeals onPick={onPick} />
      <SomethingElse onPick={onPick} />
    </>
  );
}

// ------------------------------------------------------------- A: derived view

function KitchenDerived({ foods, remove }: Ctx) {
  const [q, setQ] = useState("");
  const searching = q.trim() !== "";
  const soon = foods.filter((f) => isSoon(f) || (isLeftover(f) && !isCheck(f))).sort(byDate);
  const check = foods.filter(isCheck);
  const soonIds = new Set([...soon, ...check].map((f) => f.id));

  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      {!searching && (
        <>
          <Card title="Use soon" meta={<span className="card-meta">worked out for you</span>}>
            <ul className="kp-rows">
              {soon.map((f) => (
                <FoodRow key={f.id} food={f} onRemove={() => remove(f.id)} />
              ))}
            </ul>
          </Card>
          {check.length > 0 && (
            <Card title="Probably gone" meta={<span className="card-meta">clears itself after a week</span>}>
              <ul className="kp-rows">
                {check.map((f) => (
                  <FoodRow key={f.id} food={f} onRemove={() => remove(f.id)} />
                ))}
              </ul>
            </Card>
          )}
        </>
      )}
      {TYPES.map((type) => {
        const rows = foods
          .filter((f) => f.type === type)
          .filter((f) => (searching ? matches(f, q) : !soonIds.has(f.id)));
        if (rows.length === 0) return null;
        return (
          <Card key={type} title={type} meta={<span className="card-meta">{rows.length}</span>}>
            <ul className="kp-rows">
              {rows.map((f) => (
                <FoodRow key={f.id} food={f} onRemove={() => remove(f.id)} />
              ))}
            </ul>
          </Card>
        );
      })}
    </div>
  );
}

function PickerDerived({ foods, onPick }: PickerProps) {
  const leftovers = foods.filter(isLeftover).sort(byDate);
  const soon = foods.filter((f) => isSoon(f) && !isLeftover(f)).sort(byDate);
  return (
    <>
      {leftovers.length > 0 && (
        <>
          <p className="meal-picker-group">Leftovers</p>
          <ul className="meal-options">
            {leftovers.map((f) => (
              <LeftoverOption key={f.id} food={f} onPick={onPick} />
            ))}
          </ul>
        </>
      )}
      {soon.length > 0 && (
        <>
          <p className="meal-picker-group">Worth using soon</p>
          <p className="kp-hint">{soon.map((f) => f.name).join(", ")}</p>
        </>
      )}
      <SavedMeals onPick={onPick} />
      <SomethingElse onPick={onPick} />
    </>
  );
}

// ---------------------------------------------------------- B: maintained list

function KitchenMaintained({ foods, remove, toggleFlag }: Ctx) {
  const [q, setQ] = useState("");
  const searching = q.trim() !== "";
  const flagged = foods.filter((f) => f.flagged);
  const shelf = foods.filter((f) => (searching ? matches(f, q) : !f.flagged));

  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      {!searching && (
        <Card title="Needs eating" meta={<span className="card-meta">only what you flagged</span>}>
          <ul className="kp-rows">
            {flagged.map((f) => (
              <FoodRow
                key={f.id}
                food={f}
                onRemove={() => remove(f.id)}
                extra={
                  <button type="button" className="kp-flag is-on" aria-label={`Unflag ${f.name}`} onClick={() => toggleFlag(f.id)}>
                    ★
                  </button>
                }
              />
            ))}
            {flagged.length === 0 && <li className="muted">Nothing flagged. Tap a star below.</li>}
          </ul>
        </Card>
      )}
      <Card title="Everything else" meta={<span className="card-meta">tap to flag · × to remove</span>}>
        {TYPES.map((type) => {
          const rows = shelf.filter((f) => f.type === type);
          if (rows.length === 0) return null;
          return (
            <div key={type} className="kp-chip-group">
              <p className="meal-picker-group">{type}</p>
              <ul className="kp-chips">
                {rows.map((f) => (
                  <li key={f.id} className={isCheck(f) ? "is-check" : undefined}>
                    <button type="button" className="kp-chip-main" title={dateLabel(f)} onClick={() => toggleFlag(f.id)}>
                      {f.flagged ? "★ " : ""}
                      {f.name}
                    </button>
                    <button type="button" className="kp-chip-x" aria-label={`Remove ${f.name}`} onClick={() => remove(f.id)}>
                      ×
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </Card>
    </div>
  );
}

function PickerMaintained({ foods, onPick }: PickerProps) {
  const flagged = foods.filter((f) => f.flagged);
  return (
    <>
      {flagged.length > 0 && (
        <>
          <p className="meal-picker-group">Needs eating</p>
          <ul className="meal-options">
            {flagged.filter(isLeftover).map((f) => (
              <LeftoverOption key={f.id} food={f} onPick={onPick} />
            ))}
          </ul>
          {flagged.some((f) => !isLeftover(f)) && (
            <p className="kp-hint">
              {flagged
                .filter((f) => !isLeftover(f))
                .map((f) => f.name)
                .join(", ")}
            </p>
          )}
        </>
      )}
      <SavedMeals onPick={onPick} />
      <SomethingElse onPick={onPick} />
    </>
  );
}

// --------------------------------------------------------- C: concept dropped

function KitchenSorted({ foods, remove }: Ctx) {
  const [q, setQ] = useState("");
  const [place, setPlace] = useState<Place | "all">("all");
  const rows = foods
    .filter((f) => place === "all" || f.place === place)
    .filter((f) => matches(f, q))
    .sort(byDate);

  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      <div className="kp-pills">
        {(["all", "fridge", "freezer", "pantry"] as const).map((p) => (
          <button key={p} type="button" aria-pressed={place === p} onClick={() => setPlace(p)}>
            {p}
          </button>
        ))}
      </div>
      <Card title="Kitchen" meta={<span className="card-meta">soonest first · {rows.length}</span>}>
        <ul className="kp-rows">
          {rows.map((f) => (
            <FoodRow key={f.id} food={f} onRemove={() => remove(f.id)} />
          ))}
        </ul>
      </Card>
    </div>
  );
}

function PickerSorted({ foods, onPick, goToKitchen }: PickerProps) {
  const leftovers = foods.filter((f) => isLeftover(f) && !isCheck(f)).sort(byDate);
  const soonCount = foods.filter((f) => isSoon(f) && !isLeftover(f)).length;
  return (
    <>
      {leftovers.length > 0 && (
        <>
          <p className="meal-picker-group">Leftovers</p>
          <ul className="meal-options">
            {leftovers.map((f) => (
              <LeftoverOption key={f.id} food={f} onPick={onPick} />
            ))}
          </ul>
        </>
      )}
      <SavedMeals onPick={onPick} />
      <SomethingElse onPick={onPick} />
      {soonCount > 0 && (
        <button type="button" className="kp-link" onClick={goToKitchen}>
          {soonCount} groceries going off soon: see the Kitchen
        </button>
      )}
    </>
  );
}

// ------------------------------------------------ round 2: shared by D, E and F

/** The date on its own, short enough to sit on one line. */
function goodBy(f: Food): string {
  if (f.days === null) return "no date";
  if (f.days < 0) return "probably gone?";
  if (f.days === 0) return "good by today";
  if (f.days === 1) return "good by tomorrow";
  return `good by ${dateIn(f.days)}`;
}

const urgency = (f: Food) => (isCheck(f) ? " is-check" : isSoon(f) ? " is-soon" : "");

/** Food types with something going off first rise to the top, soonest first inside. */
function typeGroups(foods: Food[]): { type: string; rows: Food[] }[] {
  return TYPES.map((type) => ({ type, rows: foods.filter((f) => f.type === type).sort(byDate) }))
    .filter((g) => g.rows.length > 0)
    .sort((a, b) => byDate(a.rows[0]!, b.rows[0]!));
}

function DateRow({ food, onRemove, showType }: { food: Food; onRemove: () => void; showType?: boolean }) {
  return (
    <li className={"kp-line" + urgency(food)}>
      <span className="kp-line-name">
        {food.name}
        <span className="kp-line-qty">{showType ? food.type : food.qty}</span>
      </span>
      <span className="kp-line-date">{goodBy(food)}</span>
      <button type="button" className="kp-remove" aria-label={`Remove ${food.name}`} onClick={onRemove}>
        ×
      </button>
    </li>
  );
}

function TypeList({ foods, remove }: { foods: Food[]; remove: (id: string) => void }) {
  return (
    <>
      {typeGroups(foods).map(({ type, rows }) => (
        <div key={type}>
          <p className="kp-type">{type}</p>
          <ul className="kp-rows">
            {rows.map((f) => (
              <DateRow key={f.id} food={f} onRemove={() => remove(f.id)} />
            ))}
          </ul>
        </div>
      ))}
    </>
  );
}

// ----------------------------------------------------- D: food types, one list

function KitchenTypeList({ foods, remove }: Ctx) {
  const [q, setQ] = useState("");
  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      <Card>
        <TypeList foods={foods.filter((f) => matches(f, q))} remove={remove} />
      </Card>
    </div>
  );
}

// ------------------------------------------- E: food types, chips with dates

function KitchenTypeChips({ foods, remove }: Ctx) {
  const [q, setQ] = useState("");
  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      <Card>
        {typeGroups(foods.filter((f) => matches(f, q))).map(({ type, rows }) => (
          <div key={type}>
            <p className="kp-type">{type}</p>
            <ul className="kp-datechips">
              {rows.map((f) => (
                <li key={f.id} className={urgency(f).trim()}>
                  <span className="kp-datechip-main">
                    <b>{f.name}</b>
                    <small>{goodBy(f).replace("good by ", "")}</small>
                  </span>
                  <button type="button" className="kp-chip-x" aria-label={`Remove ${f.name}`} onClick={() => remove(f.id)}>
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </Card>
    </div>
  );
}

// ------------------------------------------------ F: one list, two sort orders

function KitchenToggle({ foods, remove }: Ctx) {
  const [q, setQ] = useState("");
  const [order, setOrder] = useState<"type" | "soonest">("type");
  const rows = foods.filter((f) => matches(f, q));
  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      <div className="kp-pills">
        <button type="button" aria-pressed={order === "type"} onClick={() => setOrder("type")}>
          By food type
        </button>
        <button type="button" aria-pressed={order === "soonest"} onClick={() => setOrder("soonest")}>
          Soonest first
        </button>
      </div>
      <Card>
        {order === "type" ? (
          <TypeList foods={rows} remove={remove} />
        ) : (
          <ul className="kp-rows">
            {rows.sort(byDate).map((f) => (
              <DateRow key={f.id} food={f} showType onRemove={() => remove(f.id)} />
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

// ------------------------------------------- G: chips + starred "To use up"

function StarChip({ food, toggleFlag, remove }: { food: Food; toggleFlag: Ctx["toggleFlag"]; remove: Ctx["remove"] }) {
  // Asks in place rather than in a dialog, so the rest of the list stays in view.
  const [confirming, setConfirming] = useState(false);

  if (confirming) {
    return (
      <li className="kp-confirm">
        <span>Remove {food.name}?</span>
        <button type="button" className="kp-confirm-yes" onClick={() => remove(food.id)}>
          Remove
        </button>
        <button type="button" className="kp-confirm-no" onClick={() => setConfirming(false)}>
          Keep
        </button>
      </li>
    );
  }

  return (
    <li className={urgency(food).trim()}>
      <button
        type="button"
        className="kp-datechip-main kp-datechip-tap"
        aria-pressed={Boolean(food.flagged)}
        aria-label={`${food.flagged ? "Unstar" : "Star"} ${food.name}`}
        onClick={() => toggleFlag(food.id)}
      >
        <b>
          {food.flagged && <span className="kp-star">★ </span>}
          {food.name}
        </b>
        <small>{goodBy(food).replace("good by ", "")}</small>
      </button>
      <button type="button" className="kp-chip-x" aria-label={`Remove ${food.name}`} onClick={() => setConfirming(true)}>
        ×
      </button>
    </li>
  );
}

function KitchenStarredChips({ foods, remove, toggleFlag }: Ctx) {
  const [q, setQ] = useState("");
  const searching = q.trim() !== "";
  const starred = foods.filter((f) => f.flagged).sort(byDate);
  const rest = foods.filter((f) => (searching ? matches(f, q) : !f.flagged));

  return (
    <div className="kp-stack">
      <Search value={q} onChange={setQ} />
      <ul className="kp-legend" aria-label="What the chip colors mean">
        <li>
          <i />
          Good for now
        </li>
        <li className="is-soon">
          <i />
          Good by within {USE_SOON_DAYS} days
        </li>
        <li className="is-check">
          <i />
          Past its date, probably gone
        </li>
      </ul>
      {!searching && (
        <Card title="To use up" meta={<span className="card-meta">tap a food to star it</span>}>
          {starred.length > 0 ? (
            <ul className="kp-datechips">
              {starred.map((f) => (
                <StarChip key={f.id} food={f} toggleFlag={toggleFlag} remove={remove} />
              ))}
            </ul>
          ) : (
            <p className="card-note">Nothing starred. Tap a food below to add it here.</p>
          )}
        </Card>
      )}
      <Card>
        {typeGroups(rest).map(({ type, rows }) => (
          <div key={type}>
            <p className="kp-type">{type}</p>
            <ul className="kp-datechips">
              {rows.map((f) => (
                <StarChip key={f.id} food={f} toggleFlag={toggleFlag} remove={remove} />
              ))}
            </ul>
          </div>
        ))}
      </Card>
    </div>
  );
}

/** Every Leftover stays plannable; a star only moves it up. Starred groceries can't be
 *  planned directly, so they're a reminder line. */
function PickerStarred({ foods, onPick }: PickerProps) {
  const leftovers = foods
    .filter(isLeftover)
    .sort((a, b) => Number(Boolean(b.flagged)) - Number(Boolean(a.flagged)) || byDate(a, b));
  const starred = foods.filter((f) => f.flagged && !isLeftover(f)).sort(byDate);
  return (
    <>
      {leftovers.length > 0 && (
        <>
          <p className="meal-picker-group">Leftovers</p>
          <ul className="meal-options">
            {leftovers.map((f) => (
              <LeftoverOption key={f.id} food={f} onPick={onPick} />
            ))}
          </ul>
        </>
      )}
      {starred.length > 0 && (
        <>
          <p className="meal-picker-group">To use up</p>
          <p className="kp-hint">{starred.map((f) => f.name).join(", ")}</p>
        </>
      )}
      <SavedMeals onPick={onPick} />
      <SomethingElse onPick={onPick} />
    </>
  );
}

// ------------------------------------------------- H, I, J: three looks for G

function Legend() {
  return (
    <ul className="kp-legend" aria-label="What the chip colors mean">
      <li>
        <i />
        Good for now
      </li>
      <li className="is-soon">
        <i />
        Good by within {USE_SOON_DAYS} days
      </li>
      <li className="is-check">
        <i />
        Past its date, probably gone
      </li>
    </ul>
  );
}

function KitchenLook({ look, foods, remove, toggleFlag }: Ctx & { look: "H" | "I" | "J" }) {
  const [q, setQ] = useState("");
  const searching = q.trim() !== "";
  const starred = foods.filter((f) => f.flagged).sort(byDate);
  const rest = foods.filter((f) => (searching ? matches(f, q) : !f.flagged));

  const chips = (rows: Food[]) => (
    <ul className="kp-datechips">
      {rows.map((f) => (
        <StarChip key={f.id} food={f} toggleFlag={toggleFlag} remove={remove} />
      ))}
    </ul>
  );
  const toUseUp = !searching && (
    <div className="kp-group kp-group--star">
      <p className="kp-type">★ To use up</p>
      {starred.length > 0 ? chips(starred) : <p className="card-note">Tap a food to star it.</p>}
    </div>
  );
  const groups = typeGroups(rest).map(({ type, rows }) => (
    <div key={type} className="kp-group">
      <p className="kp-type">{type}</p>
      {chips(rows)}
    </div>
  ));

  if (look === "J") {
    return (
      <div className="kp-look kp-look--J">
        <div className="kp-hero">
          <h2>Kitchen</h2>
          <Search value={q} onChange={setQ} />
          {toUseUp}
          <Legend />
        </div>
        {groups}
      </div>
    );
  }

  return (
    <div className={`kp-stack kp-look kp-look--${look}`}>
      <Search value={q} onChange={setQ} />
      <Card>
        {toUseUp}
        {groups}
        <Legend />
      </Card>
    </div>
  );
}

const LookH = (ctx: Ctx) => <KitchenLook look="H" {...ctx} />;
const LookI = (ctx: Ctx) => <KitchenLook look="I" {...ctx} />;
const LookJ = (ctx: Ctx) => <KitchenLook look="J" {...ctx} />;

// ------------------------------------------------ K: tap a chip for its options

/** Stand-ins for the Shelf-Life table: moving a food restarts its estimate. */
const FAKE_SHELF_LIFE: Record<Place, number> = { fridge: 5, freezer: 90, pantry: 30 };

const isoIn = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

const daysUntil = (iso: string) => {
  const today = new Date(`${isoIn(0)}T12:00`);
  return Math.round((new Date(`${iso}T12:00`).getTime() - today.getTime()) / 86400000);
};

function FoodBox({ food, ctx, onClose }: { food: Food; ctx: Ctx; onClose: () => void }) {
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="kp-box-backdrop" onClick={onClose}>
      <div
        className="kp-box"
        role="dialog"
        aria-modal="true"
        aria-label={food.name}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="kp-box-head">
          <div>
            <h3>{food.name}</h3>
            <p>{[food.qty, goodBy(food)].filter(Boolean).join(" · ")}</p>
          </div>
          <button type="button" className="kp-box-close" aria-label="Close" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="kp-box-fields">
          <label className="kp-box-date">
            <span className="kp-box-label">Name</span>
            <input type="text" value={food.name} onChange={(e) => ctx.update(food.id, { name: e.target.value })} />
          </label>
          <label className="kp-box-date">
            <span className="kp-box-label">Quantity</span>
            <input type="text" value={food.qty ?? ""} onChange={(e) => ctx.update(food.id, { qty: e.target.value })} />
          </label>
        </div>

        <button
          type="button"
          className={"kp-box-star" + (food.flagged ? " is-on" : "")}
          aria-pressed={Boolean(food.flagged)}
          onClick={() => ctx.toggleFlag(food.id)}
        >
          {food.flagged ? "★ In To use up. Tap to take it out" : "☆ Add to To use up"}
        </button>

        <p className="kp-box-label">Kept in</p>
        <div className="kp-pills">
          {(["fridge", "freezer", "pantry"] as Place[]).map((place) => (
            <button
              key={place}
              type="button"
              aria-pressed={food.place === place}
              onClick={() =>
                food.place !== place && ctx.update(food.id, { place, days: FAKE_SHELF_LIFE[place] })
              }
            >
              {place}
            </button>
          ))}
        </div>

        <label className="kp-box-date">
          <span className="kp-box-label">Good by</span>
          <input
            type="date"
            value={food.days === null ? "" : isoIn(food.days)}
            onChange={(e) =>
              ctx.update(food.id, { days: e.target.value ? daysUntil(e.target.value) : null })
            }
          />
        </label>

        <button
          type="button"
          className={"kp-box-remove" + (confirming ? " is-armed" : "")}
          onClick={() => {
            if (!confirming) {
              setConfirming(true);
              return;
            }
            ctx.remove(food.id);
            onClose();
          }}
        >
          {confirming ? "Are you sure? Tap again to remove" : "Remove from Kitchen"}
        </button>
      </div>
    </div>
  );
}

/** The same box with empty fields. Only the name is required. */
function AddFoodBox({ ctx, onClose }: { ctx: Ctx; onClose: () => void }) {
  const [name, setName] = useState("");
  const [qty, setQty] = useState("");
  const [type, setType] = useState("Produce");
  const [place, setPlace] = useState<Place>("fridge");
  const days = FAKE_SHELF_LIFE[place];

  return (
    <div className="kp-box-backdrop" onClick={onClose}>
      <div className="kp-box" role="dialog" aria-modal="true" aria-label="Add food" onClick={(e) => e.stopPropagation()}>
        <div className="kp-box-head">
          <div>
            <h3>Add food</h3>
            <p>Probably good by {dateIn(days)}</p>
          </div>
          <button type="button" className="kp-box-close" onClick={onClose}>
            Close
          </button>
        </div>
        <label className="kp-box-date">
          <span className="kp-box-label">Name</span>
          <input type="text" autoFocus value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="kp-box-date">
          <span className="kp-box-label">Quantity (optional)</span>
          <input type="text" placeholder="1 gal" value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <label className="kp-box-date">
          <span className="kp-box-label">Food type</span>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </label>
        <p className="kp-box-label">Kept in</p>
        <div className="kp-pills">
          {(["fridge", "freezer", "pantry"] as Place[]).map((p) => (
            <button key={p} type="button" aria-pressed={place === p} onClick={() => setPlace(p)}>
              {p}
            </button>
          ))}
        </div>
        <button
          type="button"
          className="kp-box-add"
          disabled={!name.trim()}
          onClick={() => {
            ctx.add({ id: String(Date.now()), name: name.trim(), qty: qty.trim() || undefined, type, place, days });
            onClose();
          }}
        >
          Add to Kitchen
        </button>
      </div>
    </div>
  );
}

function KitchenWithBox(ctx: Ctx) {
  const { foods } = ctx;
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const searching = q.trim() !== "";
  const starred = foods.filter((f) => f.flagged).sort(byDate);
  const rest = foods.filter((f) => (searching ? matches(f, q) : !f.flagged));
  const open = foods.find((f) => f.id === openId);

  const chips = (rows: Food[]) => (
    <ul className="kp-datechips">
      {rows.map((f) => (
        <li key={f.id} className={urgency(f).trim()}>
          <button type="button" className="kp-datechip-main kp-datechip-tap" onClick={() => setOpenId(f.id)}>
            <b>
              {f.flagged && <span className="kp-star">★ </span>}
              {f.name}
            </b>
            <small>{goodBy(f).replace("good by ", "")}</small>
          </button>
        </li>
      ))}
    </ul>
  );

  return (
    <div className="kp-look kp-look--J kp-look--K">
      <div className="kp-hero">
        <h2>Kitchen</h2>
        <div className="kp-search-row">
          <Search value={q} onChange={setQ} />
          <button type="button" className="kp-add" onClick={() => setAdding(true)}>
            + Add
          </button>
        </div>
        {!searching && (
          <div className="kp-group kp-group--star">
            <p className="kp-type">To use up</p>
            {starred.length > 0 ? chips(starred) : <p className="card-note">Tap a food to star it.</p>}
          </div>
        )}
        <Legend />
      </div>
      {typeGroups(rest).map(({ type, rows }) => (
        <div key={type} className="kp-group">
          <p className="kp-type">{type}</p>
          {chips(rows)}
        </div>
      ))}
      {open && <FoodBox food={open} ctx={ctx} onClose={() => setOpenId(null)} />}
      {adding && <AddFoodBox ctx={ctx} onClose={() => setAdding(false)} />}
    </div>
  );
}

// ------------------------------------------------------------------- the switcher

function PrototypeSwitcher({
  current,
  onChange,
  state,
  undo,
}: {
  current: string;
  onChange: (v: string) => void;
  state: string;
  undo?: () => void;
}) {
  const index = Math.max(0, VARIANTS.findIndex((v) => v.key === current));
  const step = useMemo(
    () => (by: number) => {
      const next = VARIANTS[(index + by + VARIANTS.length) % VARIANTS.length];
      if (next) onChange(next.key);
    },
    [index, onChange],
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable) return;
      if (e.key === "ArrowLeft") step(-1);
      if (e.key === "ArrowRight") step(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step]);

  return (
    <div className="kp-bar">
      <div className="kp-bar-row">
        <button type="button" aria-label="Previous variant" onClick={() => step(-1)}>
          ←
        </button>
        <strong>
          {VARIANTS[index]?.key} · {VARIANTS[index]?.name}
        </strong>
        <button type="button" aria-label="Next variant" onClick={() => step(1)}>
          →
        </button>
      </div>
      <div className="kp-bar-state">
        {state}
        {undo && (
          <button type="button" onClick={undo}>
            undo
          </button>
        )}
      </div>
    </div>
  );
}
