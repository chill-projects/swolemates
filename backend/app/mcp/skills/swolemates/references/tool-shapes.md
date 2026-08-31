# Exact tool shapes and sharp edges

Payload details that are easy to guess wrong. Read before the first logging or
correction call of a conversation; don't reload if it's already in context.

## log_workout

Items key the exercise as `"exercise"`, not `"name"`:

```json
{"exercises": [{"exercise": "Barbell Back Squat",
                "sets": [{"weight": 225, "reps": 5}]}]}
```

- Reps sets: `"reps"` > 0 and `"weight"` >= 0 (0 for bodyweight).
- Timed sets: `"set_type": "time"` with `"work_seconds"` > 0.
- `"is_warmup": true` excludes a set from PR checks.
- Optional per-exercise: `"notes"`, `"next_time_note"`, `"muscle_group"` (only
  matters when deliberately creating a custom exercise — ask the user which of
  legs/arms/shoulders/back/core/chest, don't guess).
- `date` backdates; a bare date means that day in the user's timezone.

## search_exercises

Matches one **contiguous, case-insensitive substring** of the catalog name.
"incline bench" hits "Incline Bench Press"; "incline press" hits nothing, because
the words aren't adjacent in any catalog name. On no results, retry with a shorter
fragment or a single distinctive word ("incline", "row") before concluding the
exercise isn't in the catalog. Then use a returned name **verbatim** — a
close-but-not-exact name silently creates a custom exercise with no muscle-map data.

## update_workout

Edits or deletes existing sets — it **cannot append one**. Asking for a
`set_number` beyond what was logged fails ("… has no set 3"). So get the full set
count into the original `log_workout` call: if the user's account of a session is
vague on sets, ask before logging, not after. If a set really was missed, say
plainly that chat can't append it yet rather than improvising a workaround that
double-logs.

Sets are addressed by 1-indexed `"set_number"`; only fields you pass change;
`"delete": true` removes a set. The named `"exercise"` must already be in the
workout — adding a new exercise to a logged workout isn't supported either.
