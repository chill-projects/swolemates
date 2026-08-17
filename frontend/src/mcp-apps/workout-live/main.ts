/**
 * The in-workout component. Renders in two hosts from this one bundle:
 *  - Claude, via the `ui://swolemates/workout-live.html` MCP resource
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * Layout is the decided prototype (Variant D, `prototype/in-workout-layout`):
 * a scrollable accordion grouped by superset, open-ended sets. Any tool call
 * that changes the active workout returns this same payload shape, so the
 * component re-renders fully from whichever result the host pushes — no
 * separate fetch (the tmpx/nutrition-day pattern).
 *
 * "Add set" has no server-side pending state — the draft row here is pure
 * client UI; tapping "Log set" *is* the `log_set` call, nothing is written
 * before that. An abandoned draft just vanishes on the next render.
 *
 * No `window.prompt()`/`confirm()`: the iframe is sandboxed without
 * allow-modals, where those are silently unusable.
 */

import { App } from "@modelcontextprotocol/ext-apps";

interface LastTimeSet {
  weight: number | null;
  reps: number | null;
}

interface LastTime {
  sets: LastTimeSet[];
  note: string | null;
}

interface SetEntry {
  id: string;
  set_number: number;
  set_type: "reps" | "time";
  is_warmup: boolean;
  weight: number | null;
  reps: number | null;
  work_seconds: number | null;
}

interface ExerciseEntry {
  id: string;
  exercise_id: string;
  exercise_name: string | null;
  next_time_note: string | null;
  sets: SetEntry[];
  last_time: LastTime | null;
}

interface Group {
  superset_group: number | null;
  is_superset: boolean;
  exercises: ExerciseEntry[];
}

interface LivePayload {
  active: boolean;
  id?: string;
  completed_at?: string | null;
  groups?: Group[];
  summary: string;
}

interface CatalogExercise {
  id: string;
  name: string;
  muscle_group: string;
}

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const emptyEl = $<HTMLDivElement>("empty");
const startBtn = $<HTMLButtonElement>("start-btn");
const workoutEl = $<HTMLDivElement>("workout");
const groupsEl = $<HTMLDivElement>("groups");
const pickerEl = $<HTMLDivElement>("picker");
const pickerFilterEl = $<HTMLInputElement>("picker-filter");
const pickerListEl = $<HTMLUListElement>("picker-list");
const pickerCancelEl = $<HTMLButtonElement>("picker-cancel");
const addExerciseBtn = $<HTMLButtonElement>("add-exercise-btn");
const finishBtn = $<HTMLButtonElement>("finish-btn");

// Open/collapsed accordion state and the exercise catalog cache both live outside
// render() so they survive the re-renders every tool call triggers.
const openGroups = new Set<string>();
let currentPayload: LivePayload | null = null;
let exerciseCatalog: CatalogExercise[] | null = null;
let pickerSupersetWith: string | null = null;

const app = new App({ name: "Swolemates Workouts", version: "1.0.0" });

function extractPayload(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): LivePayload | null {
  const structured = result.structuredContent as LivePayload | undefined;
  if (structured && typeof structured.active === "boolean") return structured;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as LivePayload;
    return typeof parsed.active === "boolean" ? parsed : null;
  } catch {
    return null;
  }
}

function groupKey(g: Group): string {
  return g.superset_group !== null ? `s${g.superset_group}` : `e${g.exercises[0]?.id ?? ""}`;
}

function formatLastTime(lt: LastTime): string {
  const sets = lt.sets
    .map((s) => (s.weight != null ? `${s.weight}lbs × ${s.reps}` : `${s.reps ?? "?"}`))
    .join(", ");
  const base = sets || "no sets logged";
  return lt.note ? `${base} — ${lt.note}` : base;
}

function renderExercise(e: ExerciseEntry, finished: boolean): HTMLDivElement {
  const wrap = document.createElement("div");
  wrap.className = "exercise";

  const header = document.createElement("div");
  header.className = "exercise-header";
  const name = document.createElement("strong");
  name.textContent = e.exercise_name ?? "Exercise";
  header.appendChild(name);

  if (!finished && e.sets.length === 0) {
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "muted remove-x";
    removeBtn.textContent = "×";
    removeBtn.title = "Remove exercise";
    removeBtn.onclick = () =>
      void callAndRender("update_workout_entry", {
        workout_id: currentPayload?.id,
        action: "remove_exercise",
        workout_exercise_id: e.id,
      });
    header.appendChild(removeBtn);
  }

  if (!finished) {
    const supersetBtn = document.createElement("button");
    supersetBtn.type = "button";
    supersetBtn.textContent = "+ Superset";
    supersetBtn.onclick = () => openPicker(e.id);
    header.appendChild(supersetBtn);
  }

  wrap.appendChild(header);

  if (e.last_time) {
    const lt = document.createElement("div");
    lt.className = "muted last-time";
    lt.textContent = `Last time: ${formatLastTime(e.last_time)}`;
    wrap.appendChild(lt);
  }

  const list = document.createElement("ul");
  list.className = "logged-sets";
  list.replaceChildren(
    ...e.sets.map((s) => {
      const li = document.createElement("li");
      const base =
        s.set_type === "time"
          ? `${s.work_seconds}s`
          : `${s.weight ?? "—"}lbs × ${s.reps}`;
      li.textContent = s.is_warmup ? `${base} (warmup)` : base;
      return li;
    }),
  );
  wrap.appendChild(list);

  if (!finished) {
    const draft = document.createElement("div");
    draft.className = "draft-set";

    const weightInput = document.createElement("input");
    weightInput.type = "number";
    weightInput.step = "5";
    weightInput.placeholder = "lbs";
    weightInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} weight`);

    const repsInput = document.createElement("input");
    repsInput.type = "number";
    repsInput.placeholder = "reps";
    repsInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} reps`);

    const warmupLabel = document.createElement("label");
    const warmupInput = document.createElement("input");
    warmupInput.type = "checkbox";
    warmupLabel.append(warmupInput, document.createTextNode(" warmup"));

    const logBtn = document.createElement("button");
    logBtn.type = "button";
    logBtn.textContent = "Log set";
    logBtn.onclick = () => {
      if (repsInput.value === "") return;
      const weight = weightInput.value === "" ? undefined : Number(weightInput.value);
      void callAndRender("log_set", {
        exercise: e.exercise_name,
        weight,
        reps: Number(repsInput.value),
        is_warmup: warmupInput.checked,
      });
    };

    draft.append(weightInput, repsInput, warmupLabel, logBtn);
    wrap.appendChild(draft);

    const noteInput = document.createElement("input");
    noteInput.type = "text";
    noteInput.className = "next-time-note";
    noteInput.placeholder = "Notes for next time";
    noteInput.value = e.next_time_note ?? "";
    noteInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} notes for next time`);
    noteInput.onblur = () => {
      if (noteInput.value === (e.next_time_note ?? "")) return;
      void callAndRender("update_workout_entry", {
        workout_id: currentPayload?.id,
        action: "set_next_time_note",
        workout_exercise_id: e.id,
        note: noteInput.value,
      });
    };
    wrap.appendChild(noteInput);
  }

  return wrap;
}

function renderGroup(g: Group, finished: boolean): HTMLDivElement {
  const key = groupKey(g);
  const isOpen = openGroups.has(key);
  const totalSets = g.exercises.reduce((n, e) => n + e.sets.length, 0);
  const title = g.exercises.map((e) => e.exercise_name ?? "Exercise").join(" + ");

  const wrap = document.createElement("div");
  wrap.className = "group";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "group-toggle";
  const arrow = document.createElement("span");
  arrow.textContent = isOpen ? "▾" : "▸";
  const titleEl = document.createElement("strong");
  titleEl.textContent = title;
  toggle.append(arrow, titleEl);
  if (g.is_superset) {
    const badge = document.createElement("span");
    badge.className = "badge";
    badge.textContent = "superset";
    toggle.appendChild(badge);
  }
  const count = document.createElement("span");
  count.className = "group-count muted";
  count.textContent = `${totalSets} set${totalSets === 1 ? "" : "s"}`;
  toggle.appendChild(count);
  toggle.onclick = () => {
    if (openGroups.has(key)) openGroups.delete(key);
    else openGroups.add(key);
    if (currentPayload) render(currentPayload);
  };
  wrap.appendChild(toggle);

  const body = document.createElement("div");
  body.className = "group-body";
  body.hidden = !isOpen;
  if (g.is_superset) {
    const hint = document.createElement("p");
    hint.className = "muted superset-hint";
    hint.textContent = `Work back-to-back, then rest: ${g.exercises
      .map((e) => e.exercise_name)
      .join(" → ")} → rest → repeat.`;
    body.appendChild(hint);
  }
  g.exercises.forEach((e, i) => {
    if (i > 0) body.appendChild(document.createElement("hr"));
    body.appendChild(renderExercise(e, finished));
  });
  wrap.appendChild(body);

  return wrap;
}

function render(payload: LivePayload): void {
  currentPayload = payload;
  statusEl.textContent = payload.summary;
  statusEl.className = "muted";

  if (!payload.active) {
    emptyEl.hidden = false;
    workoutEl.hidden = true;
    return;
  }
  emptyEl.hidden = true;
  workoutEl.hidden = false;
  closePicker();

  const finished = payload.completed_at != null;
  finishBtn.hidden = finished;
  addExerciseBtn.hidden = finished;

  const groups = payload.groups ?? [];
  const firstGroup = groups[0];
  if (openGroups.size === 0 && firstGroup) openGroups.add(groupKey(firstGroup));
  groupsEl.replaceChildren(...groups.map((g) => renderGroup(g, finished)));
}

async function loadCatalog(): Promise<void> {
  const result = await app.callServerTool({ name: "list_workout_exercises", arguments: {} });
  const structured = result.structuredContent as { exercises: CatalogExercise[] } | undefined;
  exerciseCatalog = structured?.exercises ?? [];
}

function renderPickerList(filter: string): void {
  const q = filter.trim().toLowerCase();
  const matches = (exerciseCatalog ?? []).filter((ex) => ex.name.toLowerCase().includes(q));
  const byGroup = new Map<string, CatalogExercise[]>();
  for (const ex of matches) {
    const list = byGroup.get(ex.muscle_group) ?? [];
    list.push(ex);
    byGroup.set(ex.muscle_group, list);
  }

  const items: HTMLElement[] = [];
  for (const [group, exs] of byGroup) {
    const label = document.createElement("li");
    label.className = "picker-group-label";
    label.textContent = group;
    items.push(label);
    for (const ex of exs) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = ex.name;
      btn.onclick = () => {
        const supersetWith = pickerSupersetWith;
        closePicker();
        void callAndRender("update_workout_entry", {
          workout_id: currentPayload?.id,
          action: "add_exercise",
          exercise: ex.name,
          ...(supersetWith ? { superset_with: supersetWith } : {}),
        });
      };
      li.appendChild(btn);
      items.push(li);
    }
  }
  pickerListEl.replaceChildren(...items);
}

function openPicker(supersetWith: string | null): void {
  pickerSupersetWith = supersetWith;
  pickerEl.hidden = false;
  pickerFilterEl.value = "";
  if (exerciseCatalog) renderPickerList("");
  else void loadCatalog().then(() => renderPickerList(""));
}

function closePicker(): void {
  pickerEl.hidden = true;
  pickerSupersetWith = null;
}

async function callAndRender(name: string, args: Record<string, unknown>): Promise<void> {
  try {
    const result = await app.callServerTool({ name, arguments: args });
    const payload = extractPayload(result);
    if (payload) {
      render(payload);
      return;
    }
    // log_set's >90-minute clarification path returns plain text, not a payload.
    const text = result.content?.find((c) => c.type === "text")?.text;
    if (text) statusEl.textContent = text;
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

startBtn.onclick = () => void callAndRender("start_workout", {});
addExerciseBtn.onclick = () => openPicker(null);
pickerFilterEl.oninput = () => renderPickerList(pickerFilterEl.value);
pickerCancelEl.onclick = () => closePicker();
finishBtn.onclick = () => {
  if (!currentPayload?.id) return;
  void callAndRender("finish_workout", { workout_id: currentPayload.id });
};

// Hosts with a push channel (the SPA) send fresh results proactively; hosts without
// one (a chat widget) at least get freshness whenever the user returns to the tab.
// No interval polling: in chat hosts every server call may prompt for approval.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void callAndRender("get_active_workout", {});
});

// The host pushes the originating tool's result once on render.
app.ontoolresult = (result) => {
  const payload = extractPayload(result);
  if (payload) render(payload);
  else statusEl.textContent = "Waiting for data…";
};

await app.connect();
statusEl.textContent = "Loading…";
