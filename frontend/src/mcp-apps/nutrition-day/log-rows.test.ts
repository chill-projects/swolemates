/**
 * Drives the real nutrition-day log list in jsdom — the actual markup from
 * nutrition-day.html and the actual main.ts, with only the MCP transport faked.
 * Same approach, and the same reason, as the template editor's editor.test.ts: the
 * AppRenderer iframe is sandboxed to scripts only, so browser automation can't reach
 * these controls at all.
 *
 * What it pins down is that every logged entry renders as the same row. Entries that
 * came from a saved meal used to render as a separate expandable variant whose
 * disclosure arrow sat where every other row keeps its checkbox, so the rows didn't
 * line up and a meal-derived entry couldn't be selected into a new meal.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import nutritionDayHtml from "./nutrition-day.html?raw";

const callServerTool = vi.fn();
const app = {
  callServerTool,
  connect: vi.fn().mockResolvedValue(undefined),
  ontoolresult: undefined as ((result: unknown) => void) | undefined,
};

vi.mock("@modelcontextprotocol/ext-apps", () => ({
  App: class {
    callServerTool = (...args: unknown[]) => app.callServerTool(...args);
    connect = () => app.connect();
    // main.ts hides the day hero when the SPA already draws one; report that host so
    // the rows render in the arrangement the user actually sees.
    getHostVersion = () => ({ name: "swolemates-web", version: "1.0.0" });
    set ontoolresult(handler: (result: unknown) => void) {
      app.ontoolresult = handler;
    }
  },
}));

/** A plain entry: logged directly, no sub-items. */
const PLAIN = {
  id: "log-plain",
  name: "chicken and rice",
  logged_at: "2026-09-23T17:18:45Z",
  meal_type: "lunch",
  values: { calories: 450, protein_g: 32, carbs_g: 48, fat_g: 12 },
  items: [],
};

/** An entry logged from a saved meal, so it carries the meal's items. */
const FROM_MEAL = {
  id: "log-meal",
  name: "Usual breakfast",
  logged_at: "2026-09-23T11:00:41Z",
  meal_type: null,
  values: { calories: 360, protein_g: 18 },
  items: [
    { id: "i1", name: "3 scrambled eggs", values: { calories: 270, protein_g: 18 } },
    { id: "i2", name: "Toast", values: { calories: 90 } },
  ],
};

/** A saved meal holding exactly one item — the case that made the inconsistency
 *  most obvious, since expanding it revealed nothing the row didn't already say. */
const SINGLE_ITEM = {
  id: "log-single",
  name: "Protein coffee",
  logged_at: "2026-09-23T08:56:00Z",
  meal_type: "breakfast",
  values: { calories: 51, protein_g: 7 },
  items: [{ id: "i3", name: "Protein coffee", values: { calories: 51, protein_g: 7 } }],
};

function payload(logs: unknown[]) {
  return {
    date: "2026-09-23",
    hero: {
      trackable_key: "calories",
      label: "Calories",
      unit: "kcal",
      consumed: 861,
      target: 2200,
    },
    bars: [],
    streak_key: "calories",
    logs,
    templates: [],
    summary: "861 kcal so far",
  };
}

function toolResult(value: unknown) {
  return { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value };
}

const rows = () => Array.from(document.querySelectorAll("#logs .log-entry"));
const rowFor = (name: string) =>
  rows().find((li) => li.textContent?.includes(name)) ?? null;

async function mountLog(logs: unknown[]): Promise<void> {
  document.body.innerHTML = nutritionDayHtml.split("<body>")[1]!.split("</body>")[0]!;
  vi.resetModules();
  callServerTool.mockReset();
  callServerTool.mockResolvedValue(toolResult(payload(logs)));
  await import("./main");
  app.ontoolresult?.(toolResult(payload(logs)));
}

beforeEach(async () => {
  await mountLog([PLAIN, FROM_MEAL, SINGLE_ITEM]);
});

describe("today's log rows", () => {
  it("renders one row per entry", () => {
    expect(rows()).toHaveLength(3);
  });

  // The ask: no row gets an expander some other row doesn't have.
  it("gives every row a checkbox, whatever it was logged from", () => {
    for (const name of ["chicken and rice", "Usual breakfast", "Protein coffee"]) {
      const row = rowFor(name);
      expect(row, name).not.toBeNull();
      expect(row!.querySelector("input.log-select"), name).not.toBeNull();
    }
  });

  it("has no expand toggle anywhere in the log", () => {
    expect(document.querySelector("#logs .group-toggle")).toBeNull();
    expect(document.querySelector("#logs .grouped-log-items")).toBeNull();
    expect(document.querySelector("#logs")!.textContent).not.toContain("▸");
  });

  // The count is the one thing the expander showed that the row doesn't: this entry
  // came from a saved meal.
  it("keeps the item count on the macro line", () => {
    expect(rowFor("Usual breakfast")!.querySelector(".log-values")!.textContent).toBe(
      "P 18g · 2 items",
    );
    expect(rowFor("Protein coffee")!.querySelector(".log-values")!.textContent).toBe(
      "P 7g · 1 item",
    );
  });

  it("leaves a plain entry's macro line alone", () => {
    expect(rowFor("chicken and rice")!.querySelector(".log-values")!.textContent).toBe(
      "P 32g · C 48g · F 12g",
    );
  });

  // Previously impossible: a meal-derived entry had no checkbox to tick.
  it("can select a meal-derived entry into a new meal", () => {
    const checkbox = rowFor("Usual breakfast")!.querySelector<HTMLInputElement>("input.log-select")!;
    checkbox.checked = true;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
    expect(document.querySelector<HTMLElement>("#save-template-bar")!.hidden).toBe(false);
  });
});
