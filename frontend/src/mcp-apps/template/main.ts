/**
 * The template editor component. Renders in two hosts from this one bundle:
 *  - Claude, via the `ui://swolemates/template.html` MCP resource (create_workout_
 *    template/get_workout_template push a result into it; update_workout_template
 *    is app-only, driven by this component's own controls)
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * No "create from scratch" flow here: per the resolved design doc, templates are
 * created conversationally in chat ("make me a pull day") — this component only
 * ever views/edits an *existing* template, same grouped-by-superset accordion shape
 * as workout-live's, but editing targets (sets/reps/weight) instead of logging
 * actuals. Unlike workout-live, "remove exercise" has no 0-sets gate — a template
 * exercise has no logged history to protect.
 */

import { App } from "@modelcontextprotocol/ext-apps";

interface TemplateExercise {
  id: string;
  exercise_id: string;
  exercise_name: string | null;
  superset_group: number | null;
  sets: number;
  reps: number | null;
  seconds: number | null;
  weight: number | null;
  notes: string | null;
}

interface TemplatePayload {
  id: string;
  name: string;
  description: string | null;
  exercises: TemplateExercise[];
}

interface Group {
  key: string;
  superset_group: number | null;
  is_superset: boolean;
  exercises: TemplateExercise[];
}

interface CatalogExercise {
  id: string;
  name: string;
  muscle_group: string;
  equipment: string | null;
}

const UNSPECIFIED_EQUIPMENT = "Unspecified";

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const templateEl = $<HTMLDivElement>("template");
const nameInputEl = $<HTMLInputElement>("name-input");
const groupsEl = $<HTMLDivElement>("groups");
const pickerEl = $<HTMLDivElement>("picker");
const pickerFilterEl = $<HTMLInputElement>("picker-filter");
const pickerFilterToggleEl = $<HTMLButtonElement>("picker-filter-toggle");
const pickerFilterBadgeEl = $<HTMLSpanElement>("picker-filter-badge");
const pickerDrawerEl = $<HTMLDivElement>("picker-drawer");
const pickerCategoryChipsEl = $<HTMLDivElement>("picker-category-chips");
const pickerEquipmentChipsEl = $<HTMLDivElement>("picker-equipment-chips");
const pickerListEl = $<HTMLUListElement>("picker-list");
const pickerCancelEl = $<HTMLButtonElement>("picker-cancel");
const addExerciseBtn = $<HTMLButtonElement>("add-exercise-btn");
const archiveBtn = $<HTMLButtonElement>("archive-btn");

const openGroups = new Set<string>();
// Only the very first render defaults a group open — `openGroups.size === 0` isn't
// a safe proxy for "first render," since collapsing the last open group also makes
// it 0 and would otherwise snap that group right back open.
let hasSetDefaultOpenGroup = false;
let currentPayload: TemplatePayload | null = null;
let exerciseCatalog: CatalogExercise[] | null = null;
let pickerSupersetWith: string | null = null;
// null means "All" for both — persist across picker close/reopen (and across
// catalog reloads) so filtering to e.g. legs+dumbbell survives adding several
// exercises in a row.
let selectedCategory: string | null = null;
let selectedEquipment: string | null = null;

const app = new App({ name: "Swolemates Templates", version: "1.0.0" });

function extractPayload(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): TemplatePayload | null {
  const structured = result.structuredContent as TemplatePayload | undefined;
  if (structured && Array.isArray(structured.exercises)) return structured;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as TemplatePayload;
    return Array.isArray(parsed.exercises) ? parsed : null;
  } catch {
    return null;
  }
}

function groupKey(e: TemplateExercise): string {
  return e.superset_group !== null ? `s${e.superset_group}` : `e${e.id}`;
}

function groupExercises(exercises: TemplateExercise[]): Group[] {
  const byKey = new Map<string, Group>();
  for (const e of exercises) {
    const key = groupKey(e);
    let group = byKey.get(key);
    if (!group) {
      group = { key, superset_group: e.superset_group, is_superset: false, exercises: [] };
      byKey.set(key, group);
    }
    group.exercises.push(e);
  }
  for (const group of byKey.values()) group.is_superset = group.exercises.length > 1;
  return [...byKey.values()];
}

function targetLabel(e: TemplateExercise): string {
  return e.seconds != null ? `${e.seconds}s` : `${e.reps ?? "?"} reps`;
}

function renderExercise(e: TemplateExercise): HTMLDivElement {
  const wrap = document.createElement("div");
  wrap.className = "exercise";

  const header = document.createElement("div");
  header.className = "exercise-header";
  const name = document.createElement("strong");
  name.textContent = e.exercise_name ?? "Exercise";
  header.appendChild(name);

  const removeBtn = document.createElement("button");
  removeBtn.type = "button";
  removeBtn.className = "muted remove-x";
  removeBtn.textContent = "×";
  removeBtn.title = "Remove exercise";
  removeBtn.onclick = () =>
    void callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "remove_exercise",
      template_exercise_id: e.id,
    });
  header.appendChild(removeBtn);

  const supersetBtn = document.createElement("button");
  supersetBtn.type = "button";
  supersetBtn.textContent = "+ Superset";
  supersetBtn.onclick = () => openPicker(e.id);
  header.appendChild(supersetBtn);

  wrap.appendChild(header);

  const targets = document.createElement("div");
  targets.className = "targets";

  const setsLabel = document.createElement("label");
  setsLabel.textContent = "sets";
  const setsInput = document.createElement("input");
  setsInput.type = "number";
  setsInput.value = String(e.sets);
  setsInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} sets`);
  setsInput.onblur = () => {
    const value = Number(setsInput.value);
    if (!value || value === e.sets) return;
    void callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "update_exercise",
      template_exercise_id: e.id,
      sets: value,
    });
  };
  setsLabel.appendChild(setsInput);

  const targetLabelEl = document.createElement("label");
  targetLabelEl.textContent = e.seconds != null ? "seconds" : "reps";
  const targetInput = document.createElement("input");
  targetInput.type = "number";
  targetInput.value = String(e.seconds ?? e.reps ?? "");
  targetInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} ${targetLabelEl.textContent}`);
  targetInput.onblur = () => {
    const value = Number(targetInput.value);
    if (!value) return;
    const field = e.seconds != null ? "seconds" : "reps";
    if (value === (e.seconds ?? e.reps)) return;
    void callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "update_exercise",
      template_exercise_id: e.id,
      [field]: value,
    });
  };
  targetLabelEl.appendChild(targetInput);

  const weightLabel = document.createElement("label");
  weightLabel.textContent = "lbs";
  const weightInput = document.createElement("input");
  weightInput.type = "number";
  weightInput.step = "5";
  weightInput.value = e.weight != null ? String(e.weight) : "";
  weightInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} weight`);
  weightInput.onblur = () => {
    if (weightInput.value === "") return;
    const value = Number(weightInput.value);
    if (value === e.weight) return;
    void callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "update_exercise",
      template_exercise_id: e.id,
      weight: value,
    });
  };
  weightLabel.appendChild(weightInput);

  targets.append(setsLabel, targetLabelEl, weightLabel);
  wrap.appendChild(targets);

  const notesInput = document.createElement("input");
  notesInput.type = "text";
  notesInput.className = "notes-input";
  notesInput.placeholder = "Notes";
  notesInput.value = e.notes ?? "";
  notesInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} notes`);
  notesInput.onblur = () => {
    if (notesInput.value === (e.notes ?? "")) return;
    void callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "update_exercise",
      template_exercise_id: e.id,
      notes: notesInput.value,
    });
  };
  wrap.appendChild(notesInput);

  return wrap;
}

function renderGroup(g: Group): HTMLDivElement {
  const isOpen = openGroups.has(g.key);
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
  const targetsSummary = document.createElement("span");
  targetsSummary.className = "muted";
  targetsSummary.style.marginLeft = "auto";
  targetsSummary.textContent = g.exercises.map((e) => `${e.sets}×${targetLabel(e)}`).join(", ");
  toggle.appendChild(targetsSummary);
  toggle.onclick = () => {
    if (openGroups.has(g.key)) openGroups.delete(g.key);
    else openGroups.add(g.key);
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
    body.appendChild(renderExercise(e));
  });
  wrap.appendChild(body);

  return wrap;
}

function render(payload: TemplatePayload): void {
  currentPayload = payload;
  statusEl.textContent = `${payload.name} — ${payload.exercises.length} exercise${payload.exercises.length === 1 ? "" : "s"}`;
  statusEl.className = "muted";
  templateEl.hidden = false;
  closePicker();

  if (document.activeElement !== nameInputEl) nameInputEl.value = payload.name;

  const groups = groupExercises(payload.exercises);
  const firstGroup = groups[0];
  if (!hasSetDefaultOpenGroup && firstGroup) {
    openGroups.add(firstGroup.key);
    hasSetDefaultOpenGroup = true;
  }
  groupsEl.replaceChildren(...groups.map(renderGroup));
}

async function loadCatalog(): Promise<void> {
  const result = await app.callServerTool({ name: "list_exercise_catalog", arguments: {} });
  const structured = result.structuredContent as { exercises: CatalogExercise[] } | undefined;
  exerciseCatalog = structured?.exercises ?? [];
  buildFilterChips();
}

/** One chip group (Category or Equipment): an "All" chip plus one chip per
 *  distinct value actually present in the catalog. Clicking the active chip (or
 *  "All") clears that group's filter back to "All". */
function buildChipGroup(
  container: HTMLElement,
  options: string[],
  get: () => string | null,
  set: (value: string | null) => void,
): void {
  const allBtn = document.createElement("button");
  allBtn.type = "button";
  allBtn.className = "chip";
  allBtn.textContent = "All";
  allBtn.onclick = () => {
    set(null);
    refreshFilterUI();
  };
  const chips = [allBtn];
  for (const opt of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = opt;
    btn.onclick = () => {
      set(get() === opt ? null : opt);
      refreshFilterUI();
    };
    chips.push(btn);
  }
  container.replaceChildren(...chips);
}

function buildFilterChips(): void {
  const catalog = exerciseCatalog ?? [];
  const categories = [...new Set(catalog.map((ex) => ex.muscle_group))].sort();
  const equipment = [
    ...new Set(catalog.map((ex) => ex.equipment ?? UNSPECIFIED_EQUIPMENT)),
  ].sort();
  buildChipGroup(
    pickerCategoryChipsEl,
    categories,
    () => selectedCategory,
    (v) => (selectedCategory = v),
  );
  buildChipGroup(
    pickerEquipmentChipsEl,
    equipment,
    () => selectedEquipment,
    (v) => (selectedEquipment = v),
  );
  refreshFilterUI();
}

function refreshFilterUI(): void {
  for (const btn of Array.from(pickerCategoryChipsEl.children) as HTMLButtonElement[]) {
    const active = btn.textContent === "All" ? selectedCategory === null : btn.textContent === selectedCategory;
    btn.setAttribute("aria-pressed", String(active));
  }
  for (const btn of Array.from(pickerEquipmentChipsEl.children) as HTMLButtonElement[]) {
    const active = btn.textContent === "All" ? selectedEquipment === null : btn.textContent === selectedEquipment;
    btn.setAttribute("aria-pressed", String(active));
  }
  const activeCount = (selectedCategory !== null ? 1 : 0) + (selectedEquipment !== null ? 1 : 0);
  pickerFilterBadgeEl.hidden = activeCount === 0;
  pickerFilterBadgeEl.textContent = String(activeCount);
  renderPickerList();
}

function matchesFilters(ex: CatalogExercise, query: string): boolean {
  if (!ex.name.toLowerCase().includes(query)) return false;
  if (selectedCategory !== null && ex.muscle_group !== selectedCategory) return false;
  if (selectedEquipment !== null) {
    const equipmentMatches =
      selectedEquipment === UNSPECIFIED_EQUIPMENT
        ? ex.equipment === null
        : ex.equipment === selectedEquipment;
    if (!equipmentMatches) return false;
  }
  return true;
}

function renderPickerList(): void {
  const q = pickerFilterEl.value.trim().toLowerCase();
  const matches = (exerciseCatalog ?? []).filter((ex) => matchesFilters(ex, q));
  // Grouping by category header is redundant once a category chip narrows the
  // list to one category already.
  const grouped = selectedCategory === null;

  const items: HTMLElement[] = [];
  let lastGroup: string | null = null;
  for (const ex of matches) {
    if (grouped && ex.muscle_group !== lastGroup) {
      const label = document.createElement("li");
      label.className = "picker-group-label";
      label.textContent = ex.muscle_group;
      items.push(label);
      lastGroup = ex.muscle_group;
    }
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = ex.name;
    btn.onclick = () => {
      const supersetWith = pickerSupersetWith;
      closePicker();
      void callAndRender("update_workout_template", {
        template_id: currentPayload?.id,
        action: "add_exercise",
        exercise: ex.name,
        sets: 3,
        reps: 10,
        ...(supersetWith ? { superset_with: supersetWith } : {}),
      });
    };
    li.appendChild(btn);
    items.push(li);
  }
  pickerListEl.replaceChildren(...items);
}

function openPicker(supersetWith: string | null): void {
  pickerSupersetWith = supersetWith;
  pickerEl.hidden = false;
  pickerFilterEl.value = "";
  if (exerciseCatalog) renderPickerList();
  else void loadCatalog().then(() => renderPickerList());
}

function closePicker(): void {
  pickerEl.hidden = true;
  pickerDrawerEl.hidden = true;
  pickerFilterToggleEl.setAttribute("aria-expanded", "false");
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
    const text = result.content?.find((c) => c.type === "text")?.text;
    if (text) statusEl.textContent = text;
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

nameInputEl.onblur = () => {
  if (!currentPayload || nameInputEl.value.trim() === "" || nameInputEl.value === currentPayload.name) return;
  void callAndRender("update_workout_template", {
    template_id: currentPayload.id,
    action: "rename",
    name: nameInputEl.value,
  });
};
addExerciseBtn.onclick = () => openPicker(null);
pickerFilterEl.oninput = () => renderPickerList();
pickerFilterToggleEl.onclick = () => {
  pickerDrawerEl.hidden = !pickerDrawerEl.hidden;
  pickerFilterToggleEl.setAttribute("aria-expanded", String(!pickerDrawerEl.hidden));
};
pickerCancelEl.onclick = () => closePicker();
archiveBtn.onclick = () => {
  if (!currentPayload) return;
  const id = currentPayload.id;
  void app
    .callServerTool({ name: "archive_workout_template", arguments: { template_id: id } })
    .then(() => {
      statusEl.textContent = "Archived.";
      templateEl.hidden = true;
    })
    .catch((err: unknown) => {
      statusEl.textContent = "Something went wrong talking to the server.";
      statusEl.className = "error";
      console.error(err);
    });
};

// The host pushes the originating tool's result once on render.
app.ontoolresult = (result) => {
  const payload = extractPayload(result);
  if (payload) render(payload);
  else statusEl.textContent = "Waiting for data…";
};

await app.connect();
statusEl.textContent = "Loading…";
