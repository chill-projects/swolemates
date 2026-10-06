/**
 * Drives the real template editor in jsdom: the actual markup from template.html,
 * the actual main.ts wiring, with only the MCP transport faked. drafts.test.ts
 * covers what a draft *is*; this covers what the editor *does* with one — above all
 * that a run of edits produces exactly one save.
 *
 * Browser automation can't reach these controls for real (the AppRenderer iframe is
 * sandboxed to scripts only, so synthetic and driver-issued input alike bounce off
 * the opaque origin), which makes this the only level at which the wiring gets
 * exercised at all.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import templateHtml from "./template.html?raw";

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
    set ontoolresult(handler: (result: unknown) => void) {
      app.ontoolresult = handler;
    }
  },
}));

const SQUAT = {
  id: "ex-squat",
  exercise_id: "c-squat",
  exercise_name: "Back Squat",
  superset_group: null,
  sets: 3,
  reps: 5,
  seconds: null,
  weight: 225,
  notes: "belt on",
};
const ROW = {
  id: "ex-row",
  exercise_id: "c-row",
  exercise_name: "Barbell Row",
  superset_group: null,
  sets: 4,
  reps: 8,
  seconds: null,
  weight: 135,
  notes: null,
};

function payload(exercises = [SQUAT, ROW]) {
  return { id: "tpl-1", name: "Pull Day", description: null, exercises };
}

function toolResult(value: unknown) {
  return { content: [{ type: "text", text: JSON.stringify(value) }], structuredContent: value };
}

const $ = <T extends Element>(selector: string): T => {
  const el = document.querySelector<T>(selector);
  if (!el) throw new Error(`missing ${selector}`);
  return el;
};

/** The inputs for one exercise, found the way a user finds them: by label. */
function fieldFor(name: string, label: string): HTMLInputElement {
  return $<HTMLInputElement>(`input[aria-label="${name} ${label}"]`);
}

function typeInto(input: HTMLInputElement, value: string): void {
  input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

const saveBar = () => $<HTMLDivElement>("#save-bar");
const saveBtn = () => $<HTMLButtonElement>("#save-btn");
const dirtyCount = () => $<HTMLSpanElement>("#dirty-count");

// main.ts binds its ⌘S/Enter shortcut to `document`, which in the real app is the
// iframe's own document and dies with it. Here every remount re-imports the module
// into one long-lived jsdom document, so without this each test would stack another
// live listener and a single Enter would fire N saves.
let shortcutHandlers: EventListener[] = [];
// Captured once, before any spy is installed — re-binding per mount would chain each
// spy onto the last and recurse.
const addEventListener = document.addEventListener.bind(document);

/** Load the editor fresh: real markup, real module, a payload pushed in the way a
 *  host pushes the originating tool's result. */
async function mountEditor(initial = payload()): Promise<void> {
  for (const handler of shortcutHandlers) document.removeEventListener("keydown", handler);
  shortcutHandlers = [];
  vi.spyOn(document, "addEventListener").mockImplementation((type, handler, options) => {
    if (type === "keydown") shortcutHandlers.push(handler as EventListener);
    addEventListener(type, handler as EventListener, options);
  });

  document.body.innerHTML = templateHtml.split("<body>")[1]!.split("</body>")[0]!;
  vi.resetModules();
  callServerTool.mockReset();
  callServerTool.mockResolvedValue(toolResult(initial));
  await import("./main");
  app.ontoolresult?.(toolResult(initial));
  // Open both accordions so every field is in the DOM.
  for (const toggle of document.querySelectorAll<HTMLButtonElement>(".group-toggle")) toggle.click();
}

beforeEach(async () => {
  await mountEditor();
});

describe("the template editor", () => {
  it("renders the template it was handed", () => {
    expect($<HTMLInputElement>("#name-input").value).toBe("Pull Day");
    expect(fieldFor("Back Squat", "reps").value).toBe("5");
    expect(fieldFor("Barbell Row", "sets").value).toBe("4");
  });

  it("starts with nothing to save", () => {
    expect(saveBar().hidden).toBe(true);
    expect(callServerTool).not.toHaveBeenCalled();
  });

  // The complaint this whole change exists for: every field used to save on blur,
  // and every save re-rendered the list out from under the next edit.
  it("does not save while you are typing", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    typeInto(fieldFor("Back Squat", "lbs"), "245");
    typeInto(fieldFor("Barbell Row", "sets"), "5");
    typeInto(fieldFor("Barbell Row", "Notes"), "straps");
    expect(callServerTool).not.toHaveBeenCalled();
  });

  it("offers one save for all of it", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    typeInto(fieldFor("Barbell Row", "sets"), "5");
    expect(saveBar().hidden).toBe(false);
    expect(dirtyCount().textContent).toBe("2 unsaved changes");
  });

  it("sends one update per edited exercise when saved", async () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    typeInto(fieldFor("Back Squat", "lbs"), "245");
    typeInto(fieldFor("Barbell Row", "sets"), "5");
    callServerTool.mockResolvedValue(toolResult(payload()));

    saveBtn().click();
    await vi.waitFor(() => expect(callServerTool).toHaveBeenCalledTimes(2));

    expect(callServerTool.mock.calls.map(([c]) => c.arguments)).toEqual([
      {
        template_id: "tpl-1",
        action: "update_exercise",
        template_exercise_id: "ex-squat",
        reps: 8,
        weight: 245,
      },
      {
        template_id: "tpl-1",
        action: "update_exercise",
        template_exercise_id: "ex-row",
        sets: 5,
      },
    ]);
  });

  it("clears the save bar once the batch lands", async () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    callServerTool.mockResolvedValue(toolResult(payload([{ ...SQUAT, reps: 8 }, ROW])));

    saveBtn().click();
    await vi.waitFor(() => expect(saveBar().hidden).toBe(true));
    expect(fieldFor("Back Squat", "reps").value).toBe("8");
  });

  it("sends a rename ahead of the field edits", async () => {
    typeInto($<HTMLInputElement>("#name-input"), "Heavy Pull");
    typeInto(fieldFor("Back Squat", "reps"), "8");
    callServerTool.mockResolvedValue(toolResult(payload()));

    saveBtn().click();
    await vi.waitFor(() => expect(callServerTool).toHaveBeenCalledTimes(2));
    expect(callServerTool.mock.calls[0]![0].arguments.action).toBe("rename");
    expect(callServerTool.mock.calls[1]![0].arguments.action).toBe("update_exercise");
  });

  it("drops an edit that is typed back to where it started", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    expect(saveBar().hidden).toBe(false);
    typeInto(fieldFor("Back Squat", "reps"), "5");
    expect(saveBar().hidden).toBe(true);
  });

  it("discards everything without touching the server", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    typeInto($<HTMLInputElement>("#name-input"), "Heavy Pull");
    $<HTMLButtonElement>("#discard-btn").click();

    expect(callServerTool).not.toHaveBeenCalled();
    expect(saveBar().hidden).toBe(true);
    expect(fieldFor("Back Squat", "reps").value).toBe("5");
    expect($<HTMLInputElement>("#name-input").value).toBe("Pull Day");
  });

  it("blocks the save on a value the server would reject", () => {
    typeInto(fieldFor("Back Squat", "sets"), "0");
    expect(saveBtn().disabled).toBe(true);
    expect(dirtyCount().textContent).toMatch(/at least 1/);
    expect(fieldFor("Back Squat", "sets").classList.contains("invalid")).toBe(true);
  });

  it("marks which boxes are waiting", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    expect(fieldFor("Back Squat", "reps").classList.contains("dirty")).toBe(true);
    expect(fieldFor("Barbell Row", "reps").classList.contains("dirty")).toBe(false);
  });

  // A collapsed header shouldn't claim 3×5 while the open box below it reads 8.
  it("keeps the collapsed summary in step with the edit", () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    expect($<HTMLElement>(".group-summary").textContent).toBe("3×8 reps");
  });

  it("saves on Enter, so a long template needn't be scrolled", async () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    callServerTool.mockResolvedValue(toolResult(payload()));

    fieldFor("Back Squat", "reps").focus();
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    await vi.waitFor(() => expect(callServerTool).toHaveBeenCalledTimes(1));
  });

  // A structural edit re-reads the template, which would silently drop whatever is
  // still pending — so the pending edits go first.
  it("flushes pending edits before a structural change", async () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    callServerTool.mockResolvedValue(toolResult(payload()));

    $<HTMLButtonElement>('button[title="Remove exercise"]').click();
    await vi.waitFor(() => expect(callServerTool).toHaveBeenCalledTimes(2));
    expect(callServerTool.mock.calls.map(([c]) => c.arguments.action)).toEqual([
      "update_exercise",
      "remove_exercise",
    ]);
  });

  it("re-reads from the server when part of a batch fails", async () => {
    typeInto(fieldFor("Back Squat", "reps"), "8");
    callServerTool.mockRejectedValueOnce(new Error("boom"));
    callServerTool.mockResolvedValue(toolResult(payload()));

    saveBtn().click();
    await vi.waitFor(() => expect($<HTMLElement>("#status").className).toBe("error"));
    expect(callServerTool.mock.calls[1]![0].name).toBe("get_workout_template");
    expect(saveBar().hidden).toBe(true);
    expect(fieldFor("Back Squat", "reps").value).toBe("5");
  });
});
