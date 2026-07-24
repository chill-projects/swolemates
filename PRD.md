# Swolemates — Product Requirements Document

**Status:** Draft — v1 scoped, v2 (AI coach) specified but deferred
**Owner:** Michelle Zhuang
**Last updated:** 2026-07-22

---

## 1. Overview

Swolemates is a mobile-first Progressive Web App that combines calorie/macro tracking, workout logging, and (in v2) an AI fitness coaching layer. It's built for personal use by the author and their partner, and doubles as a coding-practice project.

**Why build this instead of using MyFitnessPal / Cronometer / Fitbod / Strong:**
- Existing apps are bloated/ad-heavy for what's actually needed day to day.
- No existing app combines nutrition tracking and workout coaching into one coherent experience.
- It's partly a deliberate coding-practice exercise.

---

## 2. Users

Two users: the author and their partner. Each has a fully separate account with their own goals, food logs, and workout history. Accounts can be linked to each other for accountability purposes (see §5.4). This is not designed for more than two linked users in v1, though the invite-code mechanism doesn't hard-code that limit.

---

## 3. Platform & Constraints

| Constraint | Decision |
|---|---|
| Platform | Progressive Web App (PWA) — installable to homescreen on iOS and Android, no native app store distribution |
| Why PWA over React Native | No wearable/HealthKit integration is planned, which removes the main reason to go native. PWA avoids the $99/yr Apple Developer fee and app-store review, and iterates faster for a two-person coding-practice project. |
| Budget | Free/near-free only. Backend and third-party APIs should default to free tiers; the only meaningfully metered cost is Claude API usage for photo-based food estimation, which is pennies at 2-user scale. |
| Camera access | Via `<input type="file" accept="image/*" capture="environment">` — works reliably inside installed PWAs on both iOS Safari and Android Chrome without the flakiness of a live camera preview. |

---

## 4. Tech Stack

- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS
- **Backend:** Supabase (Postgres + Auth + Storage), free tier
- **PWA tooling:** `@serwist/next` for the service worker (actively maintained; the classic `next-pwa` is not)
- **Nutrition database:** Open Food Facts (free, no API key, barcode + text search)
- **AI:** Claude API (`claude-sonnet-5`) for photo-based food estimation — chosen over Opus given the stated budget constraint; still fully capable for this task and supports vision + structured JSON output in the same request.

---

## 5. V1 Scope — Requirements

V1 is deliberately limited to **logging + partner accountability**. The AI coaching layer (§8) is specified but explicitly deferred to v2, because its rules need real logged data to design and test against.

### 5.1 Accounts & Onboarding

- Standard email/password (or magic link) signup via Supabase Auth.
- On first login, capture: primary goal, secondary goal (optional), current routine description. This data is captured in v1 but not acted upon until v2's coaching layer exists.
- A user cannot be re-shown onboarding once completed.

### 5.2 Workout Logging

- Users log workouts made up of one or more exercises, each with one or more **sets**.
- Each set records **actual weight × actual reps** — not just "workout completed." This granularity is a hard requirement: any future auto-progression logic (v2) needs to know whether a prescribed set was actually hit, and a simple completion checkbox can't answer that.
- An exercise catalog (name + muscle group + equipment) is seeded with ~40 common exercises; users can add custom exercises.
- Workout history is viewable per-user.

### 5.3 Food Logging

Two logging paths, in priority order:

1. **Barcode / database search (primary)** — via Open Food Facts, for packaged/branded food. Free, no API key, but coverage is spotty for homemade or restaurant food — hence path 2.
2. **Photo-based AI estimation (fallback)** — for anything not in the database. The user photographs their food; Claude (vision + structured JSON output) returns a per-item estimate of calories/protein/carbs/fat, **each field individually tagged with a confidence level (low/medium/high)**.
   - The estimate is shown as an **editable draft**, not auto-logged. Low-confidence fields are visually flagged so the user knows exactly what to double-check before saving — this is intentionally more granular than a blanket "confirm everything" step, since photo-based portion/ingredient estimation is inherently imprecise (routinely off by 20–40% on portion size alone).
   - Photos are resized client-side (~1024px long edge) before upload to control token cost.

All food logs (regardless of source) are **strictly private to the logging user** — see §5.4.

### 5.4 Partner Accountability

- Two accounts link via a **one-time invite code/link** (not phone/email lookup, not hardcoded) — one user generates a code, the other redeems it after signing up.
- Once linked, each partner can see the **other's**: workout streaks, workout completion frequency, and high-level trend data.
- Each partner **cannot** see the other's detailed food logs or weight entries under any circumstance — this is enforced at the database (RLS) layer via a restricted aggregate function, not just hidden in the UI. A direct API/DB query for the partner's food logs must return zero rows.

### 5.5 PWA Requirements

- Installable to homescreen on iOS 16.4+ and Android Chrome, with manifest + Apple-specific meta tags (iOS partially ignores manifest icons).
- Service worker caches only the static app shell — **never** Supabase or Open Food Facts responses, since this is a mutation-heavy, data-current app where stale cached food/workout data would actively mislead the user.
- No programmatic install prompt exists on iOS — the app must show its own "tap Share → Add to Home Screen" instructional banner.
- Push notifications (e.g. streak reminders) are a stretch goal, not a v1 requirement, given the limited reliability of iOS PWA push.

---

## 6. Data Model Summary

(Full schema lives in `supabase/migrations/`, not duplicated here — this is the shape.)

| Table | Purpose | Partner visibility |
|---|---|---|
| `profiles` | goal, secondary goal, routine, onboarding state | Name/avatar only, via a public view |
| `partner_invites` / `partner_links` | invite code lifecycle + the bidirectional link | N/A (own invites only) |
| `exercises` | shared catalog + user custom entries | Shared catalog |
| `workouts` / `workout_exercises` / `workout_sets` | per-set actual weight × reps | Aggregate stats only, via a `SECURITY DEFINER` RPC — never raw rows |
| `food_logs` | calories/macros, source, per-field confidence for photo-based entries | **None — zero partner access, no exceptions** |
| `weight_entries` | body weight over time | **None — zero partner access, no exceptions** |

The partner-visible workout summary (streak, weekly/monthly completion counts, last workout date) is exposed only through a database function that verifies the caller is actually linked to the target user before returning anything — this is a security boundary enforced in Postgres, not something the frontend can accidentally bypass.

---

## 7. V1 Success Criteria

- Both users can independently sign up, complete onboarding, and link their accounts via invite code.
- Both users can log a full workout with per-set weight/reps and see it in history.
- Both users can log food via barcode search and via photo (with confidence-flagged, editable AI estimates).
- Each user can see the other's workout streak/frequency stats, and a direct attempt to query the other's food logs or weight entries returns nothing.
- The app installs to the homescreen on both an iOS and an Android device and functions with the browser chrome hidden (standalone mode).

---

## 8. V2 — AI Coach (Specified, Deferred)

This section captures the full coaching-engine design as specified by the user. **Not built in v1** — it requires real logged workout/food data from v1 to design the rule thresholds against, and requires the recovery-signal approach below (self-report) to be layered onto the daily logging flow.

### 8.1 First-time onboarding (learn the user)

Ask once, save permanently, never re-ask unless the user says something changed:
1. Primary fitness goal (e.g. lose weight, build muscle, run a 5K, get more active, reduce stress, improve mobility, train for an event, body recomposition)
2. Secondary goal (optional)
3. Current workout routine, including reps/sets where applicable

Confirm back a summary: *"Got it. You want to [goal], you have [equipment], you can do [X] days a week for [X] minutes, and you're at the [level] level. I'll avoid [limitations]. Let's go."*

### 8.2 Daily decision engine

**Momentum check (self-reported streak data, no wearables):**
- 3+ workouts in a row → push slightly harder (add a set, bump a weight suggestion, add a finisher, extend by 5 min)
- 5+ consecutive days → watch for overtraining via self-reported energy/soreness/sleep (see §8.4) rather than biometric HR data
- Missed 1 day → no comment, pick up where they left off
- Missed 2–3 days → acknowledge without guilt, prescribe something manageable
- Missed 4–7 days → gentle reset, ~20–30 min at 60% intensity
- Missed 2+ weeks → full reset to Week 1 difficulty, framed as a fresh start

**Soreness & recovery check (self-report driven):**
- Reported soreness in a specific muscle group → don't train that group; active recovery or a different focus
- Reported general fatigue / "feeling off" → drop to a light workout (walk, mobility, easy yoga)
- Hard workout yesterday + self-reported poor sleep → automatic active recovery day

### 8.3 Progressive overload system, by goal type

**Strength:**
- Track suggested weights per major lift (squat, deadlift, bench, overhead press, rows)
- +2.5–5 lbs after 2 consecutive sessions hitting all prescribed sets/reps
- Fail a set → hold weight next session; fail twice in a row → drop 10%, rebuild
- Every 4th week is a deload: −40% volume, −20% intensity, framed as intentional recovery

**Weight loss:**
- +5 min cardio/week or +1 interval per session
- Step target +500/week toward 10k
- +1 strength session every 3–4 weeks
- Track weekly-average bodyweight trend (not daily fluctuation)

**Running/endurance:**
- 10% rule — never increase weekly mileage more than 10%
- Rotate easy / tempo / long-run days
- Every 4th week: −30% mileage for recovery
- Track pace/distance trend

**General fitness / get more active:**
- Start 3x/week, 20–30 min
- +5 min every 2 weeks
- Add a 4th day after 3+ consistent weeks
- Mix modalities: strength / cardio / flexibility-or-fun

### 8.4 Recovery data source (resolved during interview)

The original spec referenced resting HR trend and sleep-tracker data. Since wearable/HealthKit integration was explicitly ruled out for this app, v2 will substitute a **daily self-report check-in** (energy level 1–5, soreness by muscle group, sleep quality 1–5) as the input to the momentum/recovery logic above, rather than biometric data. This keeps a single logging mechanism (the app itself) instead of requiring an external integration, and leaves a real wearable integration as a possible future upgrade without changing the shape of the decision engine.

### 8.5 Build-order rationale

v1 ships plain logging (workouts, food) plus the partner dashboard, with no coaching intelligence. v2 layers the decision engine above on top of that real, per-set/per-log data — this lets the progressive-overload thresholds and momentum rules be validated against actual usage rather than designed blind.

---

## 9. Open Questions / Future Considerations

- Exact daily check-in UI/UX for §8.4 self-report data — not yet designed.
- Whether push notifications become worth building once the app has real daily-active usage data.
- Whether a real wearable integration (Apple Health, Whoop, Oura) gets added later as an upgrade to the recovery signal, per §8.4.
- Cost monitoring for Claude API usage if photo-based food logging volume grows beyond "a couple of meals a day for two people."
