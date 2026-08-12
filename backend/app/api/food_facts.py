from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser
from app.schemas.food_facts import FoodFactOut
from app.services import food_facts as service

router = APIRouter(prefix="/food-facts", tags=["food-facts"])


@router.get("/search", response_model=list[FoodFactOut], operation_id="searchFoodFacts")
async def search_food_facts(
    user_sub: CurrentUser,
    query: str | None = None,
    barcode: str | None = None,
) -> list[FoodFactOut]:
    try:
        results = await service.search_food_facts(query=query, barcode=barcode)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return [FoodFactOut.model_validate(r) for r in results]
