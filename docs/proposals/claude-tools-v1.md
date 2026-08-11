# Proposal: Claude tool surface for v1

> **Status: DECIDED.** Resolved live with Michelle, 2026-08-11 (issue #6's resolution
> comment has the same summary). Workouts (#3) and nutrition (#4) are both closed now,
> so every former **OPEN** marker below is answered from their resolutions rather than
> left dangling. Where this draft and the closed `workouts-v1.md` had independently
> proposed different names for the same tool, `workouts-v1.md` wins throughout, with
> one deliberate exception (`log_set`, §3.1) reversed back the other way — noted
> inline where it happens.

Sources: ticket #6 · [product vision](https://github.com/chill-projects/swolemates/issues/1#issuecomment-5136252340)
· [interaction-model decision (#14)](https://github.com/chill-projects/swolemates/issues/14)
· [MCP Apps constraints research (#10)](https://github.com/chill-projects/swolemates/issues/10)
· [Open Food Facts research (#11)](https://github.com/chill-projects/swolemates/issues/11)
· [exercise metadata research (#15)](https://github.com/chill-projects/swolemates/issues/15)
· current patterns in `backend/app/mcp/tmpx_tools.py` · FastMCP 3.x docs (gofastmcp.com).

## 1. What chat owns (per #14)

Logging records (workouts incl. the in-workout flow, nutrition trackables) · template
creation/tweaking · goal setting · trends/history observation · food-fact search ·
**coaching** — Claude pushes toward goals and progressive overload using what the tools
expose. No autonomous rule engine (v2). No chat in the website; everything below is
registered on the existing FastMCP server at `/mcp`.

## 2. Design principles (carried from existing patterns + #10)

1. **Task-shaped, not a REST mirror.** `log_workout`, not `create_workout_row`. A tool
   corresponds to something a person says in chat, and one call finishes the thought.
2. **Every UI tool also returns plain text.** Payloads follow the tmpx shape:
   `{...structured data..., "summary": str}` — the summary is the whole story for
   non-UI hosts *and* the text Claude narrates from.
3. **One `ui://` resource per feature; related tools share it.** Every mutation returns
   the full payload its component needs, so any component can re-render from any single
   tool result (no client-side state, no polling — #10 checklist).
4. **Coaching is data, not behavior.** The server computes *facts* (streaks, PRs,
   trends, last-session numbers) and puts them in tool results. What to *say* about
   them lives in the coach prompt (§6). No server-side nudging.
5. **Thin tools.** Tools call service functions; all authz and `user_id` filtering
   stays in `app/services/` per AGENTS.md.

## 3. Proposed tools

Twenty-four tools across five groups (grew from the original 16 during reconciliation
with `workouts-v1.md` and this session's resolutions — see §8, tool count was decided
not to be trimmed for its own sake). Names are `verb_noun`, matching `log_workout` from
AGENTS.md. `whoami` already exists and stays.

### 3.1 Workouts — logging and the in-workout flow

The in-workout flow is a *conversation as well as an app UI*: "starting legs day" →
sets logged one message at a time between actual sets at the gym, or tapped in the
accordion component (§5 of `workouts-v1.md`) — either surface, same underlying rows.
Tools share one `ui://swolemates/workout-session.html` component (renamed
`workout-live.html` per `workouts-v1.md` §7) that renders the running session.

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `start_workout` | Begin a workout session, from a template, a planned workout, or ad hoc. | `template_id?` \| `planned_id?` \| `exercises?` | **Component** (session view) + summary incl. last-time numbers per planned exercise |
| `log_set` | Record one set against the active session (auto-starts one if none is active). | `exercise`, `weight?`, `reps`, `sets?` (default 1), `note?` | **Component** (updated session) + summary comparing to last session's same exercise |
| `finish_workout` | Close the session; capture notes-for-next-time; compute PRs/streaks. | `workout_id`, `notes?` | **Component** (session recap incl. celebrations) + summary |
| `log_workout` | One-shot: record an already-completed workout in a single call (retroactive or "I did X, Y, Z"). | `exercises[]` (each with sets/weights/reps), `title?`, `date?` | **Component** (recap) + summary; same celebration path as `finish_workout` |
| `log_activity` | Log a non-strength session (yoga, a swim, a hike) — the simple legacy form, no in-workout mode needed. | `activity_type` (free text, §2 of `workouts-v1.md`), `duration_minutes`, `title?`, `notes?`, `date?` | Summary only, no component |
| `update_workout` | Edit a past session's actuals conversationally ("actually that was 8 reps not 6"). | `workout_id`, `exercise_updates?`, `notes?` | Summary confirming the change (and any resulting PR correction) |
| `amend_last_log` | "Undo that" / fix the single most recent entry, workout or nutrition, without needing to identify which record. | — (resolves against the caller's own most recent log) | Summary confirming what was undone/changed |

Task-shaped because: each maps to a sentence someone says mid-workout, not a table.
`log_set` deliberately accepts one exercise's worth at a time — that's the message
grain of a person at the gym. `log_workout` exists so past workouts don't require
faking a live session. `amend_last_log` exists because "undo that" ten seconds after a
typo is a different, lower-friction ask than `update_workout`'s "go find the specific
session and fix it."

- **`log_set` is model-visible** — reversed from `workouts-v1.md` §8, which had it
  app-only. That was right for the component's own "+ set" button, but wrong as a
  blanket rule: this ticket's whole premise (and this session's resolved auto-start
  behavior, below) is that texting a set mid-workout has to work. `log_set` carries
  `visibility=["model","app"]`, callable from both. **Addendum posted back to the now-
  closed #3.**
- **No RPE parameter** — dropped from the schema entirely (`workouts-v1.md` §2,
  resolved); the earlier draft's `rpe?` param is removed.
- **`log_set` auto-start, resolved:** if no session is active, `log_set` silently
  starts one rather than erroring. If there *is* an active session, a new set logged
  within **90 minutes** of the last one auto-continues it, no question asked; past that
  gap, Claude asks whether it's a continuation or a new session, rather than guessing.
  This is separate from the existing 24h abandoned-session cleanup rule
  (`workouts-v1.md` §5), which handles a session nobody ever returns to at all, not
  this in-the-moment judgment call.

### 3.2 Workouts — templates and plans

Templates are created conversationally ("make me a push day: bench 3x8, OHP 3x10, …")
and rendered/edited on both surfaces via a shared `ui://swolemates/template.html`
component (named per `workouts-v1.md` §7).

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `create_workout_template` | Create a template in one call — Claude drafts the whole thing from the conversation and saves it. | `name`, `exercises[{exercise, sets, reps?, weight?, notes?}]` | **Component** (template preview, editable) + summary |
| `get_workout_template` / `list_workout_templates` | Look up one template by name/id, or list all. | `name_or_id` / — | **Component** (template view) + summary |
| `plan_workout` / `get_planned_workouts` | Schedule a template for a date, or read the upcoming schedule. | `template_id, date` / `range?` | **Component** (`ui://swolemates/planned.html`, "what's next") + summary |
| `search_exercises` / `add_custom_exercise` | Find exercises in the vendored catalog (now all 873, per `workouts-v1.md` §9), or add one that isn't there. | `query?, muscle_group?` / `name, muscle_group, equipment?` | **Text** — top matches with muscles/equipment/level; feeds template creation. No UI needed. |

Task-shaped because: one `create_workout_template` call captures a whole
conversational draft, instead of `create_template` + N × `add_template_exercise`.
Naming and shape here follow `workouts-v1.md` §8 exactly (it's the closed, fully-
resolved ticket for this domain) — this draft's earlier `save_workout_template`
(single tool for create+revise) and `get_planned_workout` (no schedule concept) are
both superseded.

- Exercise images are same-origin from FastAPI static (#15), so the plan component
  needs **no CSP domains** — consistent with the self-contained-bundle rule from #10.
- **Resolved:** templates use uniform `sets × reps @ weight` per exercise, not rep
  ranges or per-set prescriptions (`workouts-v1.md` §2, OQ2). Scheduling is real now,
  not name-based-only — `weekly_pattern` (day-of-week → template) generates
  `planned_workouts`, so `get_planned_workouts(range?)` is meaningfully date-aware.
  This directly answers what was §8 Q8 in this draft's own open-questions list.

### 3.3 Nutrition — logging and food facts

One generalized trackable model (#4) spans food, water, creatine, etc. One
`ui://swolemates/nutrition-day.html` component renders the day so far vs goals.

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `log_nutrition` | Record one or more trackable entries — a meal, a glass of water, creatine — in one call. Photo/text inference happens in-chat per #7 (Claude reads the image/description already in context; no backend AI call) before this tool is called with the resulting structured values. | `entries[]` (each: `trackable_key`, amounts), `date?`, `meal_type?` | **Component** (day vs goals) + summary ("1,430 kcal so far, 96 g protein — 64 g to go") |
| `search_food_facts` | Look up nutrition facts to *improve a log* — text search or barcode via Open Food Facts (per #11: v3 product endpoint + Search-a-licious, proxied through our backend). | `query?` or `barcode?` | **Text** — per-100g and per-serving numbers, serving size, brand. Task-shaped output: each hit is directly usable as a `log_nutrition` entry. |
| `save_meal_template` | Save a recurring meal/pattern ("my usual breakfast") — always save-from-log, no from-scratch builder (#4, resolved). | `name`, `entries[]`, `template_id?` (revise) | **Component** (swipeable totals-first stack, per #4's prototype) + summary |
| `log_meal_template` | Log a saved meal, optionally scaled — portion edits here affect only this log instance, never the template. | `name` or `template_id`, `multiplier?` (default 1), `date?`, `meal_type?` | **Component** (day vs goals — same payload as `log_nutrition`) + summary |
| `update_nutrition_log` | Edit a past nutrition entry conversationally ("actually that was a small coffee, not a large") — the nutrition equivalent of `update_workout`, model-visible for the same reason. | `log_id`, `updates` | Summary confirming the change |

Task-shaped because: `log_nutrition` takes a *message's worth* of intake, mixed types
allowed ("chicken and rice, big glass of water") — not one row per call. The
search→log pair is the vision's "search food facts to improve logs" loop: Claude
searches, picks serving-scaled numbers, then logs — two tool calls, zero forms.

- OFF calls go through the backend with a server-side barcode cache and the compliant
  User-Agent (#11) — the tool never exposes OFF's API shape to Claude, just normalized
  numbers.
- **Resolved (#4):** trackables are `logs`/`log_values`/`trackable_types`/`goals`, a
  generic header+values model — `trackable_key` replaces this draft's looser `type`
  discriminator. Photo-based logging (#7) needs no backend AI call: Claude infers
  values from the image already in its own chat context and calls `log_nutrition`
  directly with the result.

### 3.4 Goals

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `set_goals` | Set or update any subset of goals in one call, including which one (if any) drives your nutrition streak. | `goals[]` (each: `trackable_key`, `target_value`, `period`, `is_streak_target?`) | **Text** — restating all current goals after the change. |
| `get_goals` | Read current goals — cheap, called by the coach prompt at session start. | — | **Text** |

Task-shaped because: "let's target 2,200 kcal and 160 g protein" is one sentence and
one call. **Resolved:** goal-eligible trackables in v1 are the 5 legacy nutrition
fields (calories, protein_g, carbs_g, fat_g, fiber_g — #4); per-exercise strength
goals stayed out of scope for both #3 and #4, so `set_goals` covers nutrition only for
now.

- **`is_streak_target`, new (nutrition streaks, resolved this session):** at most one
  goal can carry `is_streak_target: true` per user, enforced service-side. That's the
  one trackable your daily nutrition streak counts against — calories for a
  weight-loss goal, protein for a muscle-building one, whichever actually matters for
  what you're working toward, set directly or inferred by Claude from your stated
  goal. Not marking any goal as the streak target is the opt-out — no separate toggle.
  This is a schema addition to the closed #4's `goals` table; **addendum posted back
  to #4.**

### 3.5 Trends, history, and the coaching backbone

Coaching is only as good as what these expose. Two tools: one wide (the dashboard), one
deep (per-exercise, for overload math).

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `get_progress` | The observation tool: workout streak, nutrition streak, PRs, volume trends, goal adherence over a period. This is what the coach prompt calls first. Own data only — see below. | `period?` (`week`/`month`/`quarter`, default month), `focus?` (`workouts`/`nutrition`/`all`) | **Component** (`ui://swolemates/progress.html` — trends dashboard) + a *dense* summary written for the model: streak lengths, recent PRs, adherence %, flat/rising/falling per lift |
| `get_exercise_history` | Deep history for one exercise: last N sessions' sets/weights/reps and the notes-for-next-time. The progressive-overload substrate. | `exercise`, `limit?` (default 5) | **Text** — table-like summary + the stored notes. Deliberately no UI: this is model food. |

Task-shaped because: `get_progress` answers "how are we doing?" in one call instead of
making Claude assemble it from list endpoints; `get_exercise_history` answers "what
should I lift today?". Names kept from this draft (not `workouts-v1.md`'s
`get_workout_history`/`get_exercise_progress`) specifically so nothing is named
"progress" twice — `get_progress` now spans both workouts and nutrition via `focus`.

- **Resolved:** PRs are heaviest-weight + e1RM (reps-at-weight dropped); workout
  streak is your weekly commitment count from `planned_workouts`, not a flat number;
  nutrition streak (new, this session) is daily, tied to whichever goal carries
  `is_streak_target` (§3.4) — both detailed in `workouts-v1.md` §6 and this doc's §3.4.
- **Resolved: no partner data in `get_progress` for v1**, full stop — not a `focus`
  option, not a parameter. Confirmed rather than reopened; partner visibility rules
  don't exist yet (#5/#12, still open), so there's nothing to build against.

### 3.6 Summary table

| # | Tool | Group | UI component | Text fallback |
|---|---|---|---|---|
| 1 | `start_workout` | workout session | workout-live.html | yes |
| 2 | `log_set` | workout session | workout-live.html | yes |
| 3 | `finish_workout` | workout session | workout-live.html | yes |
| 4 | `log_workout` | workout session | workout-summary.html | yes |
| 5 | `log_activity` | workout session | — (text only) | yes |
| 6 | `update_workout` | workout session | workout-summary.html | yes |
| 7 | `amend_last_log` | workout session / nutrition | — (text only) | yes |
| 8 | `create_workout_template` | templates | template.html | yes |
| 9 | `get_workout_template` / `list_workout_templates` | templates | template.html | yes |
| 10 | `plan_workout` / `get_planned_workouts` | templates | planned.html | yes |
| 11 | `search_exercises` / `add_custom_exercise` | templates | — (text only) | yes |
| 12 | `log_nutrition` | nutrition | nutrition-day.html | yes |
| 13 | `log_meal_template` | nutrition | nutrition-day.html | yes |
| 14 | `save_meal_template` | nutrition | nutrition-day.html | yes |
| 15 | `update_nutrition_log` | nutrition | nutrition-day.html | yes |
| 16 | `search_food_facts` | nutrition | — (text only) | yes |
| 17 | `set_goals` | goals | — (text only) | yes |
| 18 | `get_goals` | goals | — (text only) | yes |
| 19 | `get_progress` | trends | progress.html | yes |
| 20 | `get_exercise_history` | trends | — (text only) | yes |
| 21 | `whoami` (exists) | meta | — | yes |

App-only (not model-visible; iframe components call these directly, tmpx pattern):
`update_workout_entry`, `update_workout_template`, `get_active_workout`.

Six `ui://` resources (workout-live, workout-summary, template, planned,
nutrition-day, progress) — the #10 "one resource per feature, many tools share it"
shape, grown from four as the reconciliation surfaced `workout-summary.html` and
`planned.html` as their own resources (both named in `workouts-v1.md` §7). Every
component is a self-contained single-file bundle from `make apps`, no CSP domains
except the one declared exception for exercise images (`resourceDomains`, same-origin
— `workouts-v1.md` §7), re-renderable from any tool result.

## 4. How streak/PR celebrations surface

Per #14, gamification v1 = streaks + progressive-overload wins, no XP/levels/badges.

**Mechanism: a `celebrations` array in tool payloads, computed server-side in the
service layer.** `finish_workout`, `log_workout`, `log_activity`, and `log_nutrition`
results may include:

```json
"celebrations": [
  {"kind": "pr", "exercise": "Barbell Squat", "detail": "225x5 — previous best 220x5", "streak": null},
  {"kind": "streak", "detail": "12 workout days in a row", "streak": 12}
]
```

Three surfaces, one source of truth:

1. **The component** renders them inline (confetti-adjacent styling in the session
   recap — visual design belongs to #3's component work).
2. **The `summary` string** leads with them ("**New squat PR — 225x5!** Session
   logged: …"), so non-UI hosts and Claude's narration both get them for free.
3. **The coach prompt** (§6) instructs Claude to actually celebrate — the server states
   facts; the coach supplies the enthusiasm. No autonomous engine: nothing fires
   without a user-initiated tool call.

The same service function feeds the app's celebration surface later, keeping chat and
app consistent (#14: "PR celebrations in chat and app").

**Resolved:** PR/streak semantics are in §3.5. Nutrition does get its own streak —
daily, tied to whichever goal is marked `is_streak_target` (§3.4) — resolved this
session after initially leaning "no streak" and revisiting given it should track
whatever goal you're actually working toward, not a generic logging-consistency
metric.

## 5. What the server registers beyond tools

FastMCP 3.x registers **prompts** (`@mcp.prompt`) alongside tools and resources, and
claude.ai connectors surface a server's prompts to the user (prompt templates the user
invokes to start/steer a conversation). That's the reliable, shipped mechanism today,
so v1 coaching rides on **one MCP prompt** (§6).

**Skills over MCP (SEP-2640, `skill://` resource convention) is emerging but not
final** — it would let the server ship a full coach SKILL.md with references that
capable hosts auto-load. Worth watching, wrong thing to depend on for v1. **OPEN:**
revisit when SEP-2640 lands and claude.ai support is confirmed.

We should also *not* register: sampling-dependent features, app-exposed tools beyond
what components need, or resources other than the four `ui://` bundles.

## 6. The coach prompt (draft text)

Registered as `@mcp.prompt` named `coach` (title "Fitness coach session"), no
arguments — invoking it starts a coaching turn. Draft text:

> You are the user's fitness coach inside Swolemates, their workout and nutrition
> tracker. Be a coach, not a librarian: have a point of view, push gently, and always
> tie observations to their stated goals.
>
> **Start every coaching session by looking, not asking.** Call `get_goals` and
> `get_progress` (period: month) before saying anything substantive. When a workout is
> being planned or started, call `get_exercise_history` for the main lifts so your
> suggestions use their actual numbers.
>
> **Progressive overload is your default lens.** When they're about to repeat an
> exercise, compare against last time and suggest one concrete small step: +2.5–5 lb,
> +1 rep, or one extra set — one variable at a time, only when the last session's notes
> and reps say they're ready. If reps fell short or the notes say it felt bad, hold or
> reduce, and say why. Read their `notes_for_next_time` back to them at the start of a
> session — that's what the notes are for.
>
> **Push toward goals with their data, not generic advice.** "You're 40 g short of
> your protein target with one meal left" beats "eat more protein." If progress has
> stalled for several sessions, name it and propose a change (different rep range,
> deload week, swap variation) rather than letting it slide.
>
> **A plateaued weight gets a real recommendation, not just a flag.** If weight has
> held steady (roughly ±3 lb) for 14–21+ days while cutting, that's a classic sign of
> metabolic adaptation — don't just note it, propose a specific next step: tighten the
> deficit further, or take a structured refeed/diet break. Use judgment on which fits
> (how long the deficit's been sustained, anything in `coach_notes` or recent
> conversation about a planned break) and say why, the same way you'd explain a
> hold/reduce call on a lift. Weight targets are directional, never pass/fail — body
> composition means weight alone doesn't tell the whole story, so never treat a flat
> or rising weigh-in as a "miss" the way a calorie overshoot would be.
>
> **Celebrate real wins loudly and briefly.** When a tool result includes
> `celebrations`, lead with them — a PR or a streak deserves a sentence of genuine
> enthusiasm before anything else. Never invent a celebration the tools didn't report,
> and never guilt-trip about broken streaks; note it once, then focus forward.
>
> **Logging etiquette:** log what they tell you without making them repeat themselves —
> infer the exercise from context, use `search_food_facts` to fill in nutrition numbers
> instead of guessing, and confirm only genuinely ambiguous amounts. During an active
> workout keep replies to a phone-glance length: the numbers, the next suggestion, done.
>
> **Boundaries:** you are not a medical professional — for pain (as opposed to normal
> soreness), injury, or health conditions, tell them to see a professional and adjust
> the plan conservatively. Don't prescribe supplement doses or crash diets. If asked
> for something unsafe (e.g. extreme cuts), push back with the goal-aligned
> alternative.

**Resolved: this is the one fixed tone for v1**, no configurability, no
drill-sergeant-style parameter — cheap to adjust later purely by editing the prompt
text once it's actually been used.

**Resolved: always-on coaching nudges.** Coaching isn't gated behind explicitly
invoking `coach` — relevant tool descriptions (`finish_workout`, `log_workout`,
`log_nutrition`) carry a compressed version of the same instinct ("compare against
last time, mention it if notable") so some coaching happens by default in any
conversation, not only ones that invoke the prompt. The full `coach` prompt above is
still the deeper, session-opening version (`get_goals` + `get_progress` first, etc.);
the tool-description nudges are the lightweight always-on layer underneath it.

A second, lighter prompt (`log-my-day`, "dump everything I ate/did and log it") could
ride the same mechanism — proposed as a **maybe**, not core.

## 7. What this deliberately leaves out of v1

- **Partner-facing tools** — blocked on #12/#5.
- **Photo food logging as a separate tool concern** — resolved in #4/#7: it's not a
  distinct code path, just Claude inferring values in-chat before calling
  `log_nutrition` normally.
- **Autonomous coaching triggers** (scheduled check-ins, rule engines) — explicitly v2
  per #14.
- **A generic `query_history` tool** — tempting, but it's a REST mirror in disguise;
  `get_progress` + `get_exercise_history` cover the observation needs until proven
  otherwise.
- **Full delete** — resolved: chat gets `update_workout`, `update_nutrition_log`
  (edit a specific past record) and `amend_last_log` (undo the most recent one), not a
  general-purpose delete. Anything beyond "the most recent thing" or "a specific
  record I can name" still goes through the app.

## 8. Resolved decisions

All eight, resolved live with Michelle, 2026-08-11 (detail on each is inline in the
relevant section above; this is the index), plus the tool-list reconciliation with
`workouts-v1.md` this session started with:

0. ~~**Tool-list reconciliation.**~~ **Resolved:** `workouts-v1.md` wins wherever the
   two drafts named the same thing differently (§3.1–§3.2), with one deliberate
   reversal — `log_set` is model-visible, not app-only (§3.1).
1. ~~**Tool count comfort.**~~ **Resolved:** no collapsing; count grew to 24 during
   reconciliation and that's fine — Claude's tool selection doesn't meaningfully
   degrade until well past this range with clear descriptions, so trimming for the
   number's own sake isn't worth it (§3.6).
2. ~~**No delete from chat — really?**~~ **Resolved:** `update_workout` /
   `update_nutrition_log` (edit a specific record) plus a new `amend_last_log` (undo
   the most recent one) — not a general delete (§3.1, §3.3, §7).
3. ~~**`log_set` auto-start.**~~ **Resolved:** auto-starts a session if none active;
   auto-continues an open one within 90 minutes of the last set with no question;
   past that, Claude asks rather than guesses (§3.1).
4. ~~**Coach prompt tone.**~~ **Resolved:** one fixed tone, the §6 draft as written, no
   configurability (§6).
5. ~~**Prompt vs. always-on coaching.**~~ **Resolved:** always-on — relevant tool
   descriptions carry a compressed coaching nudge so some coaching happens without
   invoking `coach` explicitly (§6).
6. ~~**Nutrition streaks.**~~ **Resolved:** yes, a daily streak tied to whichever goal
   is marked `is_streak_target` — the trackable that actually matters for your stated
   aim, not a generic logging-consistency metric (§3.4, §4).
7. ~~**Partner data in `get_progress`.**~~ **Resolved:** excluded entirely for v1, own
   data only, confirmed rather than reopened (§3.5).
8. ~~**`get_planned_workout` scheduling.**~~ **Resolved automatically:** `weekly_pattern`
   (from the closed #3) already gives templates day-of-week assignment; no separate
   decision needed here (§3.2).
