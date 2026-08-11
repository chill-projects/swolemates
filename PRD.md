# Swolemates — Product Requirements Document

**Status:** Draft — v1 scope is being resolved live on the [wayfinder map](https://github.com/chill-projects/swolemates/issues/1); this doc is a snapshot of that map, not a substitute for it.
**Owner:** Michelle Zhuang
**Last updated:** 2026-08-10

> This is a full rewrite of the original 2026-07-22 draft, which described a Next.js + Supabase app. That stack was scrapped for the platform in `docs/design.md` (FastAPI + FastMCP backend, Claude connector, Vite SPA) — see `AGENTS.md`. Everything below reflects the current architecture and the decisions made so far while porting the legacy app onto it. **The map (issue #1) is the live source of truth**; when a linked ticket resolves and this doc hasn't caught up, trust the ticket.

---

## 1. Overview

Swolemates is a mobile-first app that combines calorie/macro tracking, workout logging, and AI fitness coaching, reachable two ways: a **web app** (installable PWA) and **Claude itself**, via a remote MCP connector. Both front doors share one backend, one database, and — for anything that needs a rich UI — literally the same interactive component. It's built for personal use by the author and their partner, and doubles as a coding-practice project.

**Why build this instead of using MyFitnessPal / Cronometer / Fitbod / Strong:**
- Existing apps are bloated/ad-heavy for what's actually needed day to day.
- No existing app combines nutrition tracking and workout coaching into one coherent experience.
- Claude-as-coach is a fundamentally different interaction model than any of the above — coaching happens by chatting, not by reading a screen the app generated.
- It's partly a deliberate coding-practice exercise.

---

## 2. Users

Two users: the author and their partner. Each has a fully separate account (WorkOS-authenticated) with their own goals, food logs, and workout history. Accounts can be linked to each other for accountability purposes (§5.4) — the invite-code mechanism itself is being redesigned for WorkOS identities in [Partner v1](https://github.com/chill-projects/swolemates/issues/5) (open). Not designed for more than two linked users in v1.

---

## 3. Platform & Architecture

One backend container, two front doors, converging on one service layer — see `docs/design.md` for the full design; summary:

| Piece | Decision |
|---|---|
| Backend | FastAPI, mounting `/api` (REST), `/mcp` (FastMCP 3.x connector), and the built SPA as static files |
| Frontend | Vite + React + TypeScript SPA — **not** Next.js/SSR; built in CI into the backend image, no separate host |
| Shared UI | MCP Apps (`ui://` components, `_meta.ui.*`) — one bundle renders identically inside a Claude conversation and inside the SPA |
| Database | Postgres (Railway), one schema, SQLAlchemy 2.x + Alembic |
| Auth | WorkOS AuthKit (OAuth 2.1) for both surfaces — `sub` stamped on every row is the permission model; see `docs/auth.md` |
| Deploy | Railway, blue-green via `/health`, GitHub Actions CI (ruff/pytest/tsc/generated-client-drift check) |
| Budget | ~$5–10/mo (Railway + Postgres); WorkOS free under 1M MAU; no metered AI cost — see §6 |
| Camera access | Via `<input type="file" accept="image/*" capture="environment">`, same rationale as before: reliable inside installed PWAs on iOS Safari and Android Chrome without a live-preview widget |

**PWA scope** (installability, service worker, iOS install banner) is carried forward as an intent from the original draft but not yet locked for v1 — see [PWA scope for v1](https://github.com/chill-projects/swolemates/issues/8) (open).

---

## 4. V1 Scope

Per Will's [product vision](https://github.com/chill-projects/swolemates/issues/1#issuecomment-5136252340) and the closed [Interaction model](https://github.com/chill-projects/swolemates/issues/14) ticket: **chat** owns logging, template creation/tweaks, goal setting, trends/history, food-fact search, and coaching; the **app** owns tweaking/editing records, visualizing recent activity, and partner results, mobile-first. Templates are created conversationally and edited identically on both surfaces via shared `ui://` components — "a wrong result is editable in place," not a chat-only artifact.

### 4.1 Accounts & Onboarding

- WorkOS AuthKit signup/login (replaces the original Supabase email/password plan).
- Profile data captured at first login (goals, routine) — exact fields and flow are open: [Onboarding and profile: what carries into v1](https://github.com/chill-projects/swolemates/issues/9).

### 4.2 Nutrition — decided

Resolved live with Will; full detail on [Nutrition v1](https://github.com/chill-projects/swolemates/issues/4).

- **Generalized trackable model**: `logs` (header) + `log_values` (one row per metric) + `trackable_types` (seeded data — adding sodium is a seed row, never a migration) + `goals`. One photo estimate writes 5 `log_values` under one `logs` row; a water log writes 1.
- **Meal templates**: save-from-log only (no from-scratch builder), multi-item bundles, editable on both surfaces. UX: swipeable totals-first stack (prototyped, 3 variants compared).
- **Logging paths, no metered AI call anywhere**: photo → Claude reads the image already in its own chat context and infers structured values (no backend vision-API call — see [#7](https://github.com/chill-projects/swolemates/issues/7)); barcode/search → Open Food Facts v3 (see [#11](https://github.com/chill-projects/swolemates/issues/11)), barcode decoded optically by Claude in chat or client-side (`@zxing/browser`) in the app; no match → Claude infers from a text description in chat, or the full manual-entry form in the app.
- **Goals**: 5 legacy fields only (`calories`, `protein_g`, `carbs_g`, `fat_g`, `fiber_g`) are goal-eligible in v1; everything else trackable but not targetable yet. Calorie ring + a bar per goal-eligible trackable, generalized from legacy `TodaySummary.tsx`.
- **Split out**: TDEE-assisted goal calculation + weight-as-a-trackable graduated into its own ticket, [#19](https://github.com/chill-projects/swolemates/issues/19) (open).

### 4.3 Workout logging — decided

Domain model and UX fully resolved on [Workouts v1](https://github.com/chill-projects/swolemates/issues/3); doc + models sketch on PR #17 (`proto/workouts-v1`).

- **Templates and live workouts are separate table families** — `workout_templates`/`template_exercises` (uniform `sets × reps @ weight` per exercise) vs. `workouts`/`workout_exercises`/`workout_sets` (per-set actuals, `completed_at IS NULL` = in-progress). `start_workout` copies template targets into `prescribed_*` once per session, so a template edit never rewrites history.
- **Supersets**: `superset_group` on both exercise tables — surfaced as a real requirement during UI prototyping, not originally scoped.
- **In-workout mode** (mobile-first, the centerpiece): scrollable accordion, grouped by superset; sets are open-ended (add/remove freely, no fixed count); progressive-overload framing ("last time: 135lbs × 8,8,7" + notes-for-next-time) right where you pick the weight. No rest timer or duration display in v1. Decided after comparing 4 layouts in a throwaway prototype.
- **Units**: canonical storage in lbs, per-user display preference for conversion (the preference field itself belongs to onboarding, [#9](https://github.com/chill-projects/swolemates/issues/9)).
- **A standing weekly split** (`weekly_pattern`: day-of-week → template) generates each week's `planned_workouts`; no RRULE-style recurrence engine. Editing a given week doesn't touch the pattern.
- **Streaks are commitment-based**, not a flat number: the target is however many workouts you commit to for the week (from `planned_workouts`, locked once generated); success is a pure count of completions reaching that target, regardless of which day or whether it traces back to a specific planned session.
- **PR celebrations**: heaviest weight + e1RM only (not reps-at-weight); `personal_records` is a mutable current-record cache, not an append-only log, so a correction to a past set (via the now-model-visible `update_workout`) can't leave a stale PR standing.
- Exercise catalog seeds the **full 873-exercise** free-exercise-db dataset at launch, not just the 40 legacy exercises.

### 4.4 Partner accountability

- Concept unchanged from the original draft: each partner sees the other's workout streaks/frequency/trends only, **never** food logs or weight — enforced below the UI.
- Invite-code linking mechanism over WorkOS identities: [Partner v1: linking and dashboard](https://github.com/chill-projects/swolemates/issues/5) (open).
- Enforcement mechanism — service-layer only (current pattern) vs. adding a DB-level boundary (SQL function / RLS-style) — is a deferred decision from `docs/design.md` §4, now its own ticket: [Partner-privacy enforcement approach](https://github.com/chill-projects/swolemates/issues/12) (open).

### 4.5 Claude tool surface — decided

Resolved on [#6](https://github.com/chill-projects/swolemates/issues/6) (PR #18, `docs/proposals/claude-tools-v1.md`): 24 task-shaped tools (grew from an initial 16 once reconciled against the closed workouts ticket's own tool list — not trimmed back, since count itself wasn't the risk), 6 shared `ui://` components, the `celebrations` mechanism, and one fixed-tone `coach` MCP prompt with always-on nudges baked into relevant tool descriptions too (not gated behind explicitly invoking the prompt).

- `log_set` is model-visible — texting a set mid-workout ("bench 185x8") works from chat, auto-starting a session if none is active and auto-continuing one within 90 minutes of the last logged set with no question asked; past that, Claude asks rather than guesses.
- Chat-side corrections are `update_workout`/`update_nutrition_log` (edit a specific past record) plus a lightweight `amend_last_log` ("undo that," no id required) — not a general delete.
- Nutrition gets a daily streak too, tied to a new `is_streak_target` flag on `goals`: whichever goal is marked drives the streak (calories for weight loss, protein for muscle building), not a generic logging-consistency metric.
- `get_progress` excludes partner data entirely for v1 — nothing to build against until partner visibility (§4.4) resolves.

### 4.6 PWA

Installability (manifest/icons), app-shell-only service worker, iOS "Add to Home Screen" banner — how much of this ships in v1 vs. later is open: [PWA scope for v1](https://github.com/chill-projects/swolemates/issues/8).

---

## 5. Exercise & food data sources

- **Exercises**: [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (public domain), vendored as a static dataset at seed time — no runtime API, no external network from inside a component's sandbox. All 40 legacy starter exercises resolve against it. ([research ticket](https://github.com/chill-projects/swolemates/issues/15))
- **Food**: Open Food Facts API v3 + Search-a-licious, no auth required, proper User-Agent, 15/10 req/min limits. ([research ticket](https://github.com/chill-projects/swolemates/issues/11))

---

## 6. Coaching: what's in v1 vs. deferred

This is a sharper split than the original draft's "coaching is all v2," because chat-based coaching turns out to need **no dedicated feature** — Claude coaches simply by having the right tools:

- **In v1**: Claude, in its own chat (never embedded in the website), coaches conversationally using tools that expose goals, history, and trends, plus a fixed-tone `coach` MCP prompt and always-on nudges in relevant tool descriptions ([#6](https://github.com/chill-projects/swolemates/issues/6)). This is "push the user toward their goals and progressive overload" as an emergent property of Claude reasoning over real data — no rule engine to build.
- **Deferred to v2**: the original PRD's §8-style **autonomous, codified rule engine** — hard-coded thresholds ("+2.5–5 lbs after 2 consecutive sessions," deload every 4th week, momentum/recovery state machine driven by a daily self-report check-in). That design is preserved below as a reference for when it's picked back up; it needs real v1 usage data to validate its thresholds against.

### V2 — Autonomous Coaching Rule Engine (specified, deferred)

<details>
<summary>Full spec, collapsed — not built in v1</summary>

**Onboarding (learn the user once):** primary + optional secondary fitness goal, current routine/equipment/availability, confirmed back as a summary.

**Daily decision engine**, self-reported streak/recovery data (no wearables):
- 3+ workouts in a row → push slightly harder; 5+ consecutive days → watch for overtraining via self-report, not biometrics
- Missed 1 day → no comment; 2–3 days → gentle acknowledgment; 4–7 days → reset to ~20–30 min at 60%; 2+ weeks → full reset to Week 1, framed as a fresh start
- Soreness/fatigue self-report drives active-recovery routing

**Progressive overload by goal type**: strength (weight bump after 2 clean sessions, deload every 4th week), weight loss (cardio/step/frequency ramps, weekly-average bodyweight trend), running (10% rule, easy/tempo/long rotation, recovery weeks), general fitness (frequency + duration ramps, modality mixing).

**Recovery signal**: daily self-report check-in (energy 1–5, soreness by muscle group, sleep quality 1–5) substitutes for wearable/HealthKit data, which is out of scope — a real integration is a possible future upgrade that wouldn't change the engine's shape.

**Build-order rationale**: this layers on top of real v1 logging data so its thresholds can be validated against actual usage rather than designed blind.

</details>

---

## 7. V1 Success Criteria

- Both users can independently sign up via WorkOS, complete onboarding, and link their accounts.
- Both users can log a full workout with per-set weight/reps (including supersets and open-ended sets) and see it in history, from either surface.
- Both users can log food via barcode/database search, photo, and text description — all funneling into one shared, editable card, no metered backend AI call.
- Claude, in chat, can answer trend/progress questions and coach conversationally off real logged data.
- Each user can see the other's workout streak/frequency stats, and a direct attempt to query the other's food logs or weight entries returns nothing.
- (Pending [#8](https://github.com/chill-projects/swolemates/issues/8)) The app installs to the homescreen and functions in standalone mode.

---

## 8. Where the detail lives

This doc stays intentionally high-level — an index, not the store. For anything below the summary line:

- **Platform/architecture detail**: `docs/design.md`, `docs/auth.md`
- **Per-feature domain model + UX detail**: the linked ticket above, and its linked proposal doc/PR if one exists (`docs/proposals/*.md`)
- **What's decided vs. still open, at a glance**: the [wayfinder map](https://github.com/chill-projects/swolemates/issues/1) — its "Decisions so far" and open child issues are more current than this doc will ever be in real time

### Open tickets, as of this writing

| Ticket | Question |
|---|---|
| [#5 Partner v1](https://github.com/chill-projects/swolemates/issues/5) | Invite/link mechanism + dashboard over WorkOS identities |
| [#8 PWA scope](https://github.com/chill-projects/swolemates/issues/8) | How much of §3's PWA intent ships in v1 |
| [#9 Onboarding](https://github.com/chill-projects/swolemates/issues/9) | What profile data v1 still collects, and when |
| [#12 Partner-privacy enforcement](https://github.com/chill-projects/swolemates/issues/12) | Service-layer isolation vs. a DB-level boundary |
| [#13 Execution order](https://github.com/chill-projects/swolemates/issues/13) | Build order, what's cut if anything, definition of done per slice |
| [#19 TDEE + weight tracking](https://github.com/chill-projects/swolemates/issues/19) | Goal-calculation assist + weight as a trackable |

---

## 9. Future Considerations

- The V2 autonomous coaching rule engine (§6).
- Streak/consistency-calendar specifics — sharpens once workouts + partner designs land.
- Live-update patterns beyond a user's own data (e.g. partner dashboard updating when the partner logs).
- Push notifications — stretch goal, revisit once PWA scope resolves.
- A real wearable integration (Apple Health, Whoop, Oura) as an upgrade to the V2 recovery signal.
- Whether any legacy Supabase data needs migrating, or v1 starts empty.
- Cost monitoring if usage patterns ever approach a metered AI call again (currently none exist in the design).
