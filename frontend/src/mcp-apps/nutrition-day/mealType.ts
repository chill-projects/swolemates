/**
 * Meal-type chip/select building, pulled out of main.ts so it's testable
 * without importing that module (which calls `app.connect()` at load time —
 * see main.ts's own docstring, and workout-live/prefill.ts's identical note).
 * Builds real DOM elements (jsdom-testable), but never calls a server tool
 * itself — `renderMealTypeEdit` takes an `onSelect` callback instead, so a
 * test can assert what it would have sent without a live MCP connection.
 */

export const MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack"];

export interface MealTypeEditTarget {
  /** Names the thing being tagged, for the select's accessible name. */
  label: string;
  mealType: string | null;
  /** Whether "no meal type" is a choosable value. True for a meal template
   *  (update_meal_template takes "" as an explicit clear); false for a logged
   *  entry (update_nutrition_log reads None as "leave unchanged", so it has no
   *  way to express a clear — see populateMealTypeSelect). */
  allowUnset: boolean;
}

/** Populates a meal-type <select> — shared by the log-food and save-template
 *  pickers (a real "No meal type" option, since log_nutrition/save_meal_template
 *  take meal_type=None to mean exactly that at creation time) and the editable
 *  per-log picker (no unset option — update_nutrition_log treats meal_type=None
 *  as "leave unchanged," the same "only passed fields change" convention name/
 *  values use, so there's nothing meaningful to send for "clear it"). */
export function populateMealTypeSelect(
  select: HTMLSelectElement,
  { includeUnset }: { includeUnset: boolean },
): void {
  if (includeUnset) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No meal type";
    select.appendChild(option);
  }
  for (const type of MEAL_TYPES) {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = type.charAt(0).toUpperCase() + type.slice(1);
    select.appendChild(option);
  }
}

/** Recolors a meal-type select to match its current selection, reusing the
 *  read-only chip's own .chip--* classes so an edited entry looks identical to
 *  a freshly logged one. */
export function styleMealTypeSelect(select: HTMLSelectElement, mealType: string): void {
  for (const type of MEAL_TYPES) select.classList.remove(`chip--${type}`);
  if (MEAL_TYPES.includes(mealType)) select.classList.add(`chip--${mealType}`);
}

/** The editable tag on a logged entry or a saved template — picking a value
 *  calls `onSelect` immediately, no separate save step. `onSelect` receives ""
 *  only when `allowUnset` is on, where it means "clear the tag".
 *
 *  A value that isn't one of the four (meal_type is a free string column, with
 *  nothing enforcing otherwise) is shown as a disabled option carrying its raw
 *  text, in both modes — so an oddly-tagged row reads as what it actually is
 *  rather than silently displaying as untagged. */
export function renderMealTypeEdit(
  { label, mealType, allowUnset }: MealTypeEditTarget,
  onSelect: (mealType: string) => void,
): HTMLSelectElement {
  const select = document.createElement("select");
  select.className = "meal-type-select";
  select.setAttribute("aria-label", `Meal type for ${label}`);
  const normalized = mealType?.toLowerCase() ?? null;
  const recognized = normalized !== null && MEAL_TYPES.includes(normalized);

  if (mealType !== null && !recognized) {
    const unrecognized = document.createElement("option");
    unrecognized.value = "";
    unrecognized.textContent = mealType;
    unrecognized.disabled = true;
    unrecognized.selected = true;
    select.appendChild(unrecognized);
  } else if (!allowUnset && !recognized) {
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Tag as…";
    placeholder.disabled = true;
    placeholder.selected = true;
    select.appendChild(placeholder);
  }
  populateMealTypeSelect(select, { includeUnset: allowUnset });

  const value = recognized ? (normalized as string) : "";
  select.value = value;
  styleMealTypeSelect(select, value);
  select.onchange = () => {
    // Without an unset option, "" can only be the disabled placeholder.
    if (!allowUnset && !select.value) return;
    styleMealTypeSelect(select, select.value);
    onSelect(select.value);
  };
  return select;
}
