from fastapi import APIRouter, HTTPException, status
from app.models import Item
from app.schemas import ItemCreate, ItemRead, ItemUpdate

router = APIRouter(prefix="/items", tags=["items"])
_items: dict[int, Item] = {}
_next_id = 1

@router.post("", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate) -> ItemRead:
    global _next_id
    item = Item(id=_next_id, **payload.model_dump())
    _items[item.id] = item
    _next_id += 1
    return ItemRead.model_validate(item)

@router.get("", response_model=list[ItemRead])
def list_items() -> list[ItemRead]:
    return [ItemRead.model_validate(i) for i in _items.values()]

@router.get("/{item_id}", response_model=ItemRead)
def get_item(item_id: int) -> ItemRead:
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return ItemRead.model_validate(item)

@router.patch("/{item_id}", response_model=ItemRead)
def update_item(item_id: int, payload: ItemUpdate) -> ItemRead:
    item = _items.get(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    updated = item.model_copy(update={k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None})
    _items[item_id] = updated
    return ItemRead.model_validate(updated)

@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int) -> None:
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="Item not found")
    del _items[item_id]
