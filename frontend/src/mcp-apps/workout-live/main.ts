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

interface Target {
  sets: number;
  reps: number | null;
  seconds: number | null;
  weight: number | null;
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
  target: Target | null;
}

interface Group {
  superset_group: number | null;
  is_superset: boolean;
  exercises: ExerciseEntry[];
}

interface Celebration {
  exercise_name: string;
  kind: "weight" | "e1rm";
  value: number;
  previous: number | null;
}

interface Streak {
  weeks: number;
  this_week: number;
  target: number;
}

interface MuscleCoverage {
  muscle: string;
  level: "none" | "light" | "moderate" | "heavy";
}

interface LivePayload {
  active: boolean;
  id?: string;
  completed_at?: string | null;
  groups?: Group[];
  summary: string;
  celebrations?: Celebration[];
  streak?: Streak | null;
  muscle_coverage?: MuscleCoverage[];
}

interface CatalogExercise {
  id: string;
  name: string;
  muscle_group: string;
  equipment: string | null;
}

const UNSPECIFIED_EQUIPMENT = "Unspecified";

// lucide "rotate-cw" — same source/style as the nav icons in components/icons.tsx.
const REDO_SET_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M23 4v6h-6"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>';

// lucide "x" — same style as the redo icon above.
const DELETE_SET_ICON =
  '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
  'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
  '<path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';

// Curated, not freeform: a known activity type is what lets a future calorie
// estimate look up a MET value. "Other" still escapes to free text below.
const ACTIVITY_TYPES = ["Hiking", "Yoga", "Pilates", "Zumba", "Running", "Cycling", "Swimming"];
const OTHER_ACTIVITY = "Other";

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const celebrationsEl = $<HTMLDivElement>("celebrations");
const streakLineEl = $<HTMLParagraphElement>("streak-line");
const muscleMapEl = $<HTMLDivElement>("muscle-map");
const emptyEl = $<HTMLDivElement>("empty");
const todayPlanBtn = $<HTMLButtonElement>("today-plan-btn");
const startBtn = $<HTMLButtonElement>("start-btn");
const todayPlanSectionEl = $<HTMLElement>("today-plan-section");
const todayPlanTitleEl = $<HTMLHeadingElement>("today-plan-title");
const todayPlanMetaEl = $<HTMLSpanElement>("today-plan-meta");
const todayPlanListEl = $<HTMLUListElement>("today-plan-list");
const templateListEl = $<HTMLUListElement>("template-list");
const templatesMetaEl = $<HTMLSpanElement>("templates-meta");
const activityFormEl = $<HTMLDivElement>("activity-form");
const activityTypeChipsEl = $<HTMLDivElement>("activity-type-chips");
const activityTypeOtherEl = $<HTMLInputElement>("activity-type-other");
const activityDurationEl = $<HTMLInputElement>("activity-duration");
const activityNotesEl = $<HTMLInputElement>("activity-notes");
const activityLogBtn = $<HTMLButtonElement>("activity-log-btn");
const activityCancelBtn = $<HTMLButtonElement>("activity-cancel-btn");
const workoutEl = $<HTMLDivElement>("workout");
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
const finishBtn = $<HTMLButtonElement>("finish-btn");
const cancelBtn = $<HTMLButtonElement>("cancel-btn");
const backBtn = $<HTMLButtonElement>("back-btn");

// Open/collapsed accordion state and the exercise catalog cache both live outside
// render() so they survive the re-renders every tool call triggers.
const openGroups = new Set<string>();
// Only the very first render defaults a group open — `openGroups.size === 0` isn't
// a safe proxy for "first render," since collapsing the last open group also makes
// it 0 and would otherwise snap that group right back open.
let hasSetDefaultOpenGroup = false;
let currentPayload: LivePayload | null = null;
let exerciseCatalog: CatalogExercise[] | null = null;
// Set ids currently showing their inline "delete this set?" confirm, instead of
// the normal row — same local-only re-render trick as openGroups, no server round
// trip needed just to show/hide a confirm prompt.
const pendingDeleteSetIds = new Set<string>();
let pickerSupersetWith: string | null = null;
// null means "All" for both — persist across picker close/reopen (and across
// catalog reloads) so filtering to e.g. legs+dumbbell survives adding several
// exercises in a row.
let selectedCategory: string | null = null;
let selectedEquipment: string | null = null;
let selectedActivityType: string | null = null;
// Today's still-unstarted planned workout, if any — lets the empty state offer
// "start today's plan" alongside "start from scratch" instead of only the latter.
let todayPlanned: { id: string; template_name: string; exercise_names?: string[] } | null = null;
type TemplateSummary = { id: string; name: string; exercise_count: number; set_count: number };
let templateCatalog: TemplateSummary[] = [];

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

function formatTarget(t: Target): string {
  const perSet = t.seconds != null ? `${t.seconds}s` : `${t.reps ?? "?"} reps`;
  return t.weight != null ? `${t.sets}×${perSet} @ ${t.weight}lbs` : `${t.sets}×${perSet}`;
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

  if (e.target) {
    // The prescription reads as a chip beside the name, the way the mockup puts
    // "4 × 6 · 82.5" against the exercise you're on.
    const target = document.createElement("span");
    target.className = "target-chip";
    target.textContent = formatTarget(e.target);
    // After the name, not at the end — the header's trailing slots belong to the
    // remove and superset buttons.
    name.insertAdjacentElement("afterend", target);
  }

  if (e.last_time) {
    const lt = document.createElement("div");
    lt.className = "muted last-time";
    lt.textContent = `Last time: ${formatLastTime(e.last_time)}`;
    wrap.appendChild(lt);
  }

  // Built ahead of the sets list (though appended after it, same as before) so the
  // redo button on the most recent set can reach them to prefill a repeat set.
  let weightInput: HTMLInputElement | null = null;
  let mainInput: HTMLInputElement | null = null;
  let warmupInput: HTMLInputElement | null = null;
  let draft: HTMLDivElement | null = null;
  // A template can prescribe a timed exercise (target.seconds); ad-hoc exercises
  // stay reps-only in this draft row, same as before templates existed.
  const isTimed = e.target?.seconds != null;

  if (!finished) {
    draft = document.createElement("div");
    draft.className = "draft-set";
    const lastSet = e.last_time?.sets[e.last_time.sets.length - 1];

    weightInput = document.createElement("input");
    weightInput.type = "number";
    weightInput.step = "5";
    weightInput.placeholder = "lbs";
    weightInput.value =
      e.target?.weight != null
        ? String(e.target.weight)
        : lastSet?.weight != null
          ? String(lastSet.weight)
          : "";
    weightInput.setAttribute("aria-label", `${e.exercise_name ?? "Exercise"} weight`);

    mainInput = document.createElement("input");
    mainInput.type = "number";
    mainInput.placeholder = isTimed ? "seconds" : "reps";
    mainInput.value = isTimed
      ? e.target?.seconds != null
        ? String(e.target.seconds)
        : ""
      : e.target?.reps != null
        ? String(e.target.reps)
        : lastSet?.reps != null
          ? String(lastSet.reps)
          : "";
    mainInput.setAttribute(
      "aria-label",
      `${e.exercise_name ?? "Exercise"} ${isTimed ? "seconds" : "reps"}`,
    );

    const warmupLabel = document.createElement("label");
    warmupInput = document.createElement("input");
    warmupInput.type = "checkbox";
    warmupLabel.append(warmupInput, document.createTextNode(" warmup"));

    const logBtn = document.createElement("button");
    logBtn.type = "button";
    logBtn.className = "btn-primary";
    logBtn.textContent = "Log set";
    logBtn.onclick = () => {
      if (!weightInput || !mainInput || !warmupInput) return;
      if (mainInput.value === "") return;
      const weight = weightInput.value === "" ? undefined : Number(weightInput.value);
      void callAndRender("log_set", {
        exercise: e.exercise_name,
        weight,
        is_warmup: warmupInput.checked,
        ...(isTimed
          ? { set_type: "time", work_seconds: Number(mainInput.value) }
          : { reps: Number(mainInput.value) }),
      });
    };

    draft.append(weightInput, mainInput, warmupLabel, logBtn);
  }

  const list = document.createElement("ul");
  list.className = "logged-sets";
  const mostRecentIndex = e.sets.length - 1;
  list.replaceChildren(
    ...e.sets.map((s, i) => {
      const li = document.createElement("li");

      if (!finished && pendingDeleteSetIds.has(s.id)) {
        li.className = "set-delete-confirm";
        const text = document.createElement("span");
        text.textContent = "Delete this set?";
        const yesBtn = document.createElement("button");
        yesBtn.type = "button";
        yesBtn.textContent = "Delete";
        yesBtn.onclick = () => {
          pendingDeleteSetIds.delete(s.id);
          void callAndRender("update_workout_entry", {
            workout_id: currentPayload?.id,
            action: "delete_set",
            workout_set_id: s.id,
          });
        };
        const noBtn = document.createElement("button");
        noBtn.type = "button";
        noBtn.textContent = "Cancel";
        noBtn.onclick = () => {
          pendingDeleteSetIds.delete(s.id);
          if (currentPayload) render(currentPayload);
        };
        li.append(text, yesBtn, noBtn);
        return li;
      }

      const base =
        s.set_type === "time"
          ? `${s.work_seconds}s`
          : `${s.weight ?? "—"}lbs × ${s.reps}`;
      // Warmups get the dashed, dimmed pill; working sets the filled teal one —
      // the two set states the mockup distinguishes at a glance.
      if (s.is_warmup) li.className = "is-warmup";
      const label = document.createElement("span");
      label.textContent = s.is_warmup ? `${base} · warmup` : base;
      li.appendChild(label);

      if (!finished && i === mostRecentIndex && weightInput && mainInput && warmupInput) {
        const redoBtn = document.createElement("button");
        redoBtn.type = "button";
        redoBtn.className = "redo-set-btn";
        redoBtn.title = "Copy into the set inputs below";
        redoBtn.setAttribute("aria-label", "Copy this set into the inputs below");
        redoBtn.innerHTML = REDO_SET_ICON;
        redoBtn.onclick = () => {
          if (!weightInput || !mainInput || !warmupInput) return;
          weightInput.value = s.weight != null ? String(s.weight) : "";
          mainInput.value =
            s.set_type === "time"
              ? s.work_seconds != null
                ? String(s.work_seconds)
                : ""
              : s.reps != null
                ? String(s.reps)
                : "";
          warmupInput.checked = s.is_warmup;
          mainInput.focus();
        };
        li.appendChild(redoBtn);
      }

      if (!finished) {
        const deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "delete-set-btn";
        deleteBtn.title = "Delete this set";
        deleteBtn.setAttribute("aria-label", "Delete this set");
        deleteBtn.innerHTML = DELETE_SET_ICON;
        deleteBtn.onclick = () => {
          pendingDeleteSetIds.add(s.id);
          if (currentPayload) render(currentPayload);
        };
        li.appendChild(deleteBtn);
      }
      return li;
    }),
  );
  wrap.appendChild(list);

  if (draft) {
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

function renderCelebrations(celebrations: Celebration[] | undefined): void {
  if (!celebrations || celebrations.length === 0) {
    celebrationsEl.hidden = true;
    celebrationsEl.replaceChildren();
    return;
  }
  celebrationsEl.hidden = false;
  celebrationsEl.replaceChildren(
    ...celebrations.map((c) => {
      const div = document.createElement("div");
      div.className = "celebration";
      const tag = document.createElement("span");
      tag.className = "celebration-tag";
      tag.textContent = "PR";
      const label = c.kind === "e1rm" ? "e1RM" : "weight";
      const text = document.createElement("span");
      text.textContent =
        c.previous != null
          ? `${c.exercise_name} ${label} ${c.value}lbs — up from ${c.previous}`
          : `${c.exercise_name} ${label} ${c.value}lbs`;
      div.append(tag, text);
      return div;
    }),
  );
}

function renderStreak(streak: Streak | null | undefined): void {
  if (!streak) {
    streakLineEl.hidden = true;
    return;
  }
  streakLineEl.hidden = false;
  streakLineEl.textContent = `${streak.weeks}-week streak — ${streak.this_week}/${streak.target} this week`;
}

function renderMuscleMap(coverage: MuscleCoverage[] | undefined): void {
  const byMuscle = new Map((coverage ?? []).map((c) => [c.muscle, c.level]));
  // The backend's vocabulary has no "obliques" (free-exercise-db doesn't track it
  // separately from abdominals) — alias it to abs's level so the region reflects ab
  // work instead of sitting permanently at "none".
  const absLevel = byMuscle.get("abs");
  if (absLevel) byMuscle.set("obliques", absLevel);

  muscleMapEl.querySelectorAll<SVGGElement>("[data-muscle]").forEach((g) => {
    const muscle = g.dataset.muscle;
    g.dataset.level = (muscle && byMuscle.get(muscle)) || "none";
  });
}

function render(payload: LivePayload): void {
  currentPayload = payload;
  statusEl.textContent = payload.summary;
  statusEl.className = "muted";
  renderCelebrations(payload.celebrations);
  renderStreak(payload.streak);
  renderMuscleMap(payload.muscle_coverage);

  if (!payload.active) {
    emptyEl.hidden = false;
    workoutEl.hidden = true;
    updateStartButtons();
    renderTemplateList();
    void loadTodaysPlan();
    void loadTemplates();
    return;
  }
  emptyEl.hidden = true;
  workoutEl.hidden = false;
  closePicker();

  const finished = payload.completed_at != null;
  const groups = payload.groups ?? [];
  finishBtn.hidden = finished;
  addExerciseBtn.hidden = finished;
  // Cancel only offers to back out before anything's actually logged — once real
  // exercises are added, backing out goes through Finish (which keeps the data),
  // not a silent discard.
  cancelBtn.hidden = finished || groups.length > 0;
  backBtn.hidden = !finished;

  const firstGroup = groups[0];
  if (!hasSetDefaultOpenGroup && firstGroup) {
    openGroups.add(groupKey(firstGroup));
    hasSetDefaultOpenGroup = true;
  }
  groupsEl.replaceChildren(...groups.map((g) => renderGroup(g, finished)));
}

/** Reflects `todayPlanned` onto the idle screen: the plan card only exists when
 *  today has an unstarted planned entry, and whichever button is the obvious next
 *  move carries the coral fill while the other steps back. */
function updateStartButtons(): void {
  if (todayPlanned) {
    const planned = todayPlanned;
    todayPlanSectionEl.hidden = false;
    todayPlanTitleEl.textContent = `Today's plan · ${planned.template_name}`;
    const names = planned.exercise_names ?? [];
    todayPlanMetaEl.textContent = names.length
      ? `${names.length} exercise${names.length === 1 ? "" : "s"}`
      : "";
    todayPlanListEl.replaceChildren(
      ...names.map((name) => {
        const li = document.createElement("li");
        const main = document.createElement("div");
        main.className = "row-main";
        const label = document.createElement("div");
        label.className = "row-name";
        label.textContent = name;
        main.appendChild(label);
        li.appendChild(main);
        return li;
      }),
    );
    todayPlanBtn.textContent = `Start ${planned.template_name}`;
    todayPlanBtn.onclick = () => void callAndRender("start_workout", { planned_id: planned.id });
    startBtn.textContent = "Start empty workout";
    startBtn.className = "";
  } else {
    todayPlanSectionEl.hidden = true;
    startBtn.textContent = "Start empty workout";
    startBtn.className = "btn-primary";
  }
}

/** "Start something else" — every saved template with a one-tap start. */
function renderTemplateList(): void {
  templatesMetaEl.textContent = templateCatalog.length
    ? `${templateCatalog.length} template${templateCatalog.length === 1 ? "" : "s"}`
    : "";
  templateListEl.replaceChildren(
    ...(templateCatalog.length
      ? templateCatalog.map((t) => {
          const li = document.createElement("li");
          const main = document.createElement("div");
          main.className = "row-main";
          const name = document.createElement("div");
          name.className = "row-name";
          name.textContent = t.name;
          const detail = document.createElement("div");
          detail.className = "row-detail";
          detail.textContent = `${t.exercise_count} exercise${t.exercise_count === 1 ? "" : "s"}${
            t.set_count ? ` · ${t.set_count} sets` : ""
          }`;
          main.append(name, detail);
          const start = document.createElement("button");
          start.type = "button";
          start.className = "btn-outline";
          start.textContent = "Start";
          start.onclick = () => void callAndRender("start_workout", { template_id: t.id });
          li.append(main, start);
          return li;
        })
      : [
          Object.assign(document.createElement("li"), {
            className: "muted",
            textContent: "No templates saved yet.",
          }),
        ]),
  );
}

async function loadTodaysPlan(): Promise<void> {
  try {
    const result = await app.callServerTool({ name: "get_todays_plan", arguments: {} });
    const structured = result.structuredContent as
      | { planned?: { id: string; template_name: string } | null }
      | undefined;
    todayPlanned = structured?.planned ?? null;
  } catch {
    todayPlanned = null;
  }
  updateStartButtons();
}

/** The saved templates behind "Start something else". Failure is quiet — the idle
 *  screen still works without it, you just don't get the shortcuts. */
async function loadTemplates(): Promise<void> {
  try {
    const result = await app.callServerTool({ name: "list_templates_catalog", arguments: {} });
    const structured = result.structuredContent as { templates?: TemplateSummary[] } | undefined;
    templateCatalog = structured?.templates ?? [];
  } catch {
    templateCatalog = [];
  }
  renderTemplateList();
}

async function loadCatalog(): Promise<void> {
  const result = await app.callServerTool({ name: "list_workout_exercises", arguments: {} });
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
    // log_set's >90-minute clarification path returns plain text, not a payload.
    const text = result.content?.find((c) => c.type === "text")?.text;
    if (text) statusEl.textContent = text;
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
  }
}

function refreshActivityChips(): void {
  for (const btn of Array.from(activityTypeChipsEl.children) as HTMLButtonElement[]) {
    btn.setAttribute("aria-pressed", String(btn.textContent === selectedActivityType));
  }
  activityTypeOtherEl.hidden = selectedActivityType !== OTHER_ACTIVITY;
  if (selectedActivityType !== OTHER_ACTIVITY) activityTypeOtherEl.value = "";
}

function buildActivityTypeChips(): void {
  const chips = [...ACTIVITY_TYPES, OTHER_ACTIVITY].map((type) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "chip";
    btn.textContent = type;
    btn.onclick = () => {
      selectedActivityType = selectedActivityType === type ? null : type;
      // The chips are the entry point now — picking one reveals the minutes/notes
      // fields, deselecting puts them away again.
      activityFormEl.hidden = selectedActivityType === null;
      refreshActivityChips();
      if (selectedActivityType !== null) activityDurationEl.focus();
    };
    return btn;
  });
  activityTypeChipsEl.replaceChildren(...chips);
}
buildActivityTypeChips();

function resetActivityForm(): void {
  selectedActivityType = null;
  activityDurationEl.value = "";
  activityNotesEl.value = "";
  activityTypeOtherEl.value = "";
  refreshActivityChips();
}

function closeActivityForm(): void {
  activityFormEl.hidden = true;
  resetActivityForm();
}

startBtn.onclick = () => void callAndRender("start_workout", {});
activityCancelBtn.onclick = () => closeActivityForm();
activityLogBtn.onclick = () => {
  const activityType =
    selectedActivityType === OTHER_ACTIVITY
      ? activityTypeOtherEl.value.trim()
      : selectedActivityType;
  const durationMinutes = Number(activityDurationEl.value);
  if (!activityType) {
    statusEl.textContent = "Pick an activity (or enter one under Other).";
    statusEl.className = "error";
    return;
  }
  if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
    statusEl.textContent = "Enter how many minutes.";
    statusEl.className = "error";
    return;
  }
  const notes = activityNotesEl.value.trim();
  closeActivityForm();
  void callAndRender("log_activity", {
    activity_type: activityType,
    duration_minutes: durationMinutes,
    ...(notes ? { notes } : {}),
  });
};
addExerciseBtn.onclick = () => openPicker(null);
pickerFilterEl.oninput = () => renderPickerList();
pickerFilterToggleEl.onclick = () => {
  pickerDrawerEl.hidden = !pickerDrawerEl.hidden;
  pickerFilterToggleEl.setAttribute("aria-expanded", String(!pickerDrawerEl.hidden));
};
pickerCancelEl.onclick = () => closePicker();
finishBtn.onclick = () => {
  if (!currentPayload?.id) return;
  void callAndRender("finish_workout", { workout_id: currentPayload.id });
};
// There's no "discard" tool on the server — finishing with zero logged sets is
// the sanctioned way to end a session nothing was ever added to (the backend
// docstring says as much). What makes this feel like a true cancel rather than
// "workout logged" is skipping the completed-summary view: reset straight back
// to empty instead of rendering finish_workout's own (accurate, but unwanted
// here) "Workout complete — 0 sets logged" result.
cancelBtn.onclick = async () => {
  if (!currentPayload?.id) return;
  try {
    await app.callServerTool({
      name: "finish_workout",
      arguments: { workout_id: currentPayload.id },
    });
  } catch (err) {
    console.error(err);
  }
  render({ active: false, summary: "No active workout." });
};
backBtn.onclick = () => render({ active: false, summary: "No active workout." });

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
