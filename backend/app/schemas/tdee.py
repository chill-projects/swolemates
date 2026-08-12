from pydantic import BaseModel


class CalculateTargetsResponse(BaseModel):
    tdee: int
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int
    fiber_g: int
