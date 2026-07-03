from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
import redis
import json
import threading
import asyncio
import time
import os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
r = redis.Redis(host=os.environ.get("REDIS_HOST", "localhost"), port=6379, decode_responses=True)

BASE_PRICES = {
    "eggs-12ct": 4.99,
    "milk-1gal": 3.49,
}
STARTING_STOCK = {
    "eggs-12ct": 47,
    "milk-1gal": 12,
}

def seed_inventory():
    starting_data = {
        "eggs-12ct": {"quantity": 47, "price": 4.99},
        "milk-1gal": {"quantity": 12, "price": 3.49},
    }
    for sku, data in starting_data.items():
        if not r.exists(f"qty:{sku}"):
            r.set(f"qty:{sku}", data["quantity"])
            r.set(f"price:{sku}", data["price"])

seed_inventory()

connected_clients = []
main_event_loop = None

async def broadcast(message: dict):
    dead_clients = []
    for client in connected_clients:
        try:
            await client.send_json(message)
        except Exception:
            dead_clients.append(client)
    for client in dead_clients:
        connected_clients.remove(client)

def record_sale_and_reprice(sku: str):
    now = time.time()
    sales_key = f"sales:{sku}"

    r.zadd(sales_key, {str(now): now})
    r.zremrangebyscore(sales_key, 0, now - 60)
    recent_sales = r.zcount(sales_key, now - 60, now)

    current_qty = int(r.get(f"qty:{sku}"))
    starting_qty = STARTING_STOCK[sku]
    stock_ratio = current_qty / starting_qty

    velocity_multiplier = 1 + min(recent_sales * 0.03, 0.15)
    scarcity_multiplier = 1 + max(0, (1 - stock_ratio) * 0.15)

    base_price = BASE_PRICES[sku]
    new_price = base_price * velocity_multiplier * scarcity_multiplier

    max_price = base_price * 1.20
    min_price = base_price * 0.90
    new_price = max(min_price, min(new_price, max_price))
    new_price = round(new_price, 2)

    r.set(f"price:{sku}", new_price)
    return new_price

def listen_for_events():
    pubsub = r.pubsub()
    pubsub.subscribe("inventory-events")
    print("Background listener started, waiting for events...")

    for message in pubsub.listen():
        if message["type"] != "message":
            continue

        event = json.loads(message["data"])

        if event["type"] == "sale":
            key = f"qty:{event['sku']}"
            if r.exists(key):
                current_qty = int(r.get(key))
                if current_qty > 0:
                    new_qty = r.decr(key)
                    new_price = record_sale_and_reprice(event['sku'])
                    print(f"[Event] {event['store']} sold {event['sku']} -> {new_qty} remaining, price ${new_price}")

                    update = {
                        "sku": event["sku"],
                        "quantity": new_qty,
                        "price": new_price,
                        "store": event["store"],
                        "low_stock": new_qty <= 5
                    }

                    asyncio.run_coroutine_threadsafe(broadcast(update), main_event_loop)
                else:
                    print(f"[Event] {event['store']} tried to sell {event['sku']} but it's OUT OF STOCK")

@app.on_event("startup")
def start_background_listener():
    global main_event_loop
    main_event_loop = asyncio.get_event_loop()
    thread = threading.Thread(target=listen_for_events, daemon=True)
    thread.start()

@app.get("/inventory")
def get_inventory():
    skus = ["eggs-12ct", "milk-1gal"]
    result = {}
    for sku in skus:
        qty = r.get(f"qty:{sku}")
        price = r.get(f"price:{sku}")
        result[sku] = {"quantity": int(qty), "price": float(price)}
    return result

@app.post("/sell/{sku}")
def sell_item(sku: str):
    key = f"qty:{sku}"
    if not r.exists(key):
        raise HTTPException(status_code=400, detail="Invalid SKU")

    current_qty = int(r.get(key))
    if current_qty <= 0:
        raise HTTPException(status_code=400, detail="Out of stock")

    new_qty = r.decr(key)
    return {"message": f"Sold 1 {sku}", "remaining": new_qty}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    print("Client connected. Total clients:", len(connected_clients))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_clients.remove(websocket)
        print("Client disconnected. Total clients:", len(connected_clients))