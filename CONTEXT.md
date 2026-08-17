# Swolemates

A fitness coaching app exposed identically through a web SPA and a Claude connector (remote MCP), sharing one backend and one database.

## Language

### Nutrition

**Trackable**:
A loggable nutrition metric — calories, protein_g, carbs_g, fat_g, fiber_g, weight_lbs. A generalized, seeded registry: a new Trackable is a seed row, never a schema change.
_Avoid_: metric, field

**Log**:
One logged event for a Trackable — a meal, a glass of water, a weigh-in. A header row; the actual numbers live in its Log Values (one header, many values — a single meal can log calories and protein at once).
_Avoid_: entry (fine in casual UI copy, not in code/design language), record

**Goal**:
A per-Trackable daily target the user sets. At most one Goal can also be the Streak target.
_Avoid_: target (reserve for the numeric value a Goal holds)

**Meal Template**:
A saved, reusable meal, created save-from-log only (never built from scratch) — a named bundle of items, each with its own Trackable values.
_Avoid_: recipe, preset

**Streak**:
The daily win/miss tracked against whichever Goal is marked the streak target.

**TDEE Calculator**:
The one-time, re-runnable tool that estimates starting calorie/macro Goals from profile stats and the most recently logged weight, via Mifflin-St Jeor. Never auto-recalculates — it writes ordinary Goals, then the user or coach takes over.
_Avoid_: goal calculator (fine in UI copy, not in design language)

### Workouts

**Exercise**:
A catalog entry (seeded) or a user's own custom movement — e.g. Back Squat, Bench Press.

**Workout**:
One session, strength or activity. `completed_at IS NULL` means the Workout is in progress (in-workout mode).
_Avoid_: session (collides with auth sessions)

**Workout Set**:
One set within a Workout's exercise — reps-based or timed, with prescribed and actual values.

**Activity**:
A non-strength Workout (yoga, a swim, a hike) — logged as a type/duration only, no per-set detail.
_Avoid_: cardio (too narrow — Activity covers anything non-strength)
