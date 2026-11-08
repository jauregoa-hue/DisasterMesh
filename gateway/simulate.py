"""Send a safe test SOS using the same gateway endpoint, without hardware."""
import os
import uuid
import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
key = os.getenv("GATEWAY_KEY", "")
if len(key) < 32:
    raise SystemExit("Set GATEWAY_KEY in gateway/.env first")
payload = {"packet_id": "demo-" + str(uuid.uuid4()), "device_id": "!0436bda8",
           "message": "SOS test: trapped and need help", "latitude": 39.132,
           "longitude": -84.515, "snr": 7.5}
r = requests.post(os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/") + "/gateway/messages",
                  headers={"X-Gateway-Key": key}, json=payload, timeout=8)
print("HTTP", r.status_code, r.text)
r.raise_for_status()
