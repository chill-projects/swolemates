import { test } from "node:test";
import assert from "node:assert/strict";
import { validateWorkout } from "./workoutValidation.ts";

test("rejects zero exercises", () => {
  assert.equal(validateWorkout([]), "Add at least one exercise.");
});

test("rejects an exercise with no sets", () => {
  assert.equal(
    validateWorkout([{ exerciseName: "Squat", sets: [] }]),
    "Squat needs at least one set.",
  );
});

test("rejects a rep set with no reps", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Squat",
        sets: [{ setType: "reps", actualReps: "", actualWeight: "135", workSeconds: "" }],
      },
    ]),
    "Squat: every rep set needs reps > 0.",
  );
});

test("rejects a rep set with zero reps", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Squat",
        sets: [{ setType: "reps", actualReps: "0", actualWeight: "135", workSeconds: "" }],
      },
    ]),
    "Squat: every rep set needs reps > 0.",
  );
});

test("rejects a rep set with a missing weight", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Squat",
        sets: [{ setType: "reps", actualReps: "5", actualWeight: "", workSeconds: "" }],
      },
    ]),
    "Squat: every rep set needs a weight (0 is fine for bodyweight).",
  );
});

test("accepts a rep set with a bodyweight (zero) weight", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Pull-up",
        sets: [{ setType: "reps", actualReps: "8", actualWeight: "0", workSeconds: "" }],
      },
    ]),
    null,
  );
});

test("rejects a timed set with no work seconds", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Plank",
        sets: [{ setType: "time", actualReps: "", actualWeight: "", workSeconds: "0" }],
      },
    ]),
    "Plank: every timed set needs work seconds > 0.",
  );
});

test("accepts a fully valid multi-exercise workout", () => {
  assert.equal(
    validateWorkout([
      {
        exerciseName: "Squat",
        sets: [{ setType: "reps", actualReps: "5", actualWeight: "135", workSeconds: "" }],
      },
      {
        exerciseName: "Plank",
        sets: [{ setType: "time", actualReps: "", actualWeight: "", workSeconds: "45" }],
      },
    ]),
    null,
  );
});
