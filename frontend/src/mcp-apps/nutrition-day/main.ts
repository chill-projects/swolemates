/**
 * The nutrition-day component. Renders in two hosts from this one bundle:
 *  - Claude, via the `ui://swolemates/nutrition-day.html` MCP resource
 *  - the SPA, via AppRenderer (an iframe + AppBridge backed by the REST API)
 *
 * Any tool call that changes today's totals (`log_nutrition`, `get_nutrition_day`,
 * `save_meal_template`, `log_meal_template`) returns this same payload shape, so the
 * component re-renders fully from whichever result the host pushes — no separate
 * fetch, same pattern as tmpx. `search_food_facts` is the one exception: it renders
 * into its own results list, not the day payload, and only feeds `log_nutrition` when
 * a result is picked.
 *
 * No delete-template button here: `delete_meal_template` is a REST-only action (the
 * resolved tool spec deliberately keeps chat delete-free), and this bundle runs
 * unchanged inside Claude — a button calling an unregistered tool would work in the
 * SPA and silently fail in Claude, so it's left out rather than shipped asymmetric.
 */

import { App } from "@modelcontextprotocol/ext-apps";
import { MEAL_TYPES, populateMealTypeSelect, renderMealTypeEdit } from "./mealType";

interface TrackableProgress {
  trackable_key: string;
  label: string;
  unit: string;
  consumed: number;
  target: number | null;
}

interface DayLogItem {
  id: string;
  name: string | null;
  values: Record<string, number>;
}

interface DayLogEntry {
  id: string;
  name: string | null;
  logged_at: string;
  meal_type: string | null;
  values: Record<string, number>;
  items: DayLogItem[];
}

interface FoodMatch {
  name: string;
  brand: string | null;
  // Every macro below is per 100g; serving_grams (when OFF reports a gram serving
  // size) is only a prefill hint for the grams input, not a unit the values are in.
  serving_grams: number | null;
  calories: number | null;
  protein_g: number | null;
  carbs_g: number | null;
  fat_g: number | null;
  fiber_g: number | null;
}

interface MealTemplateItem {
  id: string;
  name: string;
  serving_description: string | null;
  values: Record<string, number>;
}

const TRACKABLE_LABELS: Record<string, string> = {
  calories: "Calories",
  protein_g: "Protein (g)",
  carbs_g: "Carbs (g)",
  fat_g: "Fat (g)",
  fiber_g: "Fiber (g)",
};

interface MealTemplateSummary {
  id: string;
  name: string;
  default_meal_type: string | null;
  items: MealTemplateItem[];
  totals: Record<string, number>;
}

interface NutritionDayPayload {
  date: string;
  hero: TrackableProgress;
  bars: TrackableProgress[];
  streak_key: string | null;
  logs: DayLogEntry[];
  templates: MealTemplateSummary[];
  summary: string;
}

const RING_RADIUS = 52;
const RING_CIRCUMFERENCE = 2 * Math.PI * RING_RADIUS;

const $ = <T extends Element>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as unknown as T;
};

const statusEl = $<HTMLParagraphElement>("status");
const ringFillEl = $<SVGCircleElement>("ring-fill");
const ringValueEl = $<HTMLSpanElement>("ring-value");
const ringTargetEl = $<HTMLSpanElement>("ring-target");
const barsEl = $<HTMLDivElement>("bars");
const remainingGridEl = $<HTMLDivElement>("remaining-grid");
const remainingTipEl = $<HTMLDivElement>("remaining-tip");
const templatesEl = $<HTMLUListElement>("templates");
const templatesCountEl = $<HTMLSpanElement>("templates-count");
const dayHeroEl = $<HTMLDivElement>("day-hero");
const mealFilterEl = $<HTMLInputElement>("meal-filter");
const mealChipsEl = $<HTMLDivElement>("meal-chips");
const saveTemplateCountEl = $<HTMLSpanElement>("save-template-count");
const logsEl = $<HTMLUListElement>("logs");
const saveBarEl = $<HTMLDivElement>("save-template-bar");
const templateNameInput = $<HTMLInputElement>("template-name");
const saveTemplateMealTypeEl = $<HTMLSelectElement>("save-template-meal-type");
const saveTemplateBtn = $<HTMLButtonElement>("save-template-btn");
const foodSearchInput = $<HTMLInputElement>("food-search-input");
const foodSearchBtn = $<HTMLButtonElement>("food-search-btn");
const foodSearchResultsEl = $<HTMLUListElement>("food-search-results");

// Selection state for "save these as a template" — lives outside render() so it
// survives the re-renders every tool call triggers.
const selectedLogIds = new Set<string>();

// Saved-meals filters, kept outside render() for the same reason. `null` meal type
// means "All".
let mealTypeFilter: string | null = null;
let mealNameFilter = "";

// Static (unlike the per-result/per-log selects, which are built fresh every
// render), so it's populated once here rather than in render().
populateMealTypeSelect(saveTemplateMealTypeEl, { includeUnset: true });

// The last payload the host pushed, so a filter change can re-render from it
// without asking the server for the day again.
let currentPayload: NutritionDayPayload | null = null;

const app = new App({ name: "Swolemates Nutrition", version: "1.0.0" });

function extractPayload(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): NutritionDayPayload | null {
  const structured = result.structuredContent as NutritionDayPayload | undefined;
  if (structured && structured.hero) return structured;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as NutritionDayPayload;
    return parsed.hero ? parsed : null;
  } catch {
    return null;
  }
}

function extractMatches(result: {
  structuredContent?: unknown;
  content?: Array<{ type: string; text?: string }>;
}): FoodMatch[] {
  const structured = result.structuredContent as { matches?: FoodMatch[] } | undefined;
  if (structured?.matches) return structured.matches;
  const text = result.content?.find((c) => c.type === "text")?.text;
  if (!text) return [];
  try {
    const parsed = JSON.parse(text) as { matches?: FoodMatch[] };
    return parsed.matches ?? [];
  } catch {
    return [];
  }
}

// Matches DashboardPage.tsx's MACRO_COLORS — the per-day calendar tooltip and this
// view show the same four macros and should read as the same bars, not just similarly
// styled ones.
const MACRO_COLORS: Record<string, string> = {
  protein_g: "var(--teal)",
  carbs_g: "var(--gold)",
  fat_g: "var(--plum)",
  fiber_g: "var(--coral)",
};

function renderBar(progress: TrackableProgress): HTMLDivElement {
  const row = document.createElement("div");
  row.className = "bar-row";

  const top = document.createElement("div");
  top.className = "top";
  const label = document.createElement("span");
  label.textContent = progress.label;
  const amount = document.createElement("span");
  amount.className = "amount";
  amount.textContent = progress.target
    ? `${Math.round(progress.consumed)} / ${Math.round(progress.target)}${progress.unit}`
    : `${Math.round(progress.consumed)}${progress.unit}`;
  top.append(label, amount);

  const track = document.createElement("div");
  track.className = "bar-track";
  const fill = document.createElement("div");
  fill.className = "bar-fill";
  const pct = progress.target ? Math.min((progress.consumed / progress.target) * 100, 100) : 0;
  fill.style.width = `${pct}%`;
  fill.style.background = MACRO_COLORS[progress.trackable_key] ?? "var(--ring-fill)";
  track.appendChild(fill);

  row.append(top, track);
  return row;
}

function timeLabel(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** The macro summary under a log row. Falls back to the raw values so a log with
 *  no P/C/F (a weight entry, a calories-only quick add) still shows what it holds. */
function logDetail(values: Record<string, number>): string {
  const macros = macroLine(values);
  if (macros) return macros;
  return Object.entries(values)
    .filter(([key]) => key !== "calories")
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");
}

function macroLine(totals: Record<string, number>): string {
  const parts: string[] = [];
  if (totals.protein_g !== undefined) parts.push(`P ${Math.round(totals.protein_g)}g`);
  if (totals.carbs_g !== undefined) parts.push(`C ${Math.round(totals.carbs_g)}g`);
  if (totals.fat_g !== undefined) parts.push(`F ${Math.round(totals.fat_g)}g`);
  return parts.join(" · ");
}

// Generalizes legacy TodaySummary.tsx's "you have left today" card + protein-focused
// tip — but every macro's target is optional here (unlike the legacy version, which
// assumed a full targets object), so the tip falls back gracefully when protein or
// calories has no goal set yet.
function renderRemaining(payload: NutritionDayPayload): void {
  const items = [payload.hero, ...payload.bars];
  remainingGridEl.replaceChildren(
    ...items.map((p) => {
      const div = document.createElement("div");
      div.className = "remaining-item";
      const n = document.createElement("div");
      n.className = "n";
      const remaining = p.target !== null ? Math.max(p.target - p.consumed, 0) : null;
      n.textContent =
        remaining === null
          ? "—"
          : p.trackable_key === "calories"
            ? Math.round(remaining).toLocaleString()
            : `${Math.round(remaining)}${p.unit}`;
      // Calories carry the teal accent as the headline figure; a target already met
      // dims rather than shouting a zero.
      n.style.color =
        remaining === null || remaining === 0
          ? "var(--dim)"
          : p.trackable_key === "calories"
            ? "var(--teal)"
            : "var(--ink)";
      const l = document.createElement("div");
      l.className = "l";
      l.textContent = p.label;
      div.append(n, l);
      return div;
    }),
  );

  const protein = payload.bars.find((b) => b.trackable_key === "protein_g");
  let tip: string;
  if (payload.logs.length === 0) {
    tip = "<b>Nothing logged yet.</b> Log a meal to see today's picture.";
  } else if (protein?.target != null) {
    const remainingProtein = protein.target - protein.consumed;
    if (remainingProtein <= 0) {
      tip = "<b>Protein target hit.</b> Nice work today.";
    } else if (remainingProtein <= 25) {
      tip = `<b>Almost there on protein</b> — ${Math.round(remainingProtein)}g left.`;
    } else {
      tip = `<b>Protein still has room</b> — ${Math.round(remainingProtein)}g left.`;
    }
  } else if (payload.hero.target != null) {
    const remainingCal = payload.hero.target - payload.hero.consumed;
    tip =
      remainingCal <= 0
        ? "<b>Calorie target hit.</b> Nice work today."
        : `<b>Plenty of room left</b> — ${Math.round(remainingCal).toLocaleString()} ${payload.hero.unit} left today.`;
  } else {
    tip = "Set a calorie or protein goal to get suggestions here.";
  }
  remainingTipEl.innerHTML = tip;
}

function renderTemplateItem(templateId: string, item: MealTemplateItem): HTMLLIElement {
  const li = document.createElement("li");
  li.className = "template-item";

  const view = document.createElement("div");
  view.className = "template-item-view";
  const text = document.createElement("span");
  text.textContent = `${item.name} (${Math.round(item.values.calories ?? 0)} cal)`;
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.textContent = "Edit";
  view.append(text, editBtn);

  const form = document.createElement("div");
  form.className = "template-item-edit";
  form.hidden = true;

  const nameInput = document.createElement("input");
  nameInput.type = "text";
  nameInput.value = item.name;
  nameInput.setAttribute("aria-label", `${item.name} name`);

  const valuesRow = document.createElement("div");
  valuesRow.className = "template-item-values";
  const valueInputs: Record<string, HTMLInputElement> = {};
  for (const [key, value] of Object.entries(item.values)) {
    const label = document.createElement("label");
    label.textContent = TRACKABLE_LABELS[key] ?? key;
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.value = String(value);
    valueInputs[key] = input;
    label.appendChild(input);
    valuesRow.appendChild(label);
  }

  const editActions = document.createElement("div");
  editActions.className = "template-item-edit-actions";
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Save";
  saveBtn.onclick = () => {
    const values: Record<string, number> = {};
    for (const [key, input] of Object.entries(valueInputs)) values[key] = Number(input.value);
    void callAndRender("update_meal_template_item", {
      template_id: templateId,
      item_id: item.id,
      name: nameInput.value.trim() || item.name,
      values,
    });
  };
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.textContent = "Cancel";
  cancelBtn.onclick = () => {
    form.hidden = true;
    view.hidden = false;
  };
  editActions.append(saveBtn, cancelBtn);
  form.append(nameInput, valuesRow, editActions);

  editBtn.onclick = () => {
    view.hidden = true;
    form.hidden = false;
  };

  li.append(view, form);
  return li;
}

function renderTemplate(template: MealTemplateSummary): HTMLLIElement {
  const card = document.createElement("li");
  card.className = "template-row";

  const body = document.createElement("div");

  const name = document.createElement("span");
  name.className = "template-name";
  name.textContent = template.name;

  const total = document.createElement("span");
  total.className = "template-total";
  total.textContent = String(Math.round(template.totals.calories ?? 0));

  const macros = document.createElement("div");
  macros.className = "template-macros";
  const itemCount = `${template.items.length} item${template.items.length === 1 ? "" : "s"}`;
  const macroText = macroLine(template.totals);
  macros.textContent = macroText ? `${macroText} · ${itemCount}` : itemCount;

  const itemsList = document.createElement("ul");
  itemsList.className = "template-items";
  itemsList.hidden = true;
  itemsList.replaceChildren(
    ...template.items.map((item) => renderTemplateItem(template.id, item)),
  );

  const actions = document.createElement("div");
  actions.className = "template-actions";
  const logBtn = document.createElement("button");
  logBtn.type = "button";
  logBtn.className = "btn-outline";
  logBtn.textContent = "Log";
  logBtn.onclick = () => void callAndRender("log_meal_template", { template_id: template.id });
  const itemsBtn = document.createElement("button");
  itemsBtn.type = "button";
  itemsBtn.textContent = "Items";
  itemsBtn.onclick = () => {
    itemsList.hidden = !itemsList.hidden;
  };
  actions.append(logBtn, itemsBtn);

  // Name and meal-type picker on the left, the calorie figure and the two actions
  // hard right — the saved-meal row from the mockup, with the chip now editable:
  // this is what the meal-type filter chips above the list actually filter on.
  const top = document.createElement("div");
  top.className = "template-top";
  const mealTypeSelect = renderMealTypeEdit(
    { label: template.name, mealType: template.default_meal_type, allowUnset: true },
    (mealType) =>
      void callAndRender("update_meal_template", {
        template_id: template.id,
        default_meal_type: mealType,
      }),
  );
  const spacer = document.createElement("span");
  spacer.className = "log-spacer";
  top.append(name, mealTypeSelect, spacer, total, actions);

  body.append(top, macros, itemsList);

  // Delete lives behind a confirm step, in the card itself rather than a separate
  // management list — deleting a saved template is unrecoverable (no undo), so a
  // stray tap on a small × shouldn't be enough on its own.
  const confirm = document.createElement("div");
  confirm.className = "template-delete-confirm";
  confirm.hidden = true;
  const confirmText = document.createElement("p");
  confirmText.className = "muted";
  confirmText.textContent = `Delete "${template.name}"? This can't be undone.`;
  const confirmActions = document.createElement("div");
  confirmActions.className = "template-delete-confirm-actions";
  const confirmDeleteBtn = document.createElement("button");
  confirmDeleteBtn.type = "button";
  confirmDeleteBtn.className = "template-delete-confirm-btn";
  confirmDeleteBtn.textContent = "Delete";
  confirmDeleteBtn.onclick = () =>
    void callAndRender("delete_meal_template", { template_id: template.id });
  const cancelDeleteBtn = document.createElement("button");
  cancelDeleteBtn.type = "button";
  cancelDeleteBtn.textContent = "Cancel";
  cancelDeleteBtn.onclick = () => {
    confirm.hidden = true;
    body.hidden = false;
  };
  confirmActions.append(confirmDeleteBtn, cancelDeleteBtn);
  confirm.append(confirmText, confirmActions);

  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "template-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete template";
  deleteBtn.setAttribute("aria-label", `Delete ${template.name}`);
  deleteBtn.onclick = () => {
    body.hidden = true;
    confirm.hidden = false;
  };

  card.append(deleteBtn, body, confirm);
  return card;
}

function updateSaveBar(): void {
  saveBarEl.hidden = selectedLogIds.size === 0;
  const n = selectedLogIds.size;
  saveTemplateCountEl.textContent = `${n} ${n === 1 ? "entry" : "entries"} selected`;
}

/** Name box + meal-type chips over the saved-meals list. Counts come from the
 *  unfiltered set, so a chip still tells you what's behind it while a filter is on. */
function renderMealFilters(templates: MealTemplateSummary[]): void {
  const countFor = (meal: string | null) =>
    meal === null
      ? templates.length
      : templates.filter((t) => (t.default_meal_type ?? "").toLowerCase() === meal).length;

  const chip = (label: string, meal: string | null) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "meal-chip";
    btn.setAttribute("aria-pressed", String(mealTypeFilter === meal));
    const text = document.createElement("span");
    text.textContent = label;
    const n = document.createElement("span");
    n.className = "n";
    n.textContent = String(countFor(meal));
    btn.append(text, n);
    btn.onclick = () => {
      mealTypeFilter = mealTypeFilter === meal ? null : meal;
      if (currentPayload) render(currentPayload);
    };
    return btn;
  };

  mealChipsEl.replaceChildren(
    chip("All", null),
    // Only offer a meal type that something is actually filed under.
    ...MEAL_TYPES.filter((m) => countFor(m) > 0).map((m) => chip(m, m)),
  );
}

function visibleTemplates(templates: MealTemplateSummary[]): MealTemplateSummary[] {
  const needle = mealNameFilter.trim().toLowerCase();
  return templates.filter((t) => {
    if (mealTypeFilter && (t.default_meal_type ?? "").toLowerCase() !== mealTypeFilter) return false;
    return needle === "" || t.name.toLowerCase().includes(needle);
  });
}

function renderGroupedLog(log: DayLogEntry): HTMLLIElement {
  const li = document.createElement("li");
  li.className = "grouped-log log-entry";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "group-toggle";
  const arrow = document.createElement("span");
  arrow.textContent = "▸ ";
  const label = document.createElement("span");
  label.textContent = log.name ?? "Meal";
  toggle.append(arrow, label);

  const kcal = document.createElement("span");
  kcal.className = "log-kcal";
  kcal.textContent = String(Math.round(log.values.calories ?? 0));

  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = timeLabel(log.logged_at);

  const spacer = document.createElement("span");
  spacer.className = "log-spacer";

  const header = document.createElement("div");
  header.className = "log-top log-name";
  const mealTypeSelect = renderMealTypeEdit(
    { label: log.name ?? "entry", mealType: log.meal_type, allowUnset: false },
    (mealType) =>
      void callAndRender("update_nutrition_log", { log_id: log.id, meal_type: mealType }),
  );
  header.append(toggle, mealTypeSelect, time, spacer, kcal);

  const values = document.createElement("div");
  values.className = "log-values";
  const count = `${log.items.length} item${log.items.length === 1 ? "" : "s"}`;
  const detail = logDetail(log.values);
  values.textContent = detail ? `${detail} · ${count}` : count;

  const items = document.createElement("ul");
  items.className = "grouped-log-items";
  items.hidden = true;
  items.replaceChildren(
    ...log.items.map((item) => {
      const itemLi = document.createElement("li");
      itemLi.textContent =
        `${item.name ?? "Item"}: ` +
        Object.entries(item.values)
          .map(([key, value]) => `${key}=${value}`)
          .join(", ");
      return itemLi;
    }),
  );
  toggle.onclick = () => {
    items.hidden = !items.hidden;
    arrow.textContent = items.hidden ? "▸ " : "▾ ";
  };

  const body = document.createElement("div");
  body.append(header, values, items);

  const confirm = renderDeleteLogControl(log, body);
  const deleteBtn = renderDeleteLogBtn(log, body, confirm);

  li.append(deleteBtn, body, confirm);
  return li;
}

function renderDeleteLogControl(log: DayLogEntry, body: HTMLElement): HTMLDivElement {
  // Same confirm-behind-a-small-× pattern as the meal template card — deleting a
  // logged entry is unrecoverable, so a stray tap shouldn't be enough on its own.
  const confirm = document.createElement("div");
  confirm.className = "log-delete-confirm";
  confirm.hidden = true;
  const confirmText = document.createElement("p");
  confirmText.className = "muted";
  confirmText.textContent = `Delete "${log.name ?? "this entry"}"? This can't be undone.`;
  const confirmActions = document.createElement("div");
  confirmActions.className = "log-delete-confirm-actions";
  const confirmDeleteBtn = document.createElement("button");
  confirmDeleteBtn.type = "button";
  confirmDeleteBtn.textContent = "Delete";
  confirmDeleteBtn.onclick = () => void callAndRender("delete_nutrition_log", { log_id: log.id });
  const cancelDeleteBtn = document.createElement("button");
  cancelDeleteBtn.type = "button";
  cancelDeleteBtn.textContent = "Cancel";
  cancelDeleteBtn.onclick = () => {
    confirm.hidden = true;
    body.hidden = false;
  };
  confirmActions.append(confirmDeleteBtn, cancelDeleteBtn);
  confirm.append(confirmText, confirmActions);
  return confirm;
}

function renderDeleteLogBtn(log: DayLogEntry, body: HTMLElement, confirm: HTMLElement): HTMLButtonElement {
  const deleteBtn = document.createElement("button");
  deleteBtn.type = "button";
  deleteBtn.className = "log-delete-btn";
  deleteBtn.textContent = "×";
  deleteBtn.title = "Delete entry";
  deleteBtn.setAttribute("aria-label", `Delete ${log.name ?? "entry"}`);
  deleteBtn.onclick = () => {
    body.hidden = true;
    confirm.hidden = false;
  };
  return deleteBtn;
}

function renderLog(log: DayLogEntry): HTMLLIElement {
  if (log.items.length > 0) return renderGroupedLog(log);

  const li = document.createElement("li");
  li.className = "log-entry";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.className = "log-select";
  checkbox.checked = selectedLogIds.has(log.id);
  checkbox.setAttribute("aria-label", `Select ${log.name ?? "entry"} for a template`);
  checkbox.onchange = () => {
    if (checkbox.checked) selectedLogIds.add(log.id);
    else selectedLogIds.delete(log.id);
    updateSaveBar();
  };

  const name = document.createElement("span");
  name.className = "log-name";
  name.textContent = log.name ?? "Entry";

  const values = document.createElement("div");
  values.className = "log-values";
  values.textContent = logDetail(log.values);

  const kcal = document.createElement("span");
  kcal.className = "log-kcal";
  kcal.textContent = String(Math.round(log.values.calories ?? 0));

  const time = document.createElement("span");
  time.className = "log-time";
  time.textContent = timeLabel(log.logged_at);

  const spacer = document.createElement("span");
  spacer.className = "log-spacer";

  const top = document.createElement("div");
  top.className = "log-top";
  const mealTypeSelect = renderMealTypeEdit(
    { label: log.name ?? "entry", mealType: log.meal_type, allowUnset: false },
    (mealType) =>
      void callAndRender("update_nutrition_log", { log_id: log.id, meal_type: mealType }),
  );
  top.append(checkbox, name, mealTypeSelect, time, spacer, kcal);

  const body = document.createElement("div");
  body.append(top, values);

  const confirm = renderDeleteLogControl(log, body);
  const deleteBtn = renderDeleteLogBtn(log, body, confirm);

  li.append(deleteBtn, body, confirm);
  return li;
}

function render(payload: NutritionDayPayload): void {
  currentPayload = payload;
  statusEl.textContent = payload.summary;

  ringValueEl.textContent = Math.round(payload.hero.consumed).toLocaleString();
  ringTargetEl.textContent = payload.hero.target
    ? `/ ${Math.round(payload.hero.target).toLocaleString()}`
    : "";
  const pct = payload.hero.target ? Math.min(payload.hero.consumed / payload.hero.target, 1) : 0;
  ringFillEl.style.strokeDasharray = `${RING_CIRCUMFERENCE}`;
  ringFillEl.style.strokeDashoffset = `${RING_CIRCUMFERENCE * (1 - pct)}`;

  barsEl.replaceChildren(...payload.bars.map(renderBar));
  renderRemaining(payload);

  templatesCountEl.textContent = payload.templates.length
    ? `${payload.templates.length} saved`
    : "";
  renderMealFilters(payload.templates);
  const shown = visibleTemplates(payload.templates);
  templatesEl.replaceChildren(
    ...(shown.length
      ? shown.map(renderTemplate)
      : [
          Object.assign(document.createElement("li"), {
            className: "muted",
            textContent: payload.templates.length
              ? "Nothing matches that filter."
              : "No saved meals yet.",
          }),
        ]),
  );

  // Drop selections for entries that no longer exist (e.g. after a refresh).
  const liveIds = new Set(payload.logs.map((l) => l.id));
  for (const id of selectedLogIds) if (!liveIds.has(id)) selectedLogIds.delete(id);
  updateSaveBar();

  logsEl.replaceChildren(
    ...(payload.logs.length
      ? payload.logs.map(renderLog)
      : [Object.assign(document.createElement("li"), { className: "muted", textContent: "Nothing logged yet." })]),
  );
}

async function callAndRender(name: string, args: Record<string, unknown>): Promise<boolean> {
  try {
    const result = await app.callServerTool({ name, arguments: args });
    const payload = extractPayload(result);
    if (payload) render(payload);
    return true;
  } catch (err) {
    statusEl.textContent = "Something went wrong talking to the server.";
    statusEl.className = "error";
    console.error(err);
    return false;
  }
}

// match's fields are all per 100g — grams is how many grams were actually portioned.
function macroSummary(match: FoodMatch, grams = 100): string {
  const scale = grams / 100;
  const parts: string[] = [];
  if (match.calories != null) parts.push(`${Math.round(match.calories * scale)} cal`);
  if (match.protein_g != null) parts.push(`${Math.round(match.protein_g * scale)}g protein`);
  if (match.carbs_g != null) parts.push(`${Math.round(match.carbs_g * scale)}g carbs`);
  if (match.fat_g != null) parts.push(`${Math.round(match.fat_g * scale)}g fat`);
  if (match.fiber_g != null) parts.push(`${Math.round(match.fiber_g * scale)}g fiber`);
  return parts.join(", ");
}

function renderFoodResult(match: FoodMatch): HTMLLIElement {
  const li = document.createElement("li");

  const info = document.createElement("div");
  const name = document.createElement("div");
  name.className = "food-result-name";
  name.textContent = match.brand ? `${match.name} (${match.brand})` : match.name;
  const meta = document.createElement("div");
  meta.className = "food-result-meta";
  info.append(name, meta);

  // match's macros are all per 100g — gramsInput is how many grams were actually
  // portioned (kitchen-scale style), not a multiple of some serving. Prefilled from
  // the manufacturer's own serving size when OFF reports one in grams, else 100.
  const gramsInput = document.createElement("input");
  gramsInput.type = "number";
  gramsInput.className = "food-result-grams";
  gramsInput.value = String(match.serving_grams ?? 100);
  gramsInput.min = "1";
  gramsInput.step = "1";
  gramsInput.setAttribute("aria-label", `Grams of ${match.name}`);

  const gramsUnit = document.createElement("span");
  gramsUnit.className = "food-result-grams-unit";
  gramsUnit.textContent = "g";

  const mealTypeSelect = document.createElement("select");
  mealTypeSelect.className = "meal-type-select";
  mealTypeSelect.setAttribute("aria-label", `Meal type for ${match.name}`);
  populateMealTypeSelect(mealTypeSelect, { includeUnset: true });

  const updateMeta = () => {
    const grams = Number(gramsInput.value) || 0;
    meta.textContent = `${grams}g — ${macroSummary(match, grams)}`;
  };
  gramsInput.oninput = updateMeta;
  updateMeta();

  const logBtn = document.createElement("button");
  logBtn.type = "button";
  logBtn.className = "food-result-log";
  logBtn.textContent = "Log";
  logBtn.onclick = () => {
    const grams = Number(gramsInput.value) || 100;
    const scale = grams / 100;
    const macros: [string, number | null][] = [
      ["calories", match.calories],
      ["protein_g", match.protein_g],
      ["carbs_g", match.carbs_g],
      ["fat_g", match.fat_g],
      ["fiber_g", match.fiber_g],
    ];
    const entries = macros
      .filter(([, value]) => value != null)
      .map(([trackable_key, value]) => ({ trackable_key, value: (value as number) * scale }));
    void callAndRender("log_nutrition", {
      entries,
      name: match.name,
      meal_type: mealTypeSelect.value || null,
    }).then((ok) => {
      if (!ok) return;
      foodSearchResultsEl.replaceChildren();
      foodSearchInput.value = "";
    });
  };

  const actions = document.createElement("div");
  actions.className = "food-result-actions";
  actions.append(gramsInput, gramsUnit, mealTypeSelect, logBtn);

  li.append(info, actions);
  return li;
}

async function performFoodSearch(): Promise<void> {
  const query = foodSearchInput.value.trim();
  if (!query) return;
  foodSearchResultsEl.replaceChildren(
    Object.assign(document.createElement("li"), { className: "muted", textContent: "Searching…" }),
  );
  try {
    const result = await app.callServerTool({ name: "search_food_facts", arguments: { query } });
    const matches = extractMatches(result);
    foodSearchResultsEl.replaceChildren(
      ...(matches.length
        ? matches.map(renderFoodResult)
        : [Object.assign(document.createElement("li"), { className: "muted", textContent: "No matches found." })]),
    );
  } catch (err) {
    foodSearchResultsEl.replaceChildren(
      Object.assign(document.createElement("li"), { className: "error", textContent: "Search failed." }),
    );
    console.error(err);
  }
}

foodSearchBtn.onclick = () => void performFoodSearch();
foodSearchInput.onkeydown = (event) => {
  if (event.key === "Enter") void performFoodSearch();
};

saveTemplateBtn.onclick = () => {
  const name = templateNameInput.value.trim();
  if (!name || selectedLogIds.size === 0) return;
  const logIds = Array.from(selectedLogIds);
  const defaultMealType = saveTemplateMealTypeEl.value || null;
  // Clear before the call, not in a .then() after it — callAndRender's own render()
  // runs as soon as the server responds and reads selectedLogIds to check each log's
  // checkbox, so clearing afterward was always one render too late: the items stayed
  // checked (and the save bar stayed visible) until something else re-rendered.
  selectedLogIds.clear();
  templateNameInput.value = "";
  saveTemplateMealTypeEl.value = "";
  void callAndRender("save_meal_template", {
    name,
    log_ids: logIds,
    default_meal_type: defaultMealType,
  });
};
templateNameInput.onkeydown = (event) => {
  if (event.key === "Enter") saveTemplateBtn.click();
};

mealFilterEl.oninput = () => {
  mealNameFilter = mealFilterEl.value;
  if (currentPayload) render(currentPayload);
};

// Hosts with a push channel (the SPA) send fresh results proactively; hosts without
// one (a chat widget) at least get freshness whenever the user returns to the tab.
// No interval polling: in chat hosts every server call may prompt for approval.
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") void callAndRender("get_nutrition_day", {});
});

// The host pushes the originating tool's result (e.g. get_nutrition_day) once on render.
app.ontoolresult = (result) => {
  const payload = extractPayload(result);
  if (payload) render(payload);
  else statusEl.textContent = "Waiting for data…";
};

await app.connect();

// The SPA draws the ring and the macro bars itself, in the page hero band above
// this iframe (it reads the same payload — see AppRenderer's `onResult`). Drawing
// them here too would show the day twice, so the block is dropped in that host and
// kept everywhere else, where this component is the only thing on screen.
if (app.getHostVersion()?.name === "swolemates-web") dayHeroEl.hidden = true;

statusEl.textContent = "Loading…";
