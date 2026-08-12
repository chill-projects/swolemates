from pydantic import BaseModel


class FoodFactOut(BaseModel):
    name: str
    brand: str | None
    serving_description: str
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
