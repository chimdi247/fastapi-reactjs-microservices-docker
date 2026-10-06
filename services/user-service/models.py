from sqlmodel import SQLModel, Field
from typing import Optional


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    email: str
    password: str
    role: str = Field(default="user")  # "user" or "admin"


class UserPublic(SQLModel):
    id: int
    name: str
    email: str
    role: str


class UserCreate(SQLModel):
    """
    Registration body. Deliberately does NOT include `role` - otherwise
    anyone could POST {"role": "admin"} to /users/ and grant themselves
    admin rights. New users are always created as "user"; promoting
    someone to admin is a deliberate database-side action (see
    docker/postgres/init/02-seed.sql for how the seeded admin is created).
    """
    name: str
    email: str
    password: str


class LoginRequest(SQLModel):
    email: str
    password: str


class ProductCreate(SQLModel):
    """
    Body for POST /products (admin-only). `initial_stock` isn't part of the
    product itself - it's forwarded to inventory-service as a second write.
    """
    name: str
    price: float
    description: str = ""
    image_url: str = ""
    initial_stock: int = 0


class ProductUpdate(SQLModel):
    """
    Body for PUT /products/{id}. Every field is optional - only the ones
    actually provided get applied, everything else is left unchanged.
    """
    name: Optional[str] = None
    price: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None