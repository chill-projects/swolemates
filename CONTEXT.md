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

### Kitchen

**Kitchen**:
A best-guess record of the food at home, across the fridge, freezer and pantry. Linked partners share one Kitchen; an unlinked user has their own. It records what's in the house, not what anyone ate, so it sits outside the partner privacy rule that covers food logs.
_Avoid_: fridge (fine in casual UI copy, not in design language), inventory, pantry (that's one Storage Location)

**Kitchen Item**:
One thing in the Kitchen, with its quantity as bought in plain words ("1 gal"). Quantities are descriptive and never calculated. An item leaves when someone removes it, or by itself a week after its Estimated Expiry.
_Avoid_: stock, product

**Leftover**:
A Kitchen Item that is a portion of an already-made meal, so it has its own macros. Logging it as eaten removes it, unless a smaller portion was deliberately planned, in which case the rest stays. Everything else in the Kitchen is an Ingredient.

**Ingredient**:
A Kitchen Item that is food as bought rather than a made meal. It has no macros of its own.
_Avoid_: grocery (fine in casual UI copy)

**Storage Location**:
Where a Kitchen Item is kept: fridge, freezer or pantry. Moving an item to another Storage Location restarts its Estimated Expiry.

**Shelf-Life Category**:
A kind of food with a known typical shelf life in each Storage Location. It's the basis for an Estimated Expiry, so the same food always gets the same estimate.

**Estimated Expiry**:
The date a Kitchen Item is probably good until, worked out from its Shelf-Life Category and Storage Location unless someone overrides it, for example with the date printed on the package. It's an estimate, never a food-safety claim. A food with no sensible Shelf-Life Category has no Estimated Expiry and stays until someone removes it.
_Avoid_: expiration date, best before, use by

**To Use Up**:
The Kitchen Items someone has starred because they want them eaten. It's always a person's call, for either partner: an Estimated Expiry never puts something here, and the star goes when the item leaves the Kitchen.
_Avoid_: needs eating, use soon, tray

**Grocery Haul**:
The Kitchen Items added from one shopping trip, remembered together with their purchase date so a bad read can be undone as a whole and a likely duplicate trip can be flagged.
_Avoid_: order, shop, trip

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
