"""Matches a colloquial lift name against exercise names (#33)."""

import re
from collections.abc import Iterable

from app.models.workouts import Exercise

# Applied to query and name words alike, after plurals are stripped. Not applied twice,
# so a right-hand side must already be in final form ("dead lift", not "deadlift").
_WORD_REPLACEMENTS: dict[str, str] = {
    # Abbreviations
    "bb": "barbell",
    "bss": "bulgarian split squat",
    "cgbp": "close grip bench press",
    "db": "dumbbell",
    "kb": "kettlebell",
    "ohp": "overhead press",
    "rdl": "romanian dead lift",
    "sldl": "stiff leg dead lift",
    # Compounds and spelling variants
    "calve": "calf",
    "chinup": "chin up",
    "deadlift": "dead lift",
    "ezbar": "ez bar",
    "flie": "fly",
    "flye": "fly",
    "muscleup": "muscle up",
    "pulldown": "pull down",
    "pullup": "pull up",
    "pushdown": "push down",
    "pushup": "push up",
    "situp": "sit up",
    "skullcrusher": "skull crusher",
    "stepup": "step up",
    "tbar": "t bar",
}

# What lifters call a lift vs. what the catalog calls it: a query holding all of the
# left-hand words also searches with them swapped for the right-hand ones. The literal
# query still matches too, so "incline bench" keeps finding "Incline Bench Pull".
_QUERY_SYNONYMS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (frozenset({"ab", "wheel"}), frozenset({"ab", "roller"})),
    (frozenset({"flat", "bench"}), frozenset({"bench", "press"})),
    (frozenset({"incline", "bench"}), frozenset({"incline", "press"})),
    (frozenset({"military", "press"}), frozenset({"overhead", "press"})),
    (frozenset({"side", "raise"}), frozenset({"lateral", "raise"})),
)

# Below this a query word must match whole: "up" shouldn't hit "Upright".
_MIN_PREFIX_LENGTH = 3

# The starter exercises seeded by the workouts_core migration. They rank above the
# vendored catalog, whose rows are otherwise indistinguishable from them in the database
# (both carry a source_id) and whose long tail would fill the limit alphabetically.
STARTER_EXERCISES = frozenset(
    {
        "Arnold Press",
        "Barbell Back Squat",
        "Barbell Bench Press",
        "Barbell Curl",
        "Barbell Row",
        "Bulgarian Split Squat",
        "Cable Crunch",
        "Cable Fly",
        "Calf Raise",
        "Chest Fly (Machine)",
        "Chin-up",
        "Close-Grip Bench Press",
        "Deadlift",
        "Dip",
        "Dumbbell Bench Press",
        "Dumbbell Curl",
        "Dumbbell Row",
        "Dumbbell Shoulder Press",
        "Face Pull",
        "Front Raise",
        "Front Squat",
        "Hammer Curl",
        "Hanging Leg Raise",
        "Hip Thrust",
        "Incline Barbell Press",
        "Incline Dumbbell Press",
        "Lat Pulldown",
        "Lateral Raise",
        "Leg Curl",
        "Leg Extension",
        "Leg Press",
        "Overhead Press",
        "Plank",
        "Pull-up",
        "Push-up",
        "Romanian Deadlift",
        "Russian Twist",
        "Seated Cable Row",
        "Skull Crusher",
        "Tricep Pushdown",
        "Walking Lunge",
    }
)


def _singular(word: str) -> str:
    if word.endswith(("sses", "ches", "shes", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 2:
        return word[:-1]
    return word


def _raw_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower().replace("'", ""))


def _words(text: str) -> set[str]:
    return {
        word
        for singular in map(_singular, _raw_words(text))
        for word in _WORD_REPLACEMENTS.get(singular, singular).split()
    }


def _word_matches(wanted: str, name_words: set[str]) -> bool:
    if wanted in name_words:
        return True
    return len(wanted) >= _MIN_PREFIX_LENGTH and any(w.startswith(wanted) for w in name_words)


def _query_variants(query: str) -> list[set[str]]:
    wanted = _words(query)
    if not wanted:
        return []
    return [wanted] + [(wanted - said) | means for said, means in _QUERY_SYNONYMS if said <= wanted]


def _rank(exercise: Exercise, name_words: set[str], variants: list[set[str]]) -> tuple:
    """Sort key, closest first: the exact name, then whole-word matches over prefix ones,
    then starter exercises and the user's own customs, then the shortest name as written."""
    exact = name_words in variants
    whole_words = any(wanted <= name_words for wanted in variants)
    familiar = exercise.is_custom or exercise.name in STARTER_EXERCISES
    return (not exact, not whole_words, not familiar, len(_raw_words(exercise.name)), exercise.name)


def match_exercises(query: str, exercises: Iterable[Exercise]) -> list[Exercise]:
    """Every exercise whose name has all the query's words, in any order, closest first."""
    variants = _query_variants(query)
    ranked = []
    for exercise in exercises:
        name_words = _words(exercise.name)
        if any(all(_word_matches(w, name_words) for w in wanted) for wanted in variants):
            ranked.append((_rank(exercise, name_words, variants), exercise))
    ranked.sort(key=lambda pair: pair[0])
    return [exercise for _, exercise in ranked]
