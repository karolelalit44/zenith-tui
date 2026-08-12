from pydantic import BaseModel, Field
from typing import Literal


ItemStatus = Literal["available", "reserved", "sold"]


class ItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(gt=0)
    status: ItemStatus = "available"
    tags: list[str] = Field(default_factory=list)


class ItemUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price: float | None = Field(default=None, gt=0)
    status: ItemStatus | None = None
    tags: list[str] | None = None


class ItemRead(ItemCreate):
    id: int

    model_config = {"from_attributes": True}
