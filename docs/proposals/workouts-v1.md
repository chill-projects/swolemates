# Workouts v1 — prototype spec (ticket #3)

> **Status: DECIDED.** Every open question below is resolved — see
> [Resolved decisions](#resolved-decisions) — from a live grilling session with
> Michelle, 2026-08-11 (issue #3's resolution comment has the same summary). This
> doc reflects the final shape, not the original draft.
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
- **Units: canonical lbs, per-user display preference.** Every weight column
  (`prescribed_weight`, `actual_weight`, `template_exercises.target_weight`) stores
  a plain numeric in **pounds**, regardless of who logged it or what unit they
  prefer to see. Conversion to kg (if a user prefers it) happens only at render —
  the preference field itself lives on the user's profile, owned by
  [Onboarding (#9)](https://github.com/chill-projects/swolemates/issues/9), not this
  slice. PR math, e1RM, and "last time" comparisons all operate on canonical values
  and never need to reconcile mixed units.

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
- `activity_type text?` — free text, not an enum (e.g. "yoga", "hot yoga", "pool").
  Autocomplete suggestions come from the user's own past values (primed with a small
  starter list: yoga, pilates, cardio, swimming, hiking), not a controlled
  vocabulary. Matching for suggestions trims/lowercases so casing alone doesn't
  fragment the list, but distinct labels (`"yoga"` vs `"hot yoga"`) stay distinct —
  that granularity is the point.
- `duration_minutes int?` (activity only, CHECK)
- `title text?`, `notes text?`, `started_at`, `completed_at?` — **`completed_at IS NULL`
  = in-progress workout**; this row *is* the in-workout-mode state (see §5/§7)
- `template_id uuid? → workout_templates` — provenance: which plan this session ran

**workout_exercises**
- `id`, `workout_id fk cascade`, `exercise_id fk`, `order_index int`
- `superset_group int?` — null for a solo exercise; exercises sharing a group (and
  workout) are one superset, worked back-to-back before the shared rest. Added after
  the in-workout prototype (§5) surfaced grouping as a real requirement, not a v2
  nice-to-have.
- `notes text?` — free-form
- `next_time_note text?` — the "notes-for-next-time" field: written during/after this
  session, surfaced the next time this exercise comes up (in-workout mode and planned
  view show the most recent one for each exercise)

**workout_sets**
- `id`, `workout_exercise_id fk cascade`, `set_number int`
- `set_type enum(reps|time)`, `is_warmup bool`
- `prescribed_weight numeric?`, `prescribed_reps int?` — filled from the template /
  progression suggestion when a session starts; actuals vs prescribed is the
  progressive-overload signal
- `actual_weight numeric?`, `actual_reps int?`, `work_seconds int?`, `rest_seconds int?`
- `completed_at timestamptz?` — null until the set is logged (in-progress support)

**workout_templates** (created in chat, edited on both surfaces)
- `id`, `user_id str`, `name text`, `description text?`, `archived_at?`

**template_exercises**
- `id`, `template_id fk cascade`, `exercise_id fk`, `order_index int`
- `superset_group int?` — same convention as `workout_exercises.superset_group`;
  `start_workout` copies it onto the session rows along with the targets.
- `target_sets int`, `target_reps int?`, `target_seconds int?`, `target_weight numeric?`
  (nullable weight = "use last time's / coach's call"), `notes text?`
- Deliberately simple: uniform sets per exercise (`4×8 @ 135lbs`), not per-set
  prescriptions. Legacy had no templates at all, so there's nothing to port; per-set
  template detail feels like v2. **Decided** — see resolved Open question 2.

**weekly_pattern** (the standing split — new)
- `id`, `user_id str`, `day_of_week int (0–6)`, `template_id fk? → workout_templates`
  (null = rest/no plan that day)
- Up to 7 rows per user: "Monday is legs, Tuesday is pool." This is what generates a
  new week's `planned_workouts` rows — editing the pattern only affects weeks
  generated after the edit; a week already materialized is independent rows and
  doesn't retroactively change.

**planned_workouts** (the schedule)
- `id`, `user_id str`, `template_id fk`, `scheduled_for date`, `status
  enum(planned|done|skipped)`, `workout_id uuid?` (set when done), `note text?`
- Generated for the upcoming week from `weekly_pattern`; the user (on a Sunday
  review, say) prunes/adjusts before committing. Once generated, rows are never
  deleted — only `status` changes (e.g. to `skipped`) — which is what makes them
  double as the streak target for that week (§6): the row count *is* the
  commitment, and it doesn't shrink just because a session gets skipped later.
  Flat list, no recurrence-rule engine — the pattern above is the recurring part;
  each week's rows are concrete and freely editable.

**personal_records** (current-record cache, mutable)
- `id`, `user_id str`, `exercise_id fk`, `kind enum(weight|e1rm)`, `value numeric`,
  `workout_set_id fk`, `achieved_at`
- **One row per `(user_id, exercise_id, kind)`, updated in place — not an append-only
  log.** `log_set` upserts this row when a new record beats the cached value. If the
  *referencing* set is later edited or deleted (via `update_workout`, model-visible —
  §8), the service recomputes the true max from the remaining sets for that
  exercise/kind and updates (or deletes, if none remain) the cached row — a targeted
  recheck, not a live computation on every read. This was chosen over computing PRs
  on the fly (cheap at 2-user scale, but loses "notice the moment a record breaks,"
  not needed here) and over a true append-only history log (would go stale forever
  after a correction, since editing history is in scope for v1).

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

- **Generation**: a new week's `planned_workouts` rows come from `weekly_pattern`
  (§2) — "Monday is legs" materializes into a dated row for the upcoming Monday.
  This is where you review and prune before committing (skip a day that doesn't fit
  that week, add an extra session) — once generated, that week's rows are the fixed
  commitment the streak target reads from (§6).
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
2. **Scrollable accordion, grouped by superset** (decided against a one-exercise
   wizard and a flattened rest-timer queue — see [Prototyping: layout](#prototyping-layout)
   below). Whole workout visible at once; expand any group, log in any order, finish
   whenever.
   - The accordion unit is the **group**, not the exercise: a solo exercise is a group
     of one; a superset (`superset_group`, §2) is a group of two+ that expand/collapse
     together, badged "superset", with a "work back-to-back, then rest" hint. Exercises
     within a group render stacked (not interleaved set-by-set) — simplest to build and
     read; revisit only if stacking proves confusing in practice.
   - Header: name, thumbnail image, tap for description; `n/m sets` progress on the
     collapsed row.
   - **Progressive-overload framing:** "Last time: 135lbs × 8, 8, 7" + the last
     `next_time_note` ("felt easy, add 5") right where you pick the weight.
   - Set rows: weight / reps steppers **prefilled from prescription, falling back to
     last time's actuals** — logging a set that matches is one tap. Weight steppers
     increment by **5** (canonical lbs; a kg-preferring user sees converted values,
     stepping by an equivalent round increment — display concern only, §2) — the
     standard plate jump, not browser-default 1. Warmup toggle. `log_set` writes
     actuals + `completed_at` per set.
   - **Sets are open-ended, not capped at the prescription**: `+ Add set` appends a row
     (seeded from the last set's weight/reps/rest as a starting guess); any not-yet-
     logged set can be removed. This just works off the existing schema — sets are rows
     keyed by `workout_exercise_id` + `set_number`, not a fixed-size array — so no schema
     change was needed to support it, only UI.
   - Add an unplanned exercise (filterable picker, grouped by muscle group — port of
     WorkoutBuilder's picker).
   - **Notes-for-next-time** field per exercise, one thumb-typed line.
3. **Finish** — `finish_workout` stamps `completed_at`, links the planned_workout,
   validates (workoutValidation port; empty un-logged prescribed sets are dropped, not
   errors), computes PRs/streak, and returns the summary + celebration payload.
4. Abandoning: an in-progress workout older than ~24h is offered for discard/finish on
   next surface load. **No rest timer and no duration display in v1** — cut entirely,
   not even as a local-only ticker; keeping the component simple won out over the
   real (if modest) value a rest timer has for actual gym use.

Because all state is server-side rows (a #10 hard rule — no persistence in the iframe),
the same in-progress workout is resumable from either surface mid-session: phone dies →
open Claude, "finish my workout".

**Activity logging** stays the simple legacy form (type/duration/notes) — a small
shared component or plain tool call; it doesn't need in-workout mode.

### Prototyping: layout

Layout was checked with a throwaway UI prototype (`/prototype` skill) before writing
this section — see the branch link at the bottom of this doc. Four variants: A)
one-exercise-at-a-time wizard, B) scrollable accordion (whole workout visible), C)
flattened rest-timer-centric queue across all sets, D) B's accordion with superset
grouping and open-ended (add/remove) sets instead of a fixed count. **D won**: A hides
the rest of the workout, C loses the exercise-level structure supersets need, and both
A and B's fixed set counts didn't match how sets actually get added mid-workout (extra
set, changed my mind, etc.).

## 6. Streaks & PR celebrations

Per #14: streaks + progressive-overload wins only; no XP/levels/badges.

- **PR check** on `log_set`/`finish_workout`: heaviest weight ever for the exercise,
  and best estimated 1RM (Epley: `w × (1 + reps/30)`) — **not** reps-at-weight,
  trimmed for v1. Warmups excluded. A new record upserts the cached row in
  `personal_records` (§2 — mutable, recomputed if the achieving set is later edited)
  and rides the tool result: `celebrations: [{type: "pr", exercise, kind, value,
  previous}]`.
- **Streak**, redefined around your actual weekly commitment rather than a flat
  number:
  - **Target** = however many `planned_workouts` rows exist for that week (generated
    from `weekly_pattern`, then pruned to what you actually commit to — §2). Locked
    once the week's rows exist; skipping one later doesn't lower the target, since
    rows are never deleted, only status-flipped.
  - **Success** = a pure count of `workouts` completed that week (`completed_at`
    falls in the week) reaching that target. No requirement that a completed workout
    trace back to a specific planned row — any day, any order, and an unplanned
    bonus session counts too. It's "did you train this many times," not "did you
    follow the exact schedule."
  - **Fallback**: a flat default target of **3** for a week with zero
    `planned_workouts` (no pattern set, or a week nobody planned).
  - Returned as `streak: {weeks, this_week, target}` in workout payloads. The legacy
    **ConsistencyCalendar** ports as the visual, **SPA-only** (§7) — Claude narrates
    the streak in chat text, no chat-rendered calendar in v1.
- **Both surfaces celebrate from the same payload**: the in-workout component shows the
  moment inline (confetti-ish, legacy-styled); the `summary` text names it ("New PR:
  Deadlift 140lbs — up from 135") so Claude narrates it in chat and can coach off it.
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
served from our origin, and #10 says *every* origin must be declared. **Decided:**
the bundle declares our own origin in `resourceDomains` and fetches images
same-origin, rather than embedding base64 thumbnails in every tool result. It's a
narrow, self-referential exception to #10's "no CSP domains" default (our own
origin, already trusted everywhere else in the app), and it avoids re-embedding
image bytes on every workout/template/planned-workout payload that touches an
exercise.

**SPA pages** (thin shells around generated-client hooks + embedded shared components):
- `/workouts` — history list (legacy workouts_page design), embeds planned component
- `/workouts/:id` — detail; embeds workout-summary component for in-place edit
- `/workouts/live` — full-screen wrapper around workout-live (the phone-in-the-gym view)
- `/templates`, `/templates/:id` — list + template component
- Dashboard gets the ConsistencyCalendar. **Decided: SPA-only** — pure display, plain
  React port, no tool round-trips. Not a `ui://` component; chat answers streak
  questions from the structured `streak` object plus narration, not a rendered
  calendar. Revisit only if text narration proves too thin once this is in daily use.

**Chat-only:** trends/progress questions ("how's my squat going?") are tool + text in
v1; a progress-chart component is a fast follow.

## 8. Claude tools (task-shaped)

Model-visible entry points (all also return `summary` text for non-UI hosts):

- `log_workout(exercises, title?, date?)` — the chat path: whole completed session in
  one call ("I did 5×5 squats at 225lbs"). Returns summary + celebrations.
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
- `update_workout(workout_id, exercise_updates?, notes?)` — **decided model-visible**,
  not app-only: edit a past session's actuals conversationally ("actually that was 8
  reps not 6"). Matches the vision's "log/tweak records in chat" capability directly,
  same service call as the app-only edit path, and is the only way to correct a
  wrong `personal_records`-triggering set from chat (§2).

App-only (`visibility=["app"]`, iframe-driven): `log_set`, `update_workout_entry`
(add/remove/reorder exercise or set mid-workout, edit next-time note),
`update_workout_template`, `get_active_workout`. Mutations return the full payload
(tmpx `_items_payload` pattern) so components re-render from any result. Exact
final surface to be reconciled with ticket #6.

## 9. Exercise catalog seeding

Extends #15's recommendation (adopted, then broadened — see resolved decision below):
- Vendor free-exercise-db (public domain), **all 873 exercises seeded at launch**,
  not just the 40 legacy starters. The dataset's already fully vendorable and
  public-domain, so this is purely "how much of what we already have do we load,"
  not a new licensing or architecture question.
- The 40 legacy exercises still get their checked-in name → free-exercise-db id
  mapping (verified 40/40) so continuity of naming survives the port; the other 833
  seed under free-exercise-db's own names.
- Seed script joins `dist/exercises.json` → `name, muscle_group, equipment,
  description, image_paths, source_id` for every record. Copies all `exercises/<id>/
  {0,1}.jpg` files into `backend/app/static/exercise-images/` — **~90–110 MB** in the
  container image at full scale (vs. ~4–5 MB for just the 40 starters). One-time
  build-size cost, not per-request bandwidth (same-origin, browser-cached), so it
  doesn't change the "no CDN needed for two users" reasoning from #15.
- Runs as an idempotent seed step (upsert on `source_id`) alongside migrations.
- With the full catalog seeded, "custom exercise" (§2, `is_custom = true`) now means
  genuinely not in free-exercise-db at all — a much smaller set than "not in the 40
  starters." **Decided:** those get no auto-generated description — left blank
  rather than having Claude improvise instructions for an exercise it's never
  actually seen performed. The `notes` field on `workout_exercises` covers anything
  user-specific a blank description would've tried to guess at.

## 10. Slice seed data (dev/demo)

`make seed` (dev only, idempotent, two demo users to exercise partner views later):
- 3 templates: Push / Pull / Legs, 4–6 exercises each with plausible targets.
- ~4 weeks of completed workout history per user, weights trending up (so
  `get_exercise_progress`, streaks, and a near-miss PR are demonstrable), including
  a couple of `next_time_note`s and one activity (yoga).
- Next week of `planned_workouts`, one in-progress workout for testing resume.

## Resolved decisions

All twelve, resolved live with Michelle, 2026-08-11 (detail on each is inline in the
relevant section above; this is the index):

1. ~~**Units.**~~ **Resolved:** canonical storage in lbs, per-user display preference
   for conversion (§2).
2. ~~**Template granularity.**~~ **Resolved:** uniform `sets × reps @ weight` per
   exercise for v1, not per-set prescriptions. Templates and live workouts stay
   separate table families (`workout_templates`/`template_exercises` vs.
   `workouts`/`workout_exercises`/`workout_sets`) — `start_workout` copies
   `target_*` into `prescribed_*` once at session start, so per-set variation
   (ramping, drop sets) can still happen live without the template needing to
   model it. Per-set template prescriptions stay a v2 idea if uniform targets turn
   out to be too coarse in practice.
3. ~~**Planned workouts: recurrence?**~~ **Resolved:** a `weekly_pattern` table
   (day-of-week → template) generates each week's flat `planned_workouts` rows; no
   RRULE-style engine (§2).
4. ~~**`personal_records` table vs computed.**~~ **Resolved:** kept as a table, but as
   a mutable current-record cache (upserted, recomputed on edit/delete of the
   achieving set) rather than a computed-on-read value or an append-only log (§2).
5. ~~**PR definitions & streak target.**~~ **Resolved:** heaviest weight + e1RM only
   (reps-at-weight dropped); streak target derives from that week's committed
   `planned_workouts` count, not a flat number, falling back to 3 with no plan set
   (§6).
6. ~~**In-workout niceties.**~~ **Resolved:** cut entirely for v1 — no rest timer, no
   duration display, not even a local-only ticker (§5).
7. ~~**Images in components.**~~ **Resolved:** same-origin fetch via `resourceDomains`
   (§7).
8. ~~**ConsistencyCalendar surface.**~~ **Resolved:** SPA-only; Claude narrates streaks
   in chat text (§7).
9. ~~**Editing history in chat.**~~ **Resolved:** `update_workout` is model-visible,
   not app-only (§8).
10. ~~**Custom exercises.**~~ **Resolved:** seed the full 873-exercise catalog at
    launch (not just the 40 legacy starters), which shrinks "custom" down to
    genuinely-novel exercises; those still get no auto-generated description (§9).
11. ~~**Per-set RPE.**~~ **Resolved:** cut from the schema entirely — never used even
    in the legacy app, and nothing in v1 or the deferred v2 rule engine consumes it
    (§2).
12. ~~**Activity types.**~~ **Resolved:** free text with autocomplete suggestions from
    the user's own history, not a fixed enum (§2).

---

*Companion sketch: [`workouts_models_sketch.py`](./workouts_models_sketch.py) — a
non-compiled SQLAlchemy sketch of §2. Not under `backend/app`; does not affect the
app, migrations, or tests.*

*Companion prototype: [`prototype/in-workout-layout`](https://github.com/chill-projects/swolemates/tree/prototype/in-workout-layout)
— throwaway UI, `frontend/src/pages/PrototypeInWorkout.tsx`. Four in-workout layouts;
D (scrollable accordion, superset grouping, open-ended sets) is the decision captured
in §5.*
