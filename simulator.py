import redis
import json
import random
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

skus = ["eggs-12ct", "milk-1gal"]
stores = ["store-1", "store-2", "web"]

print("Simulator running... press Ctrl+C to stop")

while True:
    event = {
        "type": "sale",
        "sku": random.choice(skus),
        "store": random.choice(stores),
        "qty": 1,
        "time": time.strftime("%H:%M:%S")
    }

    r.publish("inventory-events", json.dumps(event))
    print(f"Published: {event}")

    time.sleep(2)