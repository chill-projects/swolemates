import { describe, expect, it, vi } from "vitest";
import {
  MEAL_TYPES,
  populateMealTypeSelect,
  renderMealTypeEdit,
  styleMealTypeSelect,
} from "./mealType";

describe("populateMealTypeSelect", () => {
  it("includes a real unset option when asked", () => {
    const select = document.createElement("select");
    populateMealTypeSelect(select, { includeUnset: true });
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(["", ...MEAL_TYPES]);
    expect(select.options[0]?.textContent).toBe("No meal type");
  });

  it("omits the unset option for the edit picker", () => {
    const select = document.createElement("select");
    populateMealTypeSelect(select, { includeUnset: false });
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toEqual(MEAL_TYPES);
  });

  it("title-cases each option's label", () => {
    const select = document.createElement("select");
    populateMealTypeSelect(select, { includeUnset: false });
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual([
      "Breakfast",
      "Lunch",
      "Dinner",
      "Snack",
    ]);
  });
});

describe("styleMealTypeSelect", () => {
  it("adds the matching chip color class and clears any other", () => {
    const select = document.createElement("select");
    select.classList.add("chip--lunch");
    styleMealTypeSelect(select, "dinner");
    expect(select.classList.contains("chip--lunch")).toBe(false);
    expect(select.classList.contains("chip--dinner")).toBe(true);
  });

  it("leaves no chip color class for an unrecognized value", () => {
    const select = document.createElement("select");
    styleMealTypeSelect(select, "brunch");
    expect(MEAL_TYPES.some((t) => select.classList.contains(`chip--${t}`))).toBe(false);
  });
});

// A logged entry: update_nutrition_log can't express "clear", so no unset option.
const logged = (mealType: string | null) =>
  ({ label: "Yogurt", mealType, allowUnset: false }) as const;
// A saved template: update_meal_template takes "" as an explicit clear.
const template = (mealType: string | null) =>
  ({ label: "Usual breakfast", mealType, allowUnset: true }) as const;

describe("renderMealTypeEdit — a logged entry (no clearing)", () => {
  it("shows a disabled 'Tag as…' placeholder when untagged", () => {
    const select = renderMealTypeEdit(logged(null), vi.fn());
    expect(select.value).toBe("");
    expect(select.options[0]?.textContent).toBe("Tag as…");
    expect(select.options[0]?.disabled).toBe(true);
  });

  it("selects and colors a recognized meal type, case-insensitively", () => {
    const select = renderMealTypeEdit(logged("Breakfast"), vi.fn());
    expect(select.value).toBe("breakfast");
    expect(select.classList.contains("chip--breakfast")).toBe(true);
    // No placeholder — the four real ones are exactly the choices.
    expect(Array.from(select.options).map((o) => o.value)).toEqual(MEAL_TYPES);
  });

  it("calls onSelect with the new value when a real option is picked", () => {
    const onSelect = vi.fn();
    const select = renderMealTypeEdit(logged(null), onSelect);
    select.value = "lunch";
    select.dispatchEvent(new Event("change"));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith("lunch");
    expect(select.classList.contains("chip--lunch")).toBe(true);
  });

  it("never calls onSelect for the disabled placeholder itself", () => {
    // A real <select> can't land on a disabled option via user interaction, but
    // the handler still guards against an empty value defensively.
    const onSelect = vi.fn();
    const select = renderMealTypeEdit(logged(null), onSelect);
    select.dispatchEvent(new Event("change"));
    expect(onSelect).not.toHaveBeenCalled();
  });
});

describe("renderMealTypeEdit — a saved template (clearable)", () => {
  it("offers a real 'No meal type' option, selected when untagged", () => {
    const select = renderMealTypeEdit(template(null), vi.fn());
    expect(Array.from(select.options).map((o) => o.value)).toEqual(["", ...MEAL_TYPES]);
    expect(select.value).toBe("");
    expect(select.options[0]?.disabled).toBe(false);
  });

  it("sends '' when the unset option is chosen, so the server clears the tag", () => {
    const onSelect = vi.fn();
    const select = renderMealTypeEdit(template("dinner"), onSelect);
    expect(select.classList.contains("chip--dinner")).toBe(true);
    select.value = "";
    select.dispatchEvent(new Event("change"));
    expect(onSelect).toHaveBeenCalledExactlyOnceWith("");
    // Cleared visually too — no leftover color from the old tag.
    expect(MEAL_TYPES.some((t) => select.classList.contains(`chip--${t}`))).toBe(false);
  });
});

describe("renderMealTypeEdit — an unrecognized stored value", () => {
  it.each([
    ["a logged entry", logged("Brunch")],
    ["a saved template", template("Brunch")],
  ])("surfaces it as disabled placeholder text rather than hiding it, for %s", (_label, target) => {
    const select = renderMealTypeEdit(target, vi.fn());
    expect(select.value).toBe("");
    expect(select.options[0]?.textContent).toBe("Brunch");
    expect(select.options[0]?.disabled).toBe(true);
  });
});
