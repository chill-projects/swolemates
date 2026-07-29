import uuid

from fastapi import APIRouter, HTTPException, status

from app.deps import CurrentUser, DbSession
from app.schemas.tmpx import TmpxItemCreate, TmpxItemOut
from app.services import tmpx as service

router = APIRouter(prefix="/tmpx", tags=["tmpx"])


@router.get("", response_model=list[TmpxItemOut], operation_id="listTmpxItems")
async def list_tmpx_items(user_sub: CurrentUser, session: DbSession) -> list[TmpxItemOut]:
    items = await service.list_items(session, user_sub)
    return [TmpxItemOut.model_validate(i) for i in items]


@router.post("", response_model=TmpxItemOut, status_code=201, operation_id="createTmpxItem")
async def create_tmpx_item(
    body: TmpxItemCreate, user_sub: CurrentUser, session: DbSession
) -> TmpxItemOut:
    item = await service.add_item(session, user_sub, name=body.name, value=body.value)
    return TmpxItemOut.model_validate(item)


@router.delete("/{item_id}", status_code=204, operation_id="deleteTmpxItem")
async def delete_tmpx_item(item_id: uuid.UUID, user_sub: CurrentUser, session: DbSession) -> None:
    try:
        await service.delete_item(session, user_sub, item_id)
    except service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
