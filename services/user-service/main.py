from fastapi import FastAPI, Depends, HTTPException, Response, status, Security
from contextlib import asynccontextmanager
from db import engine, get_session
from sqlmodel import SQLModel, Session, select, text
from models import User, UserPublic, UserCreate, LoginRequest, ProductCreate, ProductUpdate
import os
import grpc
import httpx
import product_pb2
import product_pb2_grpc
from fastapi.middleware.cors import CORSMiddleware
from auth import hash_password, verify_password, create_access_token
from shared.jwt_utils import verify_token, require_admin, security
from shared.telemetry import setup_telemetry, instrument_grpc_client
from fastapi.security import HTTPAuthorizationCredentials

PRODUCT_SERVICE_ADDR = os.getenv("PRODUCT_SERVICE_ADDR", "product-service:50051")
INVENTORY_SERVICE_URL = os.getenv("INVENTORY_SERVICE_URL", "http://inventory-service:8000")


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(lifespan=lifespan)

setup_telemetry("user-service", app=app)
instrument_grpc_client()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/users/", response_model=UserPublic)
def create_user(payload: UserCreate, session: Session = Depends(get_session)):
    # Role is intentionally not taken from the request body - always "user".
    user = User(
        name=payload.name,
        email=payload.email,
        password=hash_password(payload.password),
        role="user",
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@app.get("/users/", response_model=list[UserPublic])
def read_users(session: Session = Depends(get_session)):
    # response_model=UserPublic matters here: returning raw User rows would
    # expose every user's bcrypt password hash over the API.
    users = session.exec(select(User)).all()
    return users


@app.get("/users/me", response_model=UserPublic)
def read_current_user(
    session: Session = Depends(get_session),
    token_data: dict = Depends(verify_token),
):
    user = session.get(User, int(token_data.get("sub")))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.get("/products")
def list_products():
    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        response = stub.ListProducts(product_pb2.ListProductsRequest())

    return [
        {
            "id": p.id,
            "name": p.name,
            "price": p.price,
            "description": p.description,
            "image_url": p.image_url,
        }
        for p in response.products
    ]


@app.get("/products/{product_id}")
def get_product(product_id: int):
    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        try:
            response = stub.GetProduct(product_pb2.ProductRequest(id=product_id))
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Product not found")
            raise HTTPException(status_code=502, detail="Product service unavailable")

    return {
        "id": response.id,
        "name": response.name,
        "price": response.price,
        "description": response.description,
        "image_url": response.image_url,
    }


@app.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreate,
    token_data: dict = Depends(require_admin),
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    Admin-only. Creates a product AND its initial inventory row - two writes
    across two services, which means this can partially fail.

    There's no distributed transaction here (product-service speaks gRPC,
    inventory-service speaks HTTP, and they own separate tables). Instead
    this uses a compensating action: if the inventory write fails after the
    product was already created, the product is deleted again so we don't
    leave a product that can never be ordered because it has no stock row.

    If that rollback ALSO fails, we say so explicitly in the error rather
    than pretending the system is consistent - an operator needs to know.

    inventory-service's write endpoints are admin-guarded too, and this
    server-to-server call carries no session of its own - so the caller's
    own admin token is forwarded as-is. This means the same token that got
    this request past `require_admin` here is what authorizes the write on
    the other side; there's no separate service credential.
    """
    if payload.price < 0:
        raise HTTPException(status_code=400, detail="price cannot be negative")
    if payload.initial_stock < 0:
        raise HTTPException(status_code=400, detail="initial_stock cannot be negative")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name cannot be empty")

    forwarded_auth = {"Authorization": f"Bearer {credentials.credentials}"}

    # --- Write 1: create the product (product-service, gRPC) ---
    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        try:
            created = stub.CreateProduct(
                product_pb2.CreateProductRequest(
                    name=payload.name,
                    price=payload.price,
                    description=payload.description,
                    image_url=payload.image_url,
                )
            )
        except grpc.RpcError:
            raise HTTPException(status_code=502, detail="Product service unavailable")

    product_id = created.id

    # --- Write 2: set initial stock (inventory-service, HTTP) ---
    try:
        resp = httpx.put(
            f"{INVENTORY_SERVICE_URL}/inventory/{product_id}",
            params={"stock": payload.initial_stock},
            headers=forwarded_auth,
            timeout=5.0,
        )
        resp.raise_for_status()
    except Exception as inventory_error:
        # Compensating action: undo write 1 so we don't strand a product
        # with no inventory row.
        rollback_ok = False
        try:
            with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
                stub = product_pb2_grpc.ProductServiceStub(channel)
                stub.DeleteProduct(product_pb2.ProductRequest(id=product_id))
            rollback_ok = True
        except grpc.RpcError:
            pass

        if rollback_ok:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Could not set initial stock, so the product was not created "
                    f"({inventory_error}). Nothing was left behind - safe to retry."
                ),
            )
        raise HTTPException(
            status_code=500,
            detail=(
                f"Could not set initial stock ({inventory_error}), AND could not "
                f"roll back product {product_id}. Product {product_id} now exists "
                "with no inventory row and needs manual cleanup."
            ),
        )

    return {
        "id": created.id,
        "name": created.name,
        "price": created.price,
        "description": created.description,
        "image_url": created.image_url,
        "initial_stock": payload.initial_stock,
    }


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    token_data: dict = Depends(require_admin),
):
    """
    Admin-only. Update any subset of a product's fields - most usefully
    image_url, to point a product at a real image. Omitted fields are left
    unchanged.
    """
    request = product_pb2.UpdateProductRequest(id=product_id)

    # Only set the fields the caller actually sent, so proto3 presence
    # tracking carries "leave this alone" through to product-service.
    if payload.name is not None:
        request.name = payload.name
    if payload.price is not None:
        request.price = payload.price
    if payload.description is not None:
        request.description = payload.description
    if payload.image_url is not None:
        request.image_url = payload.image_url

    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        try:
            response = stub.UpdateProduct(request)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise HTTPException(status_code=404, detail="Product not found")
            raise HTTPException(status_code=502, detail="Product service unavailable")

    return {
        "id": response.id,
        "name": response.name,
        "price": response.price,
        "description": response.description,
        "image_url": response.image_url,
    }


@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    token_data: dict = Depends(require_admin),
    credentials: HTTPAuthorizationCredentials = Security(security),
):
    """
    Admin-only. Deletes a product AND its inventory row - the same
    cross-service concern as create, in reverse. Deletes inventory first:
    if that fails, the product still exists with its stock row intact
    (a safe, consistent state to retry from). If it's the product delete
    that fails after inventory is already gone, that's reported explicitly
    rather than silently leaving a product with no stock.
    """
    forwarded_auth = {"Authorization": f"Bearer {credentials.credentials}"}

    try:
        resp = httpx.delete(
            f"{INVENTORY_SERVICE_URL}/inventory/{product_id}",
            headers=forwarded_auth,
            timeout=5.0,
        )
        resp.raise_for_status()
    except Exception as inventory_error:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Could not remove inventory for product {product_id} "
                f"({inventory_error}). Product was not deleted - safe to retry."
            ),
        )

    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        try:
            result = stub.DeleteProduct(product_pb2.ProductRequest(id=product_id))
        except grpc.RpcError:
            raise HTTPException(
                status_code=500,
                detail=(
                    f"Removed inventory for product {product_id}, but could not "
                    "delete the product itself - product service unavailable. "
                    f"Product {product_id} now exists with no inventory row."
                ),
            )

    if not result.deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"deleted": True, "id": product_id}


@app.get("/users/{user_id}/purchases/{product_id}")
def get_user_purchase(
    user_id: int,
    product_id: int,
    token_data: dict = Depends(verify_token),
):
    if str(user_id) != token_data.get("sub"):
        raise HTTPException(status_code=403, detail="Not authorized to access this resource")

    with grpc.insecure_channel(PRODUCT_SERVICE_ADDR) as channel:
        stub = product_pb2_grpc.ProductServiceStub(channel)
        response = stub.GetProduct(product_pb2.ProductRequest(id=product_id))

    return {
        "user_id": user_id,
        "product_details": {
            "id": response.id,
            "name": response.name,
            "price": response.price
        },
        "source": "gRPC"
    }


@app.post("/login")
def login(user_data: LoginRequest, session: Session = Depends(get_session)):
    statement = select(User).where(User.email == user_data.email)
    db_user = session.exec(statement).first()

    if not db_user or not verify_password(user_data.password, db_user.password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    token = create_access_token(
        data={"sub": str(db_user.id), "email": db_user.email, "role": db_user.role}
    )
    return {"access_token": token, "token_type": "bearer"}


@app.get("/health/liveness", tags=["Health"])
def liveness_probe():
    """Checks if the FastAPI server is running."""
    return {"status": "alive"}


@app.get("/health/readiness", tags=["Health"])
def readiness_probe(response: Response, session: Session = Depends(get_session)):
    """Checks if the service is ready to handle traffic (e.g., DB connected)."""
    try:
        # Execute a simple ping to the database
        session.exec(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        # If the DB is unreachable, return a 503 error
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "detail": str(e)}
