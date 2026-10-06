import json
import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Response, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, select, text
import aio_pika

from db import engine, get_session
from models import Inventory
from shared.telemetry import setup_telemetry
from shared.jwt_utils import require_admin

setup_telemetry("inventory-service")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


async def process_message(message: aio_pika.abc.AbstractIncomingMessage):
    try:
        event_data = json.loads(message.body.decode())
        print(f"📦 Received Event: {event_data}")

        product_id = event_data.get("product_id")

        # SIMULATE A FATAL ERROR
        if product_id == 999:
            print("❌ Fatal error: Simulated crash! Rejecting message.")
            # Reject the message and DO NOT requeue it.
            # This triggers the Dead Letter Exchange (DLX).
            await message.reject(requeue=False)
            return

        with Session(engine) as session:
            item = session.get(Inventory, product_id)

            if item is not None and item.stock > 0:
                item.stock -= 1
                session.add(item)
                session.commit()
                print(f"✅ Stock reduced! Remaining stock for product {product_id}: {item.stock}")
            else:
                print(f"❌ Out of stock or invalid product: {product_id}")

        # Manually acknowledge the message was processed successfully
        await message.ack()
    except Exception as e:
        print(f"❌ Error processing message: {e}")
        # If any Python error occurs, safely dead-letter the message
        await message.reject(requeue=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    SQLModel.metadata.create_all(engine)

    # 1. Connect to RabbitMQ with retry
    connection = None
    for i in range(5):
        try:
            connection = await aio_pika.connect_robust(RABBITMQ_URL)
            channel = await connection.channel()
            break
        except Exception:
            print(f"RabbitMQ not ready yet, retrying in 2 seconds (attempt {i+1}/5)...")
            await asyncio.sleep(2)
    else:
        raise Exception("Failed to connect to RabbitMQ after 5 attempts")

    # 2. Declare the Dead Letter Exchange (DLX) and Dead Letter Queue (DLQ)
    dlx = await channel.declare_exchange("dlx", aio_pika.ExchangeType.DIRECT)
    dlq = await channel.declare_queue("order_events_dlq", durable=True)
    await dlq.bind(dlx, routing_key="order_events")

    # 3. Declare the main queue and tell it to route failures to the DLX
    arguments = {
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "order_events",
    }
    queue = await channel.declare_queue("order_events", durable=True, arguments=arguments)

    # 4. Consume messages
    await queue.consume(process_message)
    print("🎧 Inventory Service is now listening for order events...")

    yield

    await connection.close()


app = FastAPI(lifespan=lifespan)

setup_telemetry("inventory-service", app=app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/inventory/")
def list_stock(session: Session = Depends(get_session)):
    return session.exec(select(Inventory)).all()


@app.get("/inventory/{product_id}")
def get_stock(product_id: int, session: Session = Depends(get_session)):
    item = session.get(Inventory, product_id)
    if item is None:
        return {"error": "Product not found"}
    return item


@app.put("/inventory/{product_id}")
def set_stock(
    product_id: int,
    stock: int,
    session: Session = Depends(get_session),
    token_data: dict = Depends(require_admin),
):
    """
    Admin-only. Upsert the stock level for a product. Called by user-service
    when an admin creates a product (see its POST /products handler,
    which forwards the admin's own token here - see require_admin's
    docstring for why that's necessary), and usable directly for restocking.
    """
    if stock < 0:
        raise HTTPException(status_code=400, detail="stock cannot be negative")

    item = session.get(Inventory, product_id)
    if item is None:
        item = Inventory(product_id=product_id, stock=stock)
    else:
        item.stock = stock

    session.add(item)
    session.commit()
    session.refresh(item)
    return item


@app.delete("/inventory/{product_id}")
def delete_stock(
    product_id: int,
    session: Session = Depends(get_session),
    token_data: dict = Depends(require_admin),
):
    """
    Admin-only. Remove a product's inventory row. Used by user-service to
    roll back a partially-completed product creation, and when deleting a
    product entirely.
    """
    item = session.get(Inventory, product_id)
    if item is None:
        return {"deleted": False}

    session.delete(item)
    session.commit()
    return {"deleted": True}


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
