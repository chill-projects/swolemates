# Proposal: Claude tool surface for v1

> **Status: PROTOTYPE — a reaction artifact for ticket
> [#6](https://github.com/chill-projects/swolemates/issues/6), not a decision.**
> Everything here is a straw man for Will to mark up. Items tagged **OPEN** depend on
> the workouts ([#3](https://github.com/chill-projects/swolemates/issues/3)) and
> nutrition ([#4](https://github.com/chill-projects/swolemates/issues/4)) designs still
> in flight and are deliberately left unspecified.

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

Sixteen tools across five groups. Names are `verb_noun`, matching `log_workout` from
AGENTS.md. `whoami` already exists and stays.

### 3.1 Workouts — logging and the in-workout flow

The in-workout flow is a *conversation*, not a form: "starting legs day" → sets logged
one message at a time between actual sets at the gym → "done". Three tools share one
`ui://swolemates/workout-session.html` component that renders the running session
(exercise checklist, sets logged so far, last-time numbers alongside for overload).

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `start_workout` | Begin a workout session, from a template or ad hoc. | `template_id?` or `name?`, `date?` (defaults today) | **Component** (session view) + summary incl. last-time numbers per planned exercise |
| `log_set` | Record one set (or several) against the active session. | `exercise`, `weight?`, `reps`, `sets?` (default 1), `rpe?`, `note?` | **Component** (updated session) + summary comparing to last session's same exercise |
| `finish_workout` | Close the session; capture notes-for-next-time; compute PRs/streaks. | `notes_for_next_time?`, `session_id?` | **Component** (session recap incl. celebrations) + summary |
| `log_workout` | One-shot: record an already-completed workout in a single call (retroactive or "I did X, Y, Z"). | `name?`, `date?`, `exercises[]` (each with sets/weights/reps), `notes?` | **Component** (recap) + summary; same celebration path as `finish_workout` |

Task-shaped because: each maps to a sentence someone says mid-workout, not a table.
`log_set` deliberately accepts one exercise's worth at a time — that's the message
grain of a person at the gym. `log_workout` exists so past workouts don't require
faking a live session.

- **OPEN (#3):** the session/actuals schema (per-set actuals are a hard requirement in
  #3), whether sessions are first-class rows or derived, RPE and rest-time fields, and
  how "active session" is resolved when none was started (`log_set` with no session —
  auto-start? error?).
- **OPEN (#3):** whether `log_set` should be `visibility=["model","app"]` so the
  component's own "+ set" button calls it directly (the tmpx pattern) — almost
  certainly yes, but the component design belongs to #3.

### 3.2 Workouts — templates and plans

Templates are created conversationally ("make me a push day: bench 3x8, OHP 3x10, …")
and rendered/edited on both surfaces via a shared `ui://swolemates/workout-template.html`
component.

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `save_workout_template` | Create **or** revise a template in one call — Claude drafts the whole thing from the conversation and saves it. | `name`, `exercises[]` (exercise, sets, reps/rep-range, notes), `template_id?` (present = revise) | **Component** (template preview, editable) + summary |
| `get_planned_workout` | Show what's planned — the template for a day/name, enriched with exercise descriptions and images. | `template_id?` or `name?` or `date?` | **Component** (plan view with exercise images) + summary listing exercises |
| `search_exercises` | Find exercises in the vendored catalog (free-exercise-db per #15) so templates use canonical names and get images. | `query`, `muscle_group?`, `equipment?` | **Text** — top matches with muscles/equipment/level. No UI needed; this feeds template creation. |

Task-shaped because: one `save_workout_template` call captures a whole conversational
draft, instead of `create_template` + N × `add_template_exercise`. Revision is the same
verb with an id — "tweaking" per the vision is just re-saving.

- Exercise images are same-origin from FastAPI static (#15), so the plan component
  needs **no CSP domains** — consistent with the self-contained-bundle rule from #10.
- **OPEN (#3):** template schema (rep ranges vs fixed reps, progression notes,
  scheduling/day-assignment — is `date?` on `get_planned_workout` even meaningful, or
  are plans schedule-less in v1?).

### 3.3 Nutrition — logging and food facts

One generalized trackable model (#4) spans food, water, creatine, etc. One
`ui://swolemates/nutrition-day.html` component renders the day so far vs goals.

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `log_nutrition` | Record one or more trackable entries — a meal, a glass of water, creatine — in one call. | `entries[]` (each: `type` discriminator, `name?`, amounts — calories/macros for food, quantity+unit otherwise), `date?`, `meal?` | **Component** (day vs goals) + summary ("1,430 kcal so far, 96 g protein — 64 g to go") |
| `search_food_facts` | Look up nutrition facts to *improve a log* — text search or barcode via Open Food Facts (per #11: v3 product endpoint + Search-a-licious, proxied through our backend). | `query?` or `barcode?` | **Text** — per-100g and per-serving numbers, serving size, brand. Task-shaped output: each hit is directly usable as a `log_nutrition` food entry. |
| `save_meal_template` | Save a recurring meal/pattern ("my usual breakfast") for one-line logging later. | `name`, `entries[]`, `template_id?` (revise) | **Component** (template preview) + summary |
| `log_meal_template` | Log a saved meal, optionally scaled. | `name` or `template_id`, `multiplier?` (default 1), `date?`, `meal?` | **Component** (day vs goals — same payload as `log_nutrition`) + summary |

Task-shaped because: `log_nutrition` takes a *message's worth* of intake, mixed types
allowed ("chicken and rice, big glass of water") — not one row per call. The
search→log pair is the vision's "search food facts to improve logs" loop: Claude
searches, picks serving-scaled numbers, then logs — two tool calls, zero forms.

- OFF calls go through the backend with a server-side barcode cache and the compliant
  User-Agent (#11) — the tool never exposes OFF's API shape to Claude, just normalized
  numbers.
- **OPEN (#4):** the trackable discriminator vocabulary and units model; whether water/
  supplements have their own goals; the meal slot enum; photo-based logging
  ([#7](https://github.com/chill-projects/swolemates/issues/7)) is out of this tool
  surface until that ticket lands.

### 3.4 Goals

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `set_goals` | Set or update any subset of goals in one call — calories, macros, water, workout frequency, per-exercise targets. | `goals[]` (each: `kind`, `target`, `unit?`, `exercise?`) | **Text** — restating all current goals after the change. (Progress-vs-goal visuals live in `get_progress` and the nutrition component; a goals list doesn't need UI.) |
| `get_goals` | Read current goals — cheap, called by the coach prompt at session start. | — | **Text** |

Task-shaped because: "let's target 2,200 kcal and 160 g protein, and I want to squat
315 by fall" is one sentence and one call. **OPEN (#3/#4):** the goal `kind`
vocabulary, especially per-exercise strength goals vs body-weight goals.

### 3.5 Trends, history, and the coaching backbone

Coaching is only as good as what these expose. Two tools: one wide (the dashboard), one
deep (per-exercise, for overload math).

| Tool | Purpose | Key parameters | Returns |
|---|---|---|---|
| `get_progress` | The observation tool: streaks, consistency calendar, PRs, volume trends, goal adherence over a period. This is what the coach prompt calls first. | `period?` (`week`/`month`/`quarter`, default month), `focus?` (`workouts`/`nutrition`/`all`) | **Component** (`ui://swolemates/progress.html` — trends dashboard, consistency calendar ported from legacy) + a *dense* summary written for the model: streak lengths, recent PRs, adherence %, flat/rising/falling per lift |
| `get_exercise_history` | Deep history for one exercise: last N sessions' sets/weights/reps and the notes-for-next-time. The progressive-overload substrate. | `exercise`, `limit?` (default 5) | **Text** — table-like summary + the stored notes. Deliberately no UI: this is model food. |

Task-shaped because: `get_progress` answers "how are we doing?" in one call instead of
making Claude assemble it from list endpoints; `get_exercise_history` answers "what
should I lift today?".

- **OPEN (#3/#4):** PR definition (per-rep-count max? e1RM? both), streak definition
  (calendar days? scheduled-days hit?), and whether `get_progress` includes partner
  comparison — partner data visibility is
  [#12](https://github.com/chill-projects/swolemates/issues/12)/[#5](https://github.com/chill-projects/swolemates/issues/5)'s
  call; this proposal assumes **no partner data in v1 tools** until #12 resolves.

### 3.6 Summary table

| # | Tool | Group | UI component | Text fallback |
|---|---|---|---|---|
| 1 | `start_workout` | workout session | workout-session.html | yes |
| 2 | `log_set` | workout session | workout-session.html | yes |
| 3 | `finish_workout` | workout session | workout-session.html | yes |
| 4 | `log_workout` | workout session | workout-session.html | yes |
| 5 | `save_workout_template` | templates | workout-template.html | yes |
| 6 | `get_planned_workout` | templates | workout-template.html | yes |
| 7 | `search_exercises` | templates | — (text only) | yes |
| 8 | `log_nutrition` | nutrition | nutrition-day.html | yes |
| 9 | `log_meal_template` | nutrition | nutrition-day.html | yes |
| 10 | `save_meal_template` | nutrition | nutrition-day.html | yes |
| 11 | `search_food_facts` | nutrition | — (text only) | yes |
| 12 | `set_goals` | goals | — (text only) | yes |
| 13 | `get_goals` | goals | — (text only) | yes |
| 14 | `get_progress` | trends | progress.html | yes |
| 15 | `get_exercise_history` | trends | — (text only) | yes |
| 16 | `whoami` (exists) | meta | — | yes |

Four `ui://` resources, one per feature — the #10 "one resource per feature, many tools
share it" shape. Every component is a self-contained single-file bundle from
`make apps`, no CSP domains, re-renderable from any tool result.

## 4. How streak/PR celebrations surface

Per #14, gamification v1 = streaks + progressive-overload wins, no XP/levels/badges.

**Mechanism: a `celebrations` array in tool payloads, computed server-side in the
service layer.** `finish_workout`, `log_workout`, and `log_nutrition` results may
include:

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

**OPEN (#3/#4):** exact PR/streak semantics (see §3.5) and whether nutrition has its
own streak (logging streak? goal-hit streak?).

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

Two open styling questions on this text are in §8. A second, lighter prompt
(`log-my-day`, "dump everything I ate/did and log it") could ride the same mechanism —
proposed as a **maybe**, not core.

## 7. What this deliberately leaves out of v1

- **Partner-facing tools** — blocked on #12/#5.
- **Photo food logging** — blocked on #7.
- **Autonomous coaching triggers** (scheduled check-ins, rule engines) — explicitly v2
  per #14.
- **A generic `query_history` tool** — tempting, but it's a REST mirror in disguise;
  `get_progress` + `get_exercise_history` cover the observation needs until proven
  otherwise.
- **Delete/undo tools** — the interaction model says fixing wrong records is the
  *app's* job ("shared components so a wrong result can be edited in place"). Chat can
  re-log; the app edits. If this feels wrong in practice, an `amend_last_log` tool is
  the task-shaped escape hatch — flagged in §8.

## 8. Open questions for Will

1. **Tool count comfort:** 16 tools is on the larger side for a connector list.
   Claude's tool-selection is generally fine at this size, but would you rather
   collapse the meal-template pair (`save_meal_template`/`log_meal_template`) into
   `log_nutrition`/`save_workout_template`-style overloads to get under ~13?
2. **No delete from chat — really?** §7 assumes wrong logs get fixed in the app.
   Comfortable, or do you want an `amend_last_log` (fix/remove the most recent entry)
   in v1? "Claude, that was 8 reps not 10" feels like it wants to work in chat.
3. **`log_set` auto-start:** if you say "bench 185x8" with no active session, should
   the tool silently start one (frictionless) or should Claude be forced to call
   `start_workout` first (explicit sessions)? I lean auto-start; flagging because it
   shapes #3's session model.
4. **Coach prompt tone:** the §6 draft is "encouraging but pushy." Want it meaner
   (drill-sergeant option as a prompt argument?) or is one fixed tone fine for v1?
5. **Prompt vs always-on coaching:** the coach behavior only activates when you invoke
   the `coach` prompt (or ask for coaching). Should the *tool descriptions themselves*
   carry a slimmed-down coaching nudge (e.g. `finish_workout`'s description telling
   Claude to compare against last session) so some coaching happens even without the
   prompt? Cheap to add, slightly opinionated.
6. **Nutrition streaks:** workouts have an obvious streak; does nutrition get one
   (days-logged? days-under-calorie-goal?), or is that noise?
7. **Partner data in `get_progress`:** excluded pending #12 — confirm that's the right
   default rather than read-only partner summaries in chat.
8. **`get_planned_workout` scheduling:** do templates get day-of-week assignments in
   v1 (so "what's today's workout" resolves), or is it name-based only ("show me push
   day")? Depends on #3; your call shapes the tool's parameters.
