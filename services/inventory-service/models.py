from sqlmodel import SQLModel, Field
from typing import Optional


class Inventory(SQLModel, table=True):
    product_id: Optional[int] = Field(default=None, primary_key=True)
    stock: int = 0
