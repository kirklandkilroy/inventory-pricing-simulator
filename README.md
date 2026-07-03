# Omni-Channel Real-Time Inventory & Pricing Engine(With Claude help)

A simulated real-time inventory sync and dynamic pricing system for retail, built to explore how multiple sales channels (in-store POS, e-commerce, warehouse) can stay in sync without directly depending on one another.

## The Problem

Retailers running both physical stores and e-commerce platforms often struggle to keep stock levels and pricing in sync across channels. A sale at a physical register doesn't instantly reflect online, which can lead to overselling, stale pricing, and poor customer experience.

This project simulates that environment: multiple "stores" generate sales events independently, a central service reconciles inventory in real time, prices adjust automatically based on demand, and a live dashboard reflects it all instantly.

## Architecture
simulator.py (fake stores/web)
|
v
Redis Pub/Sub channel ("inventory-events")
|
v
FastAPI server (background thread subscriber)
|
+--> Redis (source of truth for stock + price, atomic updates)
|
+--> Pricing engine (velocity + scarcity based)
|
v
WebSocket broadcast
|
v
Live browser dashboard (table, updates in place)
**Flow of a single sale:**
1. `simulator.py` publishes a sale event (SKU, store, timestamp) to a Redis Pub/Sub channel
2. The FastAPI server's background thread is subscribed to that channel and receives the event
3. Stock is decremented atomically in Redis (`DECR`), preventing race conditions/overselling across concurrent channels
4. A pricing function evaluates recent sales velocity (via a Redis sorted set as a sliding time window) and current stock scarcity, adjusting price within a capped range
5. The updated stock and price are broadcast over WebSocket to all connected dashboard clients
6. The dashboard updates the relevant table row in place, with a visual highlight

## Why these tools

- **Redis Pub/Sub** decouples the event producers (simulated stores) from consumers (the inventory service). Producers don't need to know who's listening, which mirrors how real retail systems can add new consumers (analytics, fraud detection, etc.) without touching the producer.
- **Redis atomic operations** (`DECR`, sorted sets) prevent race conditions when multiple channels attempt to sell the same low-stock item simultaneously — a real, costly bug in production retail systems.
- **WebSockets** allow the dashboard to reflect changes instantly, rather than polling the API repeatedly and always being slightly behind.
- **Docker Compose** packages the server and Redis together so the whole system starts with a single command, with no manual setup steps required.

## Dynamic Pricing Logic

Price adjusts based on two signals, each capped to avoid unrealistic swings:

- **Velocity** — units sold in the last 60 seconds (tracked via a Redis sorted set, using timestamps as scores). Higher recent sales volume increases price, up to +15%.
- **Scarcity** — current stock as a percentage of starting stock. Lower stock increases price, up to +15%.

Both multipliers apply to the base price, with the final result capped between -10% and +20% of the original price to keep pricing believable.

## Tech Stack

- **Backend:** Python, FastAPI
- **Data store / message broker:** Redis (caching, Pub/Sub, atomic operations, sorted sets)
- **Real-time transport:** WebSockets
- **Frontend:** Vanilla HTML/JS (no framework — keeps the real-time logic visible and easy to reason about)
- **Containerization:** Docker, Docker Compose

## Running the Project

**Requirements:** Docker Desktop installed and running.

```bash
docker-compose up --build
```

This starts both the Redis container and the FastAPI server container, networked together.

In a separate terminal, run the store simulator (generates fake sales continuously):
```bash
python3 simulator.py
```

Then open `dashboard.html` in a browser to view the live dashboard.

### API Endpoints
- `GET /inventory` — current stock and price for all SKUs
- `POST /sell/{sku}` — manually simulate a single sale
- `WS /ws` — WebSocket stream of live inventory/price updates

## Known Limitations

This is a learning/demo project, not production-ready. Notable simplifications:
- No authentication on the API or WebSocket endpoint
- CORS is fully open (`allow_origins=["*"]`) for local development convenience
- No input validation beyond checking SKU existence
- Redis runs without a password (fine for local/dev use only)
- Pricing rules are intentionally simple and rule-based rather than ML-driven, to keep the logic transparent and explainable

## What I Learned

Building this involved working through several real distributed-systems concepts hands-on: event-driven architecture and decoupling via Pub/Sub, atomic operations to prevent race conditions, bridging background threads with asyncio for WebSocket broadcasting, and containerizing a multi-service application with Docker Compose. Debugging along the way (CORS errors, port conflicts, environment-variable-based service discovery) mirrored real issues encountered when moving an app from "runs on my machine" to a properly containerized, networked setup.
