# Workouts v1 — prototype spec (ticket #3)

> **Status: PROTOTYPE / reaction artifact.** Nothing here is decided. This is a rough
> outline for Will to attack; every judgment call I wasn't sure about is in
> [Open questions](#open-questions-for-will) instead of being silently decided.
>
> Inputs: legacy schema 0003/0004/0010 + WorkoutBuilder/ActivityForm/workouts pages,
> [product vision](https://github.com/chill-projects/swolemates/issues/1#issuecomment-5136252340),
> [#14 interaction model](https://github.com/chill-projects/swolemates/issues/14),
> [#10 MCP Apps constraints](https://github.com/chill-projects/swolemates/issues/10),
> [#15 exercise metadata](https://github.com/chill-projects/swolemates/issues/15),
> tmpx platform slice.

## 1. Scope

Strength + activity logging (per-set actuals are a hard requirement), workout
templates/plans, a planned-workouts view with descriptions/images, a mobile-first
in-workout mode built for progressive overload, and streak/PR celebration hooks.
Coaching itself lives in Claude chat (#14) — this slice's job is to expose the data
tools that make coaching possible.

## 2. Domain model

Legacy 0003/0004 is a good skeleton: `exercises → workouts → workout_exercises →
workout_sets`, with a strength/activity discriminator on `workouts` and a reps/time
discriminator on `workout_sets`. Proposed adaptations, then new tables.

### Adaptations from legacy

- `user_id` is the WorkOS `sub` — `String(255)`, no FK, filtered in the service layer
  (tmpx pattern). All RLS policies drop out; `services/workouts.py` is the only authz.
- Legacy 0010's atomic `save_strength_workout` RPC becomes an ordinary service function
  doing the whole write in one session/transaction — same guarantee, no plpgsql.
- Keep 0004's CHECK constraints (`workout_type_fields_check`, `set_type_fields_check`)
  as real DB constraints; they encode invariants v2 auto-progression relies on.
- Keep the 0003 comment's intent: for a *completed* set, actuals are required. But v1
  adds an **in-progress workout** state (in-workout mode), so "required" moves from
  NOT NULL to the set-level CHECK + service validation (port of
  `workoutValidation.ts`: reps sets need reps > 0 and weight ≥ 0; timed sets need
  work_seconds > 0).

### Tables

**exercises** (catalog + custom)
- `id uuid pk`, `name text`, `muscle_group text`, `equipment text?`
- `description text?` — joined `instructions` from free-exercise-db (#15)
- `image_paths jsonb?` — e.g. `["exercise-images/Barbell_Squat/0.jpg", ".../1.jpg"]`,
  served same-origin from FastAPI static (iframe CSP: no external origins)
- `source_id text?` — free-exercise-db id, for later re-sync / full-catalog import
- `is_custom bool`, `created_by text?` (WorkOS sub; null for catalog rows)
- Read rule in service: `is_custom = false OR created_by = user_sub` (port of the RLS
  policy).

**workouts** (one session, strength or activity)
- `id uuid pk`, `user_id str`, `workout_type enum(strength|activity)`
- `activity_type enum(yoga|pilates|cardio|other)?`, `duration_minutes int?` (activity only, CHECK)
- `title text?`, `notes text?`, `started_at`, `completed_at?` — **`completed_at IS NULL`
  = in-progress workout**; this row *is* the in-workout-mode state (see §5/§7)
- `template_id uuid? → workout_templates` — provenance: which plan this session ran

**workout_exercises**
- `id`, `workout_id fk cascade`, `exercise_id fk`, `order_index int`
- `notes text?` — free-form
- `next_time_note text?` — the "notes-for-next-time" field: written during/after this
  session, surfaced the next time this exercise comes up (in-workout mode and planned
  view show the most recent one for each exercise)

**workout_sets**
- `id`, `workout_exercise_id fk cascade`, `set_number int`
- `set_type enum(reps|time)`, `is_warmup bool`, `rpe numeric?`
- `prescribed_weight numeric?`, `prescribed_reps int?` — filled from the template /
  progression suggestion when a session starts; actuals vs prescribed is the
  progressive-overload signal
- `actual_weight numeric?`, `actual_reps int?`, `work_seconds int?`, `rest_seconds int?`
- `completed_at timestamptz?` — null until the set is logged (in-progress support)

**workout_templates** (created in chat, edited on both surfaces)
- `id`, `user_id str`, `name text`, `description text?`, `archived_at?`

**template_exercises**
- `id`, `template_id fk cascade`, `exercise_id fk`, `order_index int`
- `target_sets int`, `target_reps int?`, `target_seconds int?`, `target_weight numeric?`
  (nullable weight = "use last time's / coach's call"), `notes text?`
- Deliberately simple: uniform sets per exercise (`4×8 @ 60kg`), not per-set
  prescriptions. Legacy had no templates at all, so there's nothing to port; per-set
  template detail feels like v2. (Open question 2.)

**planned_workouts** (the schedule)
- `id`, `user_id str`, `template_id fk`, `scheduled_for date`, `status
  enum(planned|done|skipped)`, `workout_id uuid?` (set when done), `note text?`
- Minimal calendar: "Leg Day on Thursday". Recurrence (every Mon/Thu) is deliberately
  out — Claude can lay out a week of rows conversationally. (Open question 3.)

**personal_records** (denormalized celebration cache)
- `id`, `user_id str`, `exercise_id fk`, `kind enum(weight|e1rm|reps_at_weight)`,
  `value numeric`, `reps int?`, `weight numeric?`, `workout_set_id fk`, `achieved_at`
- Written inside the same transaction as set logging; makes "is this a PR?" a cheap
  lookup instead of a scan. Could instead be computed on the fly for two users —
  kept as a table because the celebration check runs on every logged set. (OQ 4.)

## 3. Templates & plans model

- **Created conversationally in chat** (#14): "make me a pull day" → Claude calls
  `create_workout_template` with exercises + targets. No template-builder wizard needed
  in v1 chat.
- **Edited on both surfaces via one shared component** (`ui://swolemates/template.html`):
  reorder, swap exercise, adjust sets/reps/weight, edit notes. Same bundle in Claude
  and the SPA templates page — this is the "wrong result editable in place" property
  from the vision.
- Templates are prescriptions; sessions copy targets into `prescribed_*` on the sets at
  start time, so editing a template never rewrites history.

## 4. Planned-workouts view

- "What's next": upcoming `planned_workouts` joined with template detail, plus per
  exercise: description, images (2-frame JPEGs, same-origin per #15), last session's
  actuals for that exercise, and the latest `next_time_note`.
- Rendered by a shared `ui://swolemates/planned.html` component (returned by
  `get_planned_workouts`) and embedded on the SPA home/workouts page. Primary CTA:
  **Start workout** → calls `start_workout` and hands off to in-workout mode.

## 5. In-workout mode (mobile-first)

The centerpiece. Flow:

1. **Start** — from a planned workout, a template, or blank. `start_workout` creates a
   `workouts` row (`completed_at NULL`) with `workout_exercises` + `workout_sets`
   pre-created from the template's targets (`prescribed_*` filled, `actual_*`/
   `completed_at` null).
2. **Per-exercise card** (one exercise on screen at a time, big touch targets):
   - Header: name, thumbnail image, tap for description.
   - **Progressive-overload framing:** "Last time: 60kg × 8, 8, 7" + the last
     `next_time_note` ("felt easy, go 62.5") right where you pick the weight.
   - Set rows: weight / reps steppers **prefilled from prescription, falling back to
     last time's actuals** — logging a set that matches is one tap. Warmup toggle,
     optional RPE. `log_set` writes actuals + `completed_at` per set.
   - Add/remove sets, add an unplanned exercise (filterable picker, grouped by muscle
     group — port of WorkoutBuilder's picker).
   - **Notes-for-next-time** field per exercise, one thumb-typed line.
3. **Finish** — `finish_workout` stamps `completed_at`, links the planned_workout,
   validates (workoutValidation port; empty un-logged prescribed sets are dropped, not
   errors), computes PRs/streak, and returns the summary + celebration payload.
4. Abandoning: an in-progress workout older than ~24h is offered for discard/finish on
   next surface load. No timer/rest-clock in v1. (OQ 6.)

Because all state is server-side rows (a #10 hard rule — no persistence in the iframe),
the same in-progress workout is resumable from either surface mid-session: phone dies →
open Claude, "finish my workout".

**Activity logging** stays the simple legacy form (type/duration/notes) — a small
shared component or plain tool call; it doesn't need in-workout mode.

## 6. Streaks & PR celebrations

Per #14: streaks + progressive-overload wins only; no XP/levels/badges.

- **PR check** on `log_set`/`finish_workout`: heaviest weight ever for the exercise,
  best estimated 1RM (Epley: `w × (1 + reps/30)`), and most reps at a given weight.
  Warmups excluded. New records insert into `personal_records` and ride the tool
  result: `celebrations: [{type: "pr", exercise, kind, value, previous}]`.
- **Streak** = consistency, computed from completed workouts: current run of weeks with
  ≥ N workouts (N = weekly target; default 3, per-user setting later). Returned as
  `streak: {weeks, this_week, target}` in workout payloads. The legacy
  **ConsistencyCalendar** ports as the visual (SPA dashboard; also usable in a
  progress component).
- **Both surfaces celebrate from the same payload**: the in-workout component shows the
  moment inline (confetti-ish, legacy-styled); the `summary` text names it ("New PR:
  Deadlift 140kg — up from 135") so Claude narrates it in chat and can coach off it.
  No push/proactive messaging in v1 (#14 keeps the rule engine in v2).

## 7. Surfaces: shared ui:// components vs SPA pages

Under the #10 constraints (self-contained single-file bundles, no CSP domains, re-render
from any single tool result, server-side state only, host-driven sizing with fluid
width + autoResize, buttons-not-forms, no polling, text fallback on every tool).

**Shared `ui://` components** (one resource per feature; many tools point at each):

| Resource | Renders | Tools bound to it |
|---|---|---|
| `ui://swolemates/workout-live.html` | in-workout mode + finish summary/celebration | `start_workout`, `log_set`, `update_workout_entry`, `finish_workout`, `get_active_workout` |
| `ui://swolemates/template.html` | template view/edit | `create_workout_template`, `get_workout_template`, `update_workout_template` |
| `ui://swolemates/planned.html` | planned-workouts view ("what's next") | `get_planned_workouts`, `plan_workout` |
| `ui://swolemates/workout-summary.html` | one completed workout, editable actuals | `log_workout`, `get_workout` |

Exercise images work inside the sandbox only if same-origin fetches resolve — they're
served from our origin, and #10 says *every* origin must be declared; the bundle can
either inline nothing and declare our own origin in `resourceDomains`, or (safer,
per-#10 "no CSP domains") the tool result carries small base64 thumbnails. (OQ 7.)

**SPA pages** (thin shells around generated-client hooks + embedded shared components):
- `/workouts` — history list (legacy workouts_page design), embeds planned component
- `/workouts/:id` — detail; embeds workout-summary component for in-place edit
- `/workouts/live` — full-screen wrapper around workout-live (the phone-in-the-gym view)
- `/templates`, `/templates/:id` — list + template component
- Dashboard gets the ConsistencyCalendar (SPA-only; pure display, no tool round-trips
  needed — cheaper as a plain React port). (OQ 8.)

**Chat-only:** trends/progress questions ("how's my squat going?") are tool + text in
v1; a progress-chart component is a fast follow.

## 8. Claude tools (task-shaped)

Model-visible entry points (all also return `summary` text for non-UI hosts):

- `log_workout(exercises, title?, date?)` — the chat path: whole completed session in
  one call ("I did 5×5 squats at 100kg"). Returns summary + celebrations.
- `log_activity(activity_type, duration_minutes, title?, notes?, date?)`
- `start_workout(template_id? | planned_id? | exercises?)` → in-workout component
- `finish_workout(workout_id, notes?)`
- `create_workout_template(name, exercises[{exercise, sets, reps?, weight?, notes?}])`
- `get_workout_template(name_or_id)` / `list_workout_templates()`
- `plan_workout(template_id, date)` / `get_planned_workouts(range?)`
- `get_workout_history(range?, exercise?)` — history + streak, feeds coaching
- `get_exercise_progress(exercise)` — per-exercise actuals over time, PRs, e1RM trend —
  the coach's data source (#14)
- `search_exercises(query?, muscle_group?)` / `add_custom_exercise(name, muscle_group, equipment?)`

App-only (`visibility=["app"]`, iframe-driven): `log_set`, `update_workout_entry`
(add/remove/reorder exercise or set mid-workout, edit next-time note),
`update_workout_template`, `get_active_workout`, `update_workout` (edit a past
session's actuals from the summary component). Mutations return the full payload
(tmpx `_items_payload` pattern) so components re-render from any result. Exact
final surface to be reconciled with ticket #6.

## 9. Exercise catalog seeding

Adopt #15 as-is:
- Vendor free-exercise-db (public domain). Starter catalog = the 40 legacy exercises
  from 0003, via the checked-in name → free-exercise-db id mapping (verified 40/40).
- Seed script joins the mapping against `dist/exercises.json` → `name, muscle_group,
  equipment, description, image_paths, source_id`. Copies the ~80 JPEGs into
  `backend/app/static/exercise-images/` (~4–5 MB, in the container image).
- Runs as an idempotent seed step (upsert on `source_id`) alongside migrations.
  Remaining ~830 exercises are a later import, no new decision.

## 10. Slice seed data (dev/demo)

`make seed` (dev only, idempotent, two demo users to exercise partner views later):
- 3 templates: Push / Pull / Legs, 4–6 exercises each with plausible targets.
- ~4 weeks of completed workout history per user, weights trending up (so
  `get_exercise_progress`, streaks, and a near-miss PR are demonstrable), including
  a couple of `next_time_note`s and one activity (yoga).
- Next week of `planned_workouts`, one in-progress workout for testing resume.

## Open questions for Will

1. **Units.** Legacy stored bare `numeric` weight. Store kg and render per-user
   preference, or store a unit column per set? (Affects PR math if you two use
   different units.)
2. **Template granularity.** Uniform `sets × reps @ weight` per exercise (proposed) —
   or per-set prescriptions (e.g. ramping 5/3/1-style sets) in v1?
3. **Planned workouts: recurrence?** I kept a flat date list and let Claude lay out
   weeks. Want real recurrence rules (every Mon/Thu) in v1 instead?
4. **`personal_records` table vs computed.** I denormalized for cheap per-set checks;
   for two users a query-time scan is also fine and one less table. Preference?
5. **PR definitions.** Heaviest weight + Epley e1RM + reps-at-weight, warmups excluded.
   Too many? Just "heaviest weight" for v1? And what's the weekly streak target —
   fixed 3, or configurable from day one?
6. **In-workout niceties.** Rest timer and workout duration display are cut from v1
   (they invite polling/ticking in an iframe). Agree, or is a rest timer essential to
   the gym experience? (A local-only ticker with no server round-trips is feasible.)
7. **Images in components.** Same-origin images require declaring our origin in the
   resource CSP (`resourceDomains`) — mild deviation from tmpx's "no CSP domains"
   purity, but keeps payloads small. Alternative: base64 thumbnails inside tool
   results (bigger payloads, zero CSP). Which way?
8. **ConsistencyCalendar surface.** I made it SPA-only (pure display). Should it also
   be a ui:// component so Claude can show your streak calendar in chat?
9. **Editing history in chat.** `update_workout` is app-only in my sketch (edits happen
   in the summary component). Should Claude also be able to edit past sessions
   conversationally ("actually that was 8 reps not 6") — i.e. model-visible too?
10. **Custom exercises** get no description/images (not in free-exercise-db). Fine, or
    should Claude write a description at creation time?
11. **Per-set RPE** is in the schema (legacy had it) but I left it out of the default
    in-workout UI to keep logging one-tap. Surface it, or schema-only until asked for?
12. **Activity types.** Keep the legacy enum (`yoga|pilates|cardio|other`) or free-text
    with suggestions, given #4's "general model with discriminators" direction for
    nutrition? (If nutrition lands on a generic trackables model, activities could
    eventually fold in — I kept them in `workouts` for v1.)

---

*Companion sketch: [`workouts_models_sketch.py`](./workouts_models_sketch.py) — a
non-compiled SQLAlchemy sketch of §2. Not under `backend/app`; does not affect the
app, migrations, or tests.*
