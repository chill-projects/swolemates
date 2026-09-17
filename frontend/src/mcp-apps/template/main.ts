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
 *
 * Field edits are batched: they collect in `drafts` and go out together when the
 * user hits Save. Structural edits (add, remove, reorder, superset) still apply
 * immediately — they change the shape of the list you're looking at, so deferring
 * them would be stranger than not. See drafts.ts for why the batching exists.
 */

import { App } from "@modelcontextprotocol/ext-apps";

import {
  type DraftField,
  type Drafts,
  type NumericField,
  NO_DRAFTS,
  clearEdit,
  describeDirty,
  dirtyFieldCount,
  draftIssues,
  effectiveValue,
  fieldIssue,
  parseNumberField,
  pendingEdits,
  stageEdit,
} from "./drafts";

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
const saveBarEl = $<HTMLDivElement>("save-bar");
const dirtyCountEl = $<HTMLSpanElement>("dirty-count");
const saveBtn = $<HTMLButtonElement>("save-btn");
const discardBtn = $<HTMLButtonElement>("discard-btn");

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
// Unsaved field edits, and the unsaved name. Both survive a re-render (the inputs
// read through `effectiveValue`), and both are cleared only by a successful save
// or an explicit discard.
let drafts: Drafts = NO_DRAFTS;
let nameDraft: string | null = null;
// Collapsed group headers show a "3×10 reps" summary. Kept as live element
// references so an in-progress edit can update them without a re-render — which
// would yank focus out of the box being typed in.
let groupSummaries: { el: HTMLElement; group: Group }[] = [];

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

/** The "10 reps" / "45s" half of a group summary, read through any pending edit so
 *  a collapsed header doesn't contradict the box you just typed in. */
function targetLabel(e: TemplateExercise): string {
  const field: NumericField = e.seconds != null ? "seconds" : "reps";
  const value = effectiveValue(drafts, e.id, field, e) ?? "?";
  return field === "seconds" ? `${value}s` : `${value} reps`;
}

function summaryFor(g: Group): string {
  return g.exercises
    .map((e) => `${effectiveValue(drafts, e.id, "sets", e) ?? e.sets}×${targetLabel(e)}`)
    .join(", ");
}

/** Outline an input that holds an unsaved value, and flag it red when that value
 *  can't be saved (0 sets, half a rep) with the reason in its tooltip. */
function markField(input: HTMLInputElement, id: string, field: DraftField): void {
  const entry = drafts.get(id);
  const staged = entry !== undefined && field in entry;
  const issue = staged ? fieldIssue(field, entry[field] as number | string) : null;
  input.classList.toggle("dirty", staged);
  input.classList.toggle("invalid", issue !== null);
  input.title = issue ?? "";
}

/** One editable number box. Edits land in `drafts` on input rather than on blur:
 *  waiting for blur is what made tabbing between two boxes fire two saves. */
function numberField(e: TemplateExercise, field: NumericField, labelText: string): HTMLLabelElement {
  const label = document.createElement("label");
  label.textContent = labelText;
  const input = document.createElement("input");
  input.type = "number";
  if (field === "weight") input.step = "5";
  const current = effectiveValue(drafts, e.id, field, e);
  input.value = current == null ? "" : String(current);
  input.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} ${labelText}`);
  input.oninput = () => {
    const parsed = parseNumberField(input.value);
    // Blank un-stages rather than staging a null: `update_exercise` reads a missing
    // field as "leave it alone", so there is no way to spell "clear this" — and
    // emptying a box mid-retype shouldn't count as an edit either way.
    drafts =
      parsed === null
        ? clearEdit(drafts, e.id, field)
        : stageEdit(drafts, e.id, field, parsed, e);
    markField(input, e.id, field);
    refreshDirtyUI();
  };
  markField(input, e.id, field);
  label.appendChild(input);
  return label;
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
    void withPendingSaved(() =>
      callAndRender("update_workout_template", {
        template_id: currentPayload?.id,
        action: "remove_exercise",
        template_exercise_id: e.id,
      }),
    );
  header.appendChild(removeBtn);

  const supersetBtn = document.createElement("button");
  supersetBtn.type = "button";
  supersetBtn.textContent = "+ Superset";
  supersetBtn.onclick = () => openPicker(e.id);
  header.appendChild(supersetBtn);

  wrap.appendChild(header);

  const targets = document.createElement("div");
  targets.className = "targets";
  targets.append(
    numberField(e, "sets", "sets"),
    numberField(e, e.seconds != null ? "seconds" : "reps", e.seconds != null ? "seconds" : "reps"),
    numberField(e, "weight", "lbs"),
  );
  wrap.appendChild(targets);

  const notesInput = document.createElement("input");
  notesInput.type = "text";
  notesInput.className = "notes-input";
  notesInput.placeholder = "Notes";
  notesInput.value = String(effectiveValue(drafts, e.id, "notes", e) ?? "");
  notesInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} notes`);
  notesInput.oninput = () => {
    drafts = stageEdit(drafts, e.id, "notes", notesInput.value, e);
    markField(notesInput, e.id, "notes");
    refreshDirtyUI();
  };
  markField(notesInput, e.id, "notes");
  wrap.appendChild(notesInput);

  return wrap;
}

/** Moves a whole group (a superset's exercises stay together) one slot up/down
 *  in the template, by rebuilding the full template_exercise_id order backend's
 *  reorder_exercises expects from the groups' current arrangement. */
function moveGroup(groups: Group[], index: number, direction: -1 | 1): void {
  const targetIndex = index + direction;
  if (targetIndex < 0 || targetIndex >= groups.length) return;
  const reordered = [...groups];
  const [moved] = reordered.splice(index, 1);
  if (!moved) return;
  reordered.splice(targetIndex, 0, moved);
  void withPendingSaved(() =>
    callAndRender("update_workout_template", {
      template_id: currentPayload?.id,
      action: "reorder_exercises",
      order: reordered.flatMap((group) => group.exercises.map((e) => e.id)),
    }),
  );
}

function renderGroup(g: Group, index: number, groups: Group[]): HTMLDivElement {
  const isOpen = openGroups.has(g.key);
  const title = g.exercises.map((e) => e.exercise_name ?? "Exercise").join(" + ");

  const wrap = document.createElement("div");
  wrap.className = "group";

  const headerRow = document.createElement("div");
  headerRow.className = "group-header";

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
  targetsSummary.className = "group-summary";
  targetsSummary.style.marginLeft = "auto";
  targetsSummary.textContent = summaryFor(g);
  groupSummaries.push({ el: targetsSummary, group: g });
  toggle.appendChild(targetsSummary);
  toggle.onclick = () => {
    if (openGroups.has(g.key)) openGroups.delete(g.key);
    else openGroups.add(g.key);
    if (currentPayload) render(currentPayload);
  };
  headerRow.appendChild(toggle);

  const upBtn = document.createElement("button");
  upBtn.type = "button";
  upBtn.className = "move-btn";
  upBtn.title = "Move up";
  upBtn.setAttribute("aria-label", `Move ${title} up`);
  upBtn.textContent = "↑";
  upBtn.disabled = index === 0;
  upBtn.onclick = () => moveGroup(groups, index, -1);
  headerRow.appendChild(upBtn);

  const downBtn = document.createElement("button");
  downBtn.type = "button";
  downBtn.className = "move-btn";
  downBtn.title = "Move down";
  downBtn.setAttribute("aria-label", `Move ${title} down`);
  downBtn.textContent = "↓";
  downBtn.disabled = index === groups.length - 1;
  downBtn.onclick = () => moveGroup(groups, index, 1);
  headerRow.appendChild(downBtn);

  wrap.appendChild(headerRow);

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

  if (document.activeElement !== nameInputEl) nameInputEl.value = nameDraft ?? payload.name;

  const groups = groupExercises(payload.exercises);
  const firstGroup = groups[0];
  if (!hasSetDefaultOpenGroup && firstGroup) {
    openGroups.add(firstGroup.key);
    hasSetDefaultOpenGroup = true;
  }
  groupSummaries = [];
  groupsEl.replaceChildren(...groups.map((g, i) => renderGroup(g, i, groups)));
  refreshDirtyUI();
}

/** Everything that reflects unsaved state, updated without rebuilding the list —
 *  this runs on every keystroke, and a re-render would take focus with it. */
function refreshDirtyUI(): void {
  const count = dirtyFieldCount(drafts, nameDraft !== null);
  const issues = draftIssues(drafts);
  saveBarEl.hidden = count === 0;
  saveBtn.disabled = issues.length > 0;
  dirtyCountEl.textContent = issues[0]
    ? `${issues[0].field} ${issues[0].message}`
    : describeDirty(count);
  dirtyCountEl.className = issues.length > 0 ? "error" : "muted";
  for (const { el, group } of groupSummaries) el.textContent = summaryFor(group);
}

/**
 * Push every pending edit, then re-render once from what came back.
 *
 * One call per edited exercise, because `update_exercise` is a one-row action —
 * but the render is the thing that used to be per-field, and now it happens once
 * at the end. Returns false if nothing was sent, so callers waiting on a clean
 * slate know not to continue.
 */
async function saveAll(): Promise<boolean> {
  if (!currentPayload || draftIssues(drafts).length > 0) return false;
  const templateId = currentPayload.id;
  const edits = pendingEdits(drafts);
  const rename = nameDraft;
  if (edits.length === 0 && rename === null) return true;

  const calls: Record<string, unknown>[] = [];
  if (rename !== null) {
    calls.push({ template_id: templateId, action: "rename", name: rename });
  }
  for (const edit of edits) {
    calls.push({
      template_id: templateId,
      action: "update_exercise",
      template_exercise_id: edit.template_exercise_id,
      ...edit.fields,
    });
  }

  saveBtn.disabled = true;
  saveBtn.textContent = "Saving…";
  let latest: TemplatePayload | null = null;
  try {
    for (const args of calls) {
      const result = await app.callServerTool({ name: "update_workout_template", arguments: args });
      latest = extractPayload(result) ?? latest;
    }
  } catch (err) {
    console.error(err);
    // Part of the batch may already have landed. Re-read instead of guessing, so
    // what's on screen is what's in the database and the user can see which of
    // their edits still need making.
    drafts = NO_DRAFTS;
    nameDraft = null;
    await callAndRender("get_workout_template", { template_id: templateId });
    statusEl.textContent = "Couldn't save everything — reloaded from the server.";
    statusEl.className = "error";
    return false;
  } finally {
    saveBtn.textContent = "Save changes";
    saveBtn.disabled = false;
  }

  drafts = NO_DRAFTS;
  nameDraft = null;
  // Every update_workout_template returns the whole template, so the last reply is
  // already the fresh truth — one render for the batch. The re-read is only for a
  // host that answered in plain text and gave us nothing to render.
  if (latest) render(latest);
  else await callAndRender("get_workout_template", { template_id: templateId });
  return true;
}

/** Structural edits rebuild the list from the server's answer, which would throw
 *  away anything still pending — so those go out first. */
async function withPendingSaved(run: () => Promise<void>): Promise<void> {
  if (dirtyFieldCount(drafts, nameDraft !== null) > 0 && !(await saveAll())) return;
  await run();
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
      void withPendingSaved(() =>
        callAndRender("update_workout_template", {
          template_id: currentPayload?.id,
          action: "add_exercise",
          exercise: ex.name,
          sets: 3,
          reps: 10,
          ...(supersetWith ? { superset_with: supersetWith } : {}),
        }),
      );
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

nameInputEl.oninput = () => {
  const value = nameInputEl.value;
  // A blank name is a rename the server would reject, so it reads as "not changed
  // yet" rather than as a pending edit — same guard the old on-blur save had.
  nameDraft =
    !currentPayload || value.trim() === "" || value === currentPayload.name ? null : value;
  refreshDirtyUI();
};

saveBtn.onclick = () => void saveAll();
discardBtn.onclick = () => {
  drafts = NO_DRAFTS;
  nameDraft = null;
  if (currentPayload) render(currentPayload);
};

// Enter and ⌘/Ctrl-S both save, so finishing an edit near the bottom of a long
// template doesn't mean scrolling to find the button.
document.addEventListener("keydown", (event) => {
  const chord = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s";
  const enterInField =
    event.key === "Enter" &&
    document.activeElement instanceof HTMLInputElement &&
    document.activeElement !== pickerFilterEl;
  if (!chord && !enterInField) return;
  event.preventDefault();
  void saveAll();
});

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
