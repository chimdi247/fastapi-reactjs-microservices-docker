import json
import os
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, select, text
import aio_pika

from db import engine, get_session
from models import Order
from shared.jwt_utils import verify_token
from shared.telemetry import setup_telemetry

setup_telemetry("order-service")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")

# Global connection variable
rabbitmq_connection = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rabbitmq_connection

    SQLModel.metadata.create_all(engine)

    # Connect to RabbitMQ container with retry
    for i in range(5):
        try:
            rabbitmq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
            break
        except Exception:
            print(f"RabbitMQ not ready yet, retrying in 2 seconds (attempt {i+1}/5)...")
            await asyncio.sleep(2)
    else:
        raise Exception("Failed to connect to RabbitMQ after 5 attempts")

    print("Connected to RabbitMQ!")
    yield
    # Cleanup on shutdown
    await rabbitmq_connection.close()


app = FastAPI(lifespan=lifespan)

setup_telemetry("order-service", app=app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/orders/")
async def place_order(
    product_id: int,
    session: Session = Depends(get_session),
    token_data: dict = Depends(verify_token),
):
    # The user placing the order is whoever the verified JWT says it is -
    # never a client-supplied value (that was a real bug: anyone could
    # previously place an order "as" any other user_id just by passing it).
    user_id = int(token_data.get("sub"))

    order = Order(user_id=user_id, product_id=product_id, status="pending")
    session.add(order)
    session.commit()
    session.refresh(order)

    order_event = {
        "event": "OrderPlaced",
        "order_id": order.id,
        "product_id": product_id,
        "user_id": user_id,
        "status": "pending",
    }

    async with rabbitmq_connection.channel() as channel:
        message = aio_pika.Message(body=json.dumps(order_event).encode())
        await channel.default_exchange.publish(
            message,
            routing_key="order_events",  # This is the queue name
        )

    return {
        "message": "Order received and is being processed in the background.",
        "order": order,
    }


@app.get("/orders/")
def list_my_orders(
    session: Session = Depends(get_session),
    token_data: dict = Depends(verify_token),
):
    user_id = int(token_data.get("sub"))
    orders = session.exec(
        select(Order).where(Order.user_id == user_id).order_by(Order.id.desc())
    ).all()
    return orders


@app.get("/health/liveness", tags=["Health"])
def liveness_probe():
    return {"status": "alive"}


@app.get("/health/readiness", tags=["Health"])
def readiness_probe(response: Response, session: Session = Depends(get_session)):
    try:
        session.exec(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unhealthy", "detail": str(e)}
