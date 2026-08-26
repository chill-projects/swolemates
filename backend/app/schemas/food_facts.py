from pydantic import BaseModel


class FoodFactOut(BaseModel):
    name: str
    brand: str | None
    # Every macro below is per 100g — a manufacturer serving size, when OFF reports
    # one in grams, comes through here only as a UI prefill hint.
    serving_grams: float | None
    calories: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
