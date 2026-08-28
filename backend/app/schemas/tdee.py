from pydantic import BaseModel


class CalculateTargetsResponse(BaseModel):
    tdee: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int


class TdeeEstimateOut(BaseModel):
    """The read-only counterpart to CalculateTargetsResponse: the same numbers, but
    computed without persisting them, and expressed so an incomplete profile is a
    normal answer rather than a 400. `missing` names what's still needed."""

    tdee: int | None = None
    calories: int | None = None
    protein_g: int | None = None
    carbs_g: int | None = None
    fat_g: int | None = None
    fiber_g: int | None = None
    missing: list[str] = []
