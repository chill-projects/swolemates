from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.tdee import CalculateTargetsResponse, TdeeEstimateOut
from app.services import tdee as service

router = APIRouter(prefix="/tdee", tags=["tdee"])


@router.get("", response_model=TdeeEstimateOut, operation_id="getTdeeEstimate")
async def get_tdee_estimate(user_sub: CurrentUser, session: DbSession) -> TdeeEstimateOut:
    """What the calculator would produce right now, persisting nothing — the Profile
    page shows this next to the targets you've actually saved, so the estimate can be
    displayed without silently overwriting them."""
    inputs, missing = await service.gather_inputs(session, user_sub)
    if inputs is None:
        return TdeeEstimateOut(missing=missing)
    targets, tdee = service.calculate_targets(inputs)
    return TdeeEstimateOut(
        tdee=round(tdee),
        calories=targets.calories,
        protein_g=targets.protein_g,
        carbs_g=targets.carbs_g,
        fat_g=targets.fat_g,
        fiber_g=targets.fiber_g,
    )


@router.post(
    "/calculate-targets",
    response_model=CalculateTargetsResponse,
    operation_id="calculateTargets",
)
async def calculate_targets(user_sub: CurrentUser, session: DbSession) -> CalculateTargetsResponse:
    try:
        targets, tdee = await service.calculate_and_apply_targets(session, user_sub)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return CalculateTargetsResponse(
        tdee=round(tdee),
        calories=targets.calories,
        protein_g=targets.protein_g,
        carbs_g=targets.carbs_g,
        fat_g=targets.fat_g,
        fiber_g=targets.fiber_g,
    )
