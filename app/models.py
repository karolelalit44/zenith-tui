from pydantic import BaseModel, Field
from typing import Literal


ItemStatus = Literal["available", "reserved", "sold"]


class Item(BaseModel):
    id: int
    name: str = Field(min_length=1, max_length=120)
    price: float = Field(gt=0)
    status: ItemStatus = "available"
    tags: list[str] = Field(default_factory=list)
