# Nutrition v1: generalized trackables, goals, and logging

> **PROTOTYPE — reaction artifact for [#4](https://github.com/chill-projects/swolemates/issues/4).**
> This is one concrete proposal for Will to mark up, not a decision. Nothing here is
> implemented; the models sketch (`nutrition_models_sketch.py`) is illustrative and does
> not live under `backend/app`.

Inputs: the [product vision](https://github.com/chill-projects/swolemates/issues/1#issuecomment-5136252340),
the [interaction-model decision (#14)](https://github.com/chill-projects/swolemates/issues/14),
the [OFF research (#11)](https://github.com/chill-projects/swolemates/issues/11),
the [MCP Apps constraints (#10)](https://github.com/chill-projects/swolemates/issues/10),
legacy migrations 0005/0007/0008 and components `FoodSearch` / `PhotoFoodLogger` /
`TargetsForm` / `ConfidenceBadge` / `TodaySummary`, legacy logic `tdee.ts` /
`openfoodfacts.ts` / `food-estimate.route.ts`, and the TmpX platform slice.

---

## 1. The generalized trackable model (the crux)

### Primary design: registry + single entries table + typed JSONB payloads + metrics

Three tables carry the whole domain. The key move is separating **what you can track**
(a registry row), **what you logged** (a single polymorphic entries table), and **what
you're aiming for** (goals against *metrics*, not tables).

```
trackable_types            entries                          goals
--------------            -------                          -----
key (PK, text)            id uuid PK                       id uuid PK
name                      user_id (WorkOS sub)             user_id
category                  type_key  → trackable_types      metric_key   e.g. "protein_g"
unit ("g","ml","dose")    occurred_at timestamptz          direction    at_least|at_most|target
payload_schema jsonb      quantity numeric  (in unit)      target numeric
metrics jsonb             payload jsonb     (typed)        period       day (v1: only day)
default_goal jsonb        source enum                      starts_on date
is_builtin bool           source_ref text                  ends_on date null  (null = active)
created_by null|user_id   status: confirmed|draft
                          confidence jsonb null
                          raw_provider_response jsonb null
                          edited_by_user bool
                          photo_ref text null
```

**Discriminator strategy.** `entries.type_key` is the discriminator; there is exactly one
log table. The "decorator" is `payload` — a JSONB blob validated in the **service layer**
by a Pydantic discriminated union keyed on `type_key`:

- `food` → `FoodPayload {name, brand?, meal_type?, serving_description?, calories, protein_g, carbs_g, fat_g, fiber_g?}`
- `water` → `WaterPayload {}` (quantity in ml is the whole story)
- `supplement` → `SupplementPayload {name, dose_description?}` (creatine is a seeded
  trackable_type, not special-cased)
- anything else → `GenericPayload {notes?}` validated against the registry row's
  `payload_schema` (a small JSON-schema-ish field list)

**"Extensible without a migration"** means, concretely: a new trackable type is an
`INSERT` into `trackable_types` (via a tool/UI, or seed), and entries for it flow
through the generic path immediately — quantity + unit + generic payload + a goal, all
render in the generic UI. Writing a *rich* Pydantic payload class or a bespoke component
for it is a code change, but never a schema change. The three built-ins ship as seed
rows, so "built-in" vs "user-created" is a flag, not a structural difference.

**Metrics: what goals and progress bind to.** A goal against "protein" is not a goal
against a table — it aggregates a field across food entries. Each registry row declares
the metrics its entries emit, as extraction rules over the entry:

```json
// trackable_types.metrics for "food"
{"calories": "payload.calories", "protein_g": "payload.protein_g",
 "carbs_g": "payload.carbs_g", "fat_g": "payload.fat_g", "fiber_g": "payload.fiber_g"}
// for "water"
{"water_ml": "quantity"}
// for "creatine" (supplement instance)
{"creatine_g": "quantity"}
```

The service layer's `day_totals(user_sub, date)` is one query over `entries` grouped by
`type_key`, folded through the metric map in Python. Two users, dozens of rows a day —
no need for generated columns or materialized views in v1; the escape hatch (JSONB
expression indexes / generated columns) exists if it ever matters.

**Why this shape:**
- One table to filter by `user_id` — the service-layer isolation rule stays one-liner simple.
- Cross-type queries ("everything logged today") are trivial — that's the daily screen.
- The photo-draft columns (`status`, `confidence`, `raw_provider_response`,
  `edited_by_user`) generalize legacy `food_logs`' forward-looking columns to every type.
- Goals-by-metric means "water goal" and "protein goal" are the same row shape, and a new
  trackable type gets goals for free.
- Goal rows have date ranges (`starts_on`/`ends_on`) instead of legacy's mutable columns
  on `profiles` — historical hit/miss stays truthful when targets change.

### Rejected alternatives

1. **Per-type tables (joined-table inheritance): `food_logs`, `water_logs`, …** — every
   new trackable is a migration plus a UNION in every "today" query; it's the exact thing
   the ticket rules out.
2. **Pure EAV (`entry_values(entry_id, key, value)` rows)** — maximally generic but
   miserable to query and validate; JSONB payloads give the same extensibility with
   typed validation and readable rows.
3. **Legacy as-is (food-only table + target columns on profiles)** — no water/supplements,
   no goal history, and targets-on-profile can't express per-metric direction.

---

## 2. Goals: setting and progress

- **TDEE inputs** live in a small `nutrition_profiles` table (one row per user: sex, age,
  height_in, weight_lbs, activity_level, goal_type — imperial, per legacy 0008).
  `tdee.ts` ports to `services/tdee.py` verbatim: Mifflin-St Jeor, activity multipliers,
  GOAL_PARAMS, `distribute_macros` (protein anchored to bodyweight, fat/carbs/fiber
  redistribute when calories change), `goal_direction`-based hit/miss with the grace
  windows (deficit ≤105%, surplus ≥95%, maintain 90–110%).
- **Suggest → confirm, on both surfaces.** `suggest_nutrition_targets` computes from
  the profile; `set_nutrition_goals` writes goal rows (closing the previous rows'
  `ends_on`). In chat that's two tool calls with Claude narrating; in the app it's the
  ported `TargetsForm` (calculate button previews TDEE, fields stay hand-editable).
- **Directions:** calories = `target` (direction inferred from goal_type for hit/miss),
  protein/fiber/water = `at_least`, fat/carbs = `target` (advisory bars, never "failed").
  Creatine = `at_least` daily dose. Defaults come from `trackable_types.default_goal`.
- **Progress** = `day_totals` vs active goals: the `TodaySummary` port (calorie ring +
  macro bars + deterministic daily tip) as an MCP app for chat, the same component in the
  SPA dashboard. Streak/consistency calendar (per #14 gamification) reads
  `dayStatus`-style hit/miss over the goal history.

## 3. Meal patterns / templates

`templates` table: `id, user_id, name, items jsonb, created_at, updated_at`. `items` is
a list of entry drafts — `{type_key, quantity, payload}` — i.e. the same validated
payload shapes as entries, so logging a template is "insert N entries, stamped
`source='template'`, `source_ref=template_id`", with optional per-item overrides
("my usual breakfast but no toast").

- Created conversationally (`save_meal_template` — typically Claude proposes one from
  what you just logged), edited on both surfaces via one shared template-editor
  component (per #14).
- Templates can mix types: "morning stack" = creatine + water + a food item.

## 4. Food search (OFF), per #11

`services/food_catalog.py`, backend-only (protects the per-IP budget and hides OFF from
clients):

- **Text search**: Search-a-licious `GET search.openfoodfacts.org/search?q=…&page_size=20`
  **with `fields=code,product_name,brands,serving_size,nutriments`** (legacy omitted
  `fields`). Normalize `brands` as array here.
- **Barcode**: v3 product endpoint (new capability vs legacy), `fields=` always, HTTP 404
  = "not found" not an error. Normalize `brands` as comma-string here.
- User-Agent `Swolemates/1.0 (wfstevens@icloud.com)` (fixes legacy's non-conforming one).
- Capture per-100g **and** `_serving` nutriments + numeric `serving_quantity` when
  present, all nullable; keep legacy's drop-hits-without-calories filter.
- Rate limits (10/min search, 15/min product, per backend IP): debounce search-as-you-type
  ≥400 ms in the component, plus a small in-process TTL cache for barcode lookups. No
  cache table in v1.
- **Flow (both surfaces, shared `food-search` component):** search → pick product →
  choose grams or servings (scale per-100g or per-serving) → optional meal type → logs a
  `food` entry with `source='barcode'|'text_search'` and `source_ref=barcode`. In chat
  Claude can also drive it textually: `search_food` returns the normalized hit list as
  structured content + text, and Claude calls `log_food` with the scaled numbers.

## 5. Photo estimation flow (provider abstract)

- `services/food_estimator.py` defines a protocol only: `estimate(image) ->
  FoodEstimate {items[{name, serving_description, calories, protein_g, carbs_g, fat_g,
  fiber_g, confidence{per-field low|med|high}}], overall_confidence, assumptions[]}` —
  the legacy Gemini schema, kept as the interface. Which provider implements it is the
  separate ticket; v1 ships the protocol + a stub.
- Result is written as **`status='draft'` entries** (one per detected item) with
  `confidence` + `raw_provider_response` + `assumptions` retained, `source='photo_ai'`.
  Drafts are real rows, so they're editable **on either surface** immediately — the shared
  entry editor shows `ConfidenceBadge` per field (hide "high", amber/red for med/low) and
  the assumptions list. Confirming flips `status`; editing sets `edited_by_user` and
  clears that field's badge. Drafts don't count in `day_totals` until confirmed
  (open question below).
- Photo intake: SPA upload (client-side resize to ≤1024px as legacy did) or an image
  pasted in chat that Claude passes through the tool.

## 6. Shared components (per #10 constraints)

Three `ui://` bundles, single-file, self-contained, no CSP domains, all data via
`callServerTool`, re-renderable from any single tool result (every mutation tool returns
the full day payload), buttons+keydown not form-submit, host CSS vars with light/dark
fallbacks, `autoResize: true`, refresh on `visibilitychange` (no polling), plain-text
`summary` on every result:

1. `ui://swolemates/nutrition-today.html` — TodaySummary port (ring, macro/water bars,
   streak chip) + the day's entry list with **inline edit/delete** (this is the "wrong
   log fixable on either surface" component). Draft entries render with confidence
   badges + confirm button.
2. `ui://swolemates/food-search.html` — search → portion → log flow (§4).
3. `ui://swolemates/nutrition-goals.html` — TargetsForm port + template editor tab
   (they share the "list of editable typed rows" chassis).

The SPA renders the same three bundles via AppRenderer (fixed-height box for now; SSE
gives it freshness). **Mobile-first**: single column, big touch targets, number inputs
with `inputmode`, the legacy visual design (partner-approved) on the new stack.

## 7. Seed data (slice-owned)

Extend `backend/scripts/seed.py`: the three built-in `trackable_types` (+ metrics +
default goals), a `nutrition_profile` and active goal set for both dev users, ~10 days of
mixed entries (food from realistic OFF-shaped payloads, water, creatine — including one
photo-draft with mixed confidence and one `edited_by_user`), and one multi-type template
("usual breakfast"). Enough to render every component state offline, including
hit/miss/no-data calendar days. Built-in `trackable_types` rows are also inserted by
migration (idempotent) so production has them without seeding.

## 8. Proposed Claude tools (task-shaped)

| Tool | Visibility | Notes |
|---|---|---|
| `log_food(name, quantity_g \| servings, macros?, meal_type?, when?)` | model, app | macros optional — Claude estimates from its own knowledge when no OFF match |
| `log_water(amount_ml, when?)` | model, app | |
| `log_supplement(type_key, quantity?, when?)` | model, app | creatine and future supplements |
| `search_food(query)` / `lookup_barcode(code)` | model, app | returns normalized hits; renders food-search app |
| `get_nutrition_today(date?)` | model, app | renders nutrition-today; the coaching entry point |
| `get_nutrition_trends(days?)` | model | totals + hit/miss series, text/structured only — Claude narrates trends |
| `suggest_nutrition_targets()` / `set_nutrition_goals(...)` | model, app | renders goals app |
| `save_meal_template(name, items)` / `log_meal_template(name, overrides?)` | model, app | |
| `estimate_food_from_photo(image)` | model | writes draft entries; renders nutrition-today with drafts |
| `edit_entry(id, patch)` / `delete_entry(id)` / `confirm_entry(id)` | app (+model for edit/delete) | powers in-component editing |
| `define_trackable(key, name, unit, fields?, default_goal?)` | model | the no-migration extension path, chat-driven |

All thin wrappers over `services/nutrition.py` / `food_catalog.py` / `tdee.py`, same
functions the REST routers call, `user_sub` scoping inside the service per house rules.

## 9. Rough sequencing (for later ticket-splitting, not a commitment)

models + migration + seed → services (nutrition, tdee, food_catalog) → tools + REST →
nutrition-today component → food-search component → goals/templates component → photo
drafts (stub provider).

---

## Open questions for Will

1. **Draft entries and totals** — should photo drafts count toward the day's totals
   immediately (optimistic) or only after confirm? Proposal above says only after
   confirm; the counter-argument is you photograph food you definitely ate.
2. **Tool granularity** — per-type tools (`log_food`/`log_water`/`log_supplement`, as
   proposed) or one generic `log_intake(type_key, …)`? Per-type reads better in chat but
   grows the tool list with each new trackable.
3. **Partner visibility** — legacy `food_logs` was strictly owner-only, but the vision
   says "see your partner's results." Owner-only rows + a partner-visible daily summary
   (totals + hit/miss only, no individual entries)? Or full entry visibility?
4. **Streak semantics** — does the consistency streak require *food* logged, any entry at
   all, or hitting the calorie goal? (Legacy: any food log = logged day.)
5. **Water units** — ml canonical with oz display toggle, or oz-native like the imperial
   body stats?
6. **Custom trackables in v1 UI** — `define_trackable` chat-only (as proposed), or does
   the app also need a "new trackable" form in v1?
7. **Goal changes mid-week** — proposal keeps dated goal rows so history stays truthful;
   fine to show "goal changed" markers in the calendar, or overkill?
8. **Meal type** — keep legacy's free-text-ish breakfast/lunch/dinner/snack on food
   entries, or drop it in favor of timestamps only?
