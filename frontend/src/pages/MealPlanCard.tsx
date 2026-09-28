import { useMemo, useState } from "react";

import {
  type KitchenItem,
  type PlannedMeal,
  useAddKitchenItem,
  useClearPlannedMeal,
  useKitchen,
  useLogPlannedMeal,
  useMealPlan,
  usePlanMeal,
  useRemoveKitchenItem,
  useUpdatePlannedMeal,
} from "../api/mealPlan";
import { useTemplates } from "../api/plan";
import { Card } from "../components/ui";
import {
  EDITABLE_TRACKABLES,
  MEAL_TYPES,
  TRACKABLE_LABELS,
  addDays,
  dayLabel,
  dayMacros,
  isoDate,
  macroLabel,
  macrosFromForm,
  sortBySlot,
  tidyNumber,
  weekStart,
} from "../lib/mealPlan";

type Slot = { date: string; mealType: string };

/**
 * The eating half of the Plan tab.
 *
 * Seven day columns, four slots each, sitting under the weekly workout pattern so a
 * day reads as one thing. Clicking a slot opens the picker; the picker's sources are
 * ordered by what you're most likely to want — leftovers that need eating, then saved
 * meals, then a name with no numbers.
 *
 * Deliberately plain React rather than an mcp-apps bundle: the picker and the macro
 * editor are a lot of interaction to drive through the AppBridge, and Claude reaches
 * all of this through the meal-plan tools instead. A `ui://` component can come later
 * if the chat side wants to render the week rather than describe it.
 */
export function MealPlanCard() {
  const [anchor, setAnchor] = useState(() => weekStart(new Date()));
  const start = isoDate(anchor);
  const end = isoDate(addDays(anchor, 6));

  const plan = useMealPlan(start, end);
  const kitchen = useKitchen();
  const templates = useTemplates();

  const [openSlot, setOpenSlot] = useState<Slot | null>(null);
  const [editing, setEditing] = useState<PlannedMeal | null>(null);

  const planMeal = usePlanMeal();
  const clearMeal = useClearPlannedMeal();
  const logMeal = useLogPlannedMeal();

  const todayIso = isoDate(new Date());
  const error =
    planMeal.error ?? clearMeal.error ?? logMeal.error ?? plan.error ?? kitchen.error;

  return (
    <Card
      title="Meal plan"
      meta={
        <span className="card-meta meal-week-nav">
          <button type="button" onClick={() => setAnchor(addDays(anchor, -7))} aria-label="Previous week">
            ‹
          </button>
          <span>
            {dayLabel(start)} – {dayLabel(end)}
          </span>
          <button type="button" onClick={() => setAnchor(addDays(anchor, 7))} aria-label="Next week">
            ›
          </button>
        </span>
      }
    >
      {error && <p className="error">{(error as Error).message}</p>}
      {plan.isPending && <p className="muted">Loading…</p>}

      <div className="meal-week">
        {(plan.data ?? []).map((day) => {
          const meals = sortBySlot(day.meals);
          const macros = dayMacros(meals);
          const bySlot = new Map(meals.map((m) => [m.meal_type, m]));
          return (
            <div
              key={day.scheduled_for}
              className={day.scheduled_for === todayIso ? "meal-day meal-day--today" : "meal-day"}
            >
              <span className="meal-day-name">{dayLabel(day.scheduled_for)}</span>
              {MEAL_TYPES.map((mealType) => {
                const meal = bySlot.get(mealType);
                const isOpen =
                  openSlot?.date === day.scheduled_for && openSlot?.mealType === mealType;
                return (
                  <button
                    key={mealType}
                    type="button"
                    className={
                      (meal ? `meal-slot meal-slot--${mealType}` : "meal-slot meal-slot--empty") +
                      (isOpen ? " is-open" : "")
                    }
                    onClick={() =>
                      setOpenSlot(isOpen ? null : { date: day.scheduled_for, mealType })
                    }
                  >
                    <span className="meal-slot-kind">{mealType}</span>
                    <span className="meal-slot-name">{meal ? meal.name : "+ add"}</span>
                    {meal && (
                      <span
                        className={
                          meal.estimated ? "meal-slot-macros" : "meal-slot-macros is-unknown"
                        }
                      >
                        {macroLabel(meal)}
                      </span>
                    )}
                    {meal?.status === "logged" && <span className="meal-slot-logged">logged</span>}
                  </button>
                );
              })}
              <div className="meal-day-foot">
                <b>{macros.calories.toLocaleString()}</b> kcal · {macros.protein} g
                {macros.unestimated > 0 && (
                  <span className="meal-day-unknown">{macros.unestimated} not estimated</span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {openSlot && (
        <MealPicker
          slot={openSlot}
          kitchen={kitchen.data ?? []}
          templates={(templates.data ?? []).map((t) => ({ id: t.id, name: t.name }))}
          current={
            (plan.data ?? [])
              .find((d) => d.scheduled_for === openSlot.date)
              ?.meals.find((m) => m.meal_type === openSlot.mealType) ?? null
          }
          busy={planMeal.isPending}
          onPick={(body) => {
            planMeal.mutate(
              { scheduled_for: openSlot.date, meal_type: openSlot.mealType, ...body },
              { onSuccess: () => setOpenSlot(null) },
            );
          }}
          onEdit={(meal) => {
            setEditing(meal);
            setOpenSlot(null);
          }}
          onLog={(meal) => logMeal.mutate(meal.id, { onSuccess: () => setOpenSlot(null) })}
          onClear={(meal) => clearMeal.mutate(meal.id, { onSuccess: () => setOpenSlot(null) })}
          onClose={() => setOpenSlot(null)}
        />
      )}

      {editing && <MacroEditor meal={editing} onClose={() => setEditing(null)} />}

      <KitchenTray items={kitchen.data ?? []} templates={templates.data ?? []} />
    </Card>
  );
}

/** What a slot can be filled with, in the order you're most likely to want it. */
function MealPicker({
  slot,
  kitchen,
  templates,
  current,
  busy,
  onPick,
  onEdit,
  onLog,
  onClear,
  onClose,
}: {
  slot: Slot;
  kitchen: KitchenItem[];
  templates: { id: string; name: string }[];
  current: PlannedMeal | null;
  busy: boolean;
  onPick: (body: { template_id?: string; kitchen_item_id?: string; name?: string }) => void;
  onEdit: (meal: PlannedMeal) => void;
  onLog: (meal: PlannedMeal) => void;
  onClear: (meal: PlannedMeal) => void;
  onClose: () => void;
}) {
  const [quick, setQuick] = useState("");
  const leftovers = kitchen.filter((i) => i.kind === "leftover");
  const ingredients = kitchen.filter((i) => i.kind === "ingredient");

  return (
    <div className="meal-picker">
      <div className="meal-picker-head">
        <strong>
          {dayLabel(slot.date)} · {slot.mealType}
        </strong>
        {current && <span className="muted">currently {current.name}</span>}
        <button type="button" className="meal-picker-close" onClick={onClose}>
          Close
        </button>
      </div>

      {current && (
        <div className="meal-picker-actions">
          <button type="button" onClick={() => onEdit(current)}>
            Edit macros
          </button>
          {current.status !== "logged" && (
            <button type="button" onClick={() => onLog(current)}>
              Log it
            </button>
          )}
          <button type="button" className="danger" onClick={() => onClear(current)}>
            Clear slot
          </button>
        </div>
      )}

      {leftovers.length > 0 && (
        <>
          <p className="meal-picker-group">Needs eating</p>
          <ul className="meal-options">
            {leftovers.map((item) => (
              <li key={item.id} className="is-leftover">
                <button type="button" disabled={busy} onClick={() => onPick({ kitchen_item_id: item.id })}>
                  <span className="mo-name">{item.name}</span>
                  <span className="mo-macros">
                    {tidyNumber(item.values.calories)} kcal · {tidyNumber(item.values.protein_g)} g
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}

      {ingredients.map((item) => (
        <div key={item.id}>
          <p className="meal-picker-group">
            To use up <b>{item.name.toLowerCase()}</b>
          </p>
          <ul className="meal-options">
            {item.templates.map((t) => (
              <li key={t.id}>
                <button type="button" disabled={busy} onClick={() => onPick({ template_id: t.id })}>
                  <span className="mo-name">{t.name}</span>
                </button>
              </li>
            ))}
            {item.templates.length === 0 && (
              <li className="muted meal-options-empty">No saved meal uses it yet.</li>
            )}
          </ul>
        </div>
      ))}

      <p className="meal-picker-group">Saved meals</p>
      <ul className="meal-options">
        {templates.map((t) => (
          <li key={t.id}>
            <button type="button" disabled={busy} onClick={() => onPick({ template_id: t.id })}>
              <span className="mo-name">{t.name}</span>
            </button>
          </li>
        ))}
        {templates.length === 0 && (
          <li className="muted meal-options-empty">
            No saved meals yet — save one from a logged day.
          </li>
        )}
      </ul>

      <p className="meal-picker-group">Something else</p>
      <div className="meal-quick">
        <input
          type="text"
          value={quick}
          placeholder="e.g. dinner at Mum's"
          aria-label="Name this meal"
          onChange={(e) => setQuick(e.target.value)}
        />
        <button
          type="button"
          disabled={busy || quick.trim() === ""}
          onClick={() => onPick({ name: quick.trim() })}
        >
          Add
        </button>
      </div>
      <p className="card-note">No numbers attached — the day will say so rather than guess.</p>
    </div>
  );
}

/** Correcting the macros, which is the edit people actually reach for. */
function MacroEditor({ meal, onClose }: { meal: PlannedMeal; onClose: () => void }) {
  const update = useUpdatePlannedMeal();
  const [name, setName] = useState(meal.name);
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      EDITABLE_TRACKABLES.map((key) => [key, tidyNumber(meal.values[key])]),
    ),
  );

  const macros = useMemo(() => macrosFromForm(form), [form]);

  return (
    <div className="meal-editor">
      <div className="meal-picker-head">
        <strong>{meal.name}</strong>
        <span className="muted">
          {dayLabel(meal.scheduled_for)} · {meal.meal_type}
        </span>
        <button type="button" className="meal-picker-close" onClick={onClose}>
          Close
        </button>
      </div>

      <label className="meal-editor-name">
        <span>Name</span>
        <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
      </label>

      <div className="meal-editor-macros">
        {EDITABLE_TRACKABLES.map((key) => (
          <label key={key}>
            <span>{TRACKABLE_LABELS[key]}</span>
            <input
              type="number"
              min="0"
              value={form[key] ?? ""}
              aria-label={TRACKABLE_LABELS[key]}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
      </div>

      <p className="card-note">
        {Object.keys(macros).length === 0
          ? "All blank — saving puts the numbers back to whatever the meal itself says."
          : meal.overridden
            ? "These numbers are yours; editing the saved meal later won't change them."
            : "Saving these replaces the numbers derived from the saved meal."}
      </p>

      <div className="meal-picker-actions">
        <button
          type="button"
          className="primary"
          disabled={update.isPending}
          onClick={() =>
            update.mutate(
              { id: meal.id, body: { name, values: macros } },
              { onSuccess: onClose },
            )
          }
        >
          {update.isPending ? "Saving…" : "Save"}
        </button>
        <button type="button" onClick={onClose}>
          Cancel
        </button>
      </div>
      {update.error && <p className="error">{(update.error as Error).message}</p>}
    </div>
  );
}

/** The "needs eating" tray, and the form that fills it. */
function KitchenTray({
  items,
  templates,
}: {
  items: KitchenItem[];
  templates: { id: string; name: string }[];
}) {
  const add = useAddKitchenItem();
  const remove = useRemoveKitchenItem();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"leftover" | "ingredient">("leftover");
  const [name, setName] = useState("");
  const [portion, setPortion] = useState("0.5");
  const [calories, setCalories] = useState("");
  const [protein, setProtein] = useState("");
  const [usedBy, setUsedBy] = useState<string[]>([]);

  const reset = () => {
    setName("");
    setCalories("");
    setProtein("");
    setUsedBy([]);
    setOpen(false);
  };

  return (
    <div className="kitchen">
      <div className="kitchen-head">
        <h3>Needs eating</h3>
        <span className="card-meta">leftovers go straight on a day · ingredients suggest meals</span>
        <button type="button" onClick={() => setOpen(!open)}>
          {open ? "Cancel" : "+ Add something"}
        </button>
      </div>

      {open && (
        <div className="kitchen-form">
          <div className="kitchen-kind">
            <button
              type="button"
              aria-pressed={kind === "leftover"}
              onClick={() => setKind("leftover")}
            >
              Leftovers
            </button>
            <button
              type="button"
              aria-pressed={kind === "ingredient"}
              onClick={() => setKind("ingredient")}
            >
              An ingredient
            </button>
          </div>

          <label>
            <span>Name</span>
            <input
              type="text"
              value={name}
              placeholder={kind === "leftover" ? "Chicken curry" : "Half a cabbage"}
              onChange={(e) => setName(e.target.value)}
            />
          </label>

          {kind === "leftover" ? (
            <>
              <label>
                <span>How much is left</span>
                <select value={portion} onChange={(e) => setPortion(e.target.value)}>
                  <option value="0.25">a quarter</option>
                  <option value="0.5">half</option>
                  <option value="0.75">three quarters</option>
                  <option value="1">all of it</option>
                </select>
              </label>
              <label>
                <span>Whole meal kcal</span>
                <input
                  type="number"
                  min="0"
                  value={calories}
                  aria-label="Whole meal kcal"
                  onChange={(e) => setCalories(e.target.value)}
                />
              </label>
              <label>
                <span>Whole meal protein</span>
                <input
                  type="number"
                  min="0"
                  value={protein}
                  aria-label="Whole meal protein"
                  onChange={(e) => setProtein(e.target.value)}
                />
              </label>
              <p className="card-note">
                Give the whole meal's numbers — the portion scales them, so correcting
                &ldquo;actually there's a third left&rdquo; later is one change.
              </p>
            </>
          ) : (
            <label>
              <span>Meals that use it</span>
              <select
                multiple
                value={usedBy}
                aria-label="Meals that use it"
                onChange={(e) =>
                  setUsedBy(Array.from(e.target.selectedOptions).map((o) => o.value))
                }
              >
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <div className="meal-picker-actions">
            <button
              type="button"
              className="primary"
              disabled={add.isPending || name.trim() === ""}
              onClick={() =>
                add.mutate(
                  kind === "leftover"
                    ? {
                        kind,
                        name: name.trim(),
                        portion,
                        values: macrosFromForm({ calories, protein_g: protein }),
                      }
                    : { kind, name: name.trim(), template_ids: usedBy },
                  { onSuccess: reset },
                )
              }
            >
              Add
            </button>
          </div>
          {add.error && <p className="error">{(add.error as Error).message}</p>}
        </div>
      )}

      <ul className="kitchen-list">
        {items.map((item) => (
          <li key={item.id} className={item.kind === "leftover" ? "is-leftover" : undefined}>
            <span className="k-name">
              {item.name}
              <span className="k-detail">
                {item.kind === "leftover"
                  ? `${tidyNumber(item.values.calories)} kcal · ${tidyNumber(item.values.protein_g)} g`
                  : item.templates.length
                    ? `used by ${item.templates.map((t) => t.name).join(", ")}`
                    : "no meal uses it yet"}
              </span>
            </span>
            <button
              type="button"
              className="k-remove"
              aria-label={`Remove ${item.name}`}
              onClick={() => remove.mutate(item.id)}
            >
              ×
            </button>
          </li>
        ))}
        {items.length === 0 && (
          <li className="muted">Nothing waiting. Add what needs eating and plan around it.</li>
        )}
      </ul>
    </div>
  );
}
