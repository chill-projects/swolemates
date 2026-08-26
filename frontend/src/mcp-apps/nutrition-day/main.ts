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
  serving_description: string;
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
const templatesEl = $<HTMLDivElement>("templates");
const logsEl = $<HTMLUListElement>("logs");
const saveBarEl = $<HTMLDivElement>("save-template-bar");
const templateNameInput = $<HTMLInputElement>("template-name");
const saveTemplateBtn = $<HTMLButtonElement>("save-template-btn");
const foodSearchInput = $<HTMLInputElement>("food-search-input");
const foodSearchBtn = $<HTMLButtonElement>("food-search-btn");
const foodSearchResultsEl = $<HTMLUListElement>("food-search-results");

// Selection state for "save these as a template" — lives outside render() so it
// survives the re-renders every tool call triggers.
const selectedLogIds = new Set<string>();

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
  const items = [...payload.bars, payload.hero];
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

function renderTemplate(template: MealTemplateSummary): HTMLDivElement {
  const card = document.createElement("div");
  card.className = "template-card";

  const body = document.createElement("div");

  const name = document.createElement("strong");
  name.textContent = template.name;

  const total = document.createElement("div");
  total.className = "template-total";
  total.textContent = `${Math.round(template.totals.calories ?? 0)} cal`;

  const macros = document.createElement("div");
  macros.className = "muted template-macros";
  macros.textContent = macroLine(template.totals);

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
  logBtn.textContent = "Log";
  logBtn.onclick = () => void callAndRender("log_meal_template", { template_id: template.id });
  const itemsBtn = document.createElement("button");
  itemsBtn.type = "button";
  itemsBtn.textContent = "Items";
  itemsBtn.onclick = () => {
    itemsList.hidden = !itemsList.hidden;
  };
  actions.append(logBtn, itemsBtn);

  body.append(name, total, macros, actions, itemsList);

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
  saveTemplateBtn.textContent = `Save ${selectedLogIds.size} as template`;
}

function renderGroupedLog(log: DayLogEntry): HTMLLIElement {
  const li = document.createElement("li");
  li.className = "grouped-log";

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "group-toggle";
  const arrow = document.createElement("span");
  arrow.textContent = "▸ ";
  const label = document.createElement("span");
  label.textContent = log.name ?? "Meal";
  toggle.append(arrow, label);
  if (log.meal_type) {
    const meta = document.createElement("span");
    meta.className = "log-meta";
    meta.textContent = ` · ${log.meal_type}`;
    toggle.appendChild(meta);
  }
  const header = document.createElement("div");
  header.className = "log-name";
  header.appendChild(toggle);

  const values = document.createElement("div");
  values.className = "log-values";
  values.textContent = Object.entries(log.values)
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");

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

  li.append(header, values, items);
  return li;
}

function renderLog(log: DayLogEntry): HTMLLIElement {
  if (log.items.length > 0) return renderGroupedLog(log);

  const li = document.createElement("li");

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
  if (log.meal_type) {
    const meta = document.createElement("span");
    meta.className = "log-meta";
    meta.textContent = ` · ${log.meal_type}`;
    name.appendChild(meta);
  }

  const values = document.createElement("div");
  values.className = "log-values";
  values.textContent = Object.entries(log.values)
    .map(([key, value]) => `${key}: ${value}`)
    .join(", ");

  const top = document.createElement("div");
  top.className = "log-top";
  top.append(checkbox, name);

  li.append(top, values);
  return li;
}

function render(payload: NutritionDayPayload): void {
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

  templatesEl.replaceChildren(
    ...(payload.templates.length
      ? payload.templates.map(renderTemplate)
      : [Object.assign(document.createElement("p"), { className: "muted", textContent: "No saved meals yet." })]),
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

function macroSummary(match: FoodMatch): string {
  const parts: string[] = [];
  if (match.calories != null) parts.push(`${Math.round(match.calories)} cal`);
  if (match.protein_g != null) parts.push(`${Math.round(match.protein_g)}g protein`);
  if (match.carbs_g != null) parts.push(`${Math.round(match.carbs_g)}g carbs`);
  if (match.fat_g != null) parts.push(`${Math.round(match.fat_g)}g fat`);
  if (match.fiber_g != null) parts.push(`${Math.round(match.fiber_g)}g fiber`);
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
  meta.textContent = `${match.serving_description} — ${macroSummary(match)}`;
  info.append(name, meta);

  const logBtn = document.createElement("button");
  logBtn.type = "button";
  logBtn.className = "food-result-log";
  logBtn.textContent = "Log";
  logBtn.onclick = () => {
    const macros: [string, number | null][] = [
      ["calories", match.calories],
      ["protein_g", match.protein_g],
      ["carbs_g", match.carbs_g],
      ["fat_g", match.fat_g],
      ["fiber_g", match.fiber_g],
    ];
    const entries = macros
      .filter(([, value]) => value != null)
      .map(([trackable_key, value]) => ({ trackable_key, value: value as number }));
    void callAndRender("log_nutrition", { entries, name: match.name }).then((ok) => {
      if (!ok) return;
      foodSearchResultsEl.replaceChildren();
      foodSearchInput.value = "";
    });
  };

  li.append(info, logBtn);
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
  void callAndRender("save_meal_template", {
    name,
    log_ids: Array.from(selectedLogIds),
  }).then(() => {
    selectedLogIds.clear();
    templateNameInput.value = "";
  });
};
templateNameInput.onkeydown = (event) => {
  if (event.key === "Enter") saveTemplateBtn.click();
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
statusEl.textContent = "Loading…";
