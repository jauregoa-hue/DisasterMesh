"""Two-node local Meshtastic gateway. Run on the Mac, not in Docker."""
import os
import time
from datetime import datetime, timezone

import meshtastic.serial_interface
import requests
from dotenv import load_dotenv
from pubsub import pub

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
RESCUE_DEVICE_ID = "!043877c8"
GATEWAY_KEY = os.getenv("GATEWAY_KEY", "")
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
SERIAL_PORT = os.getenv("MESHTASTIC_PORT") or None
latest_positions = {}


def extract_position(position):
    lat = position.get("latitude")
    lon = position.get("longitude")
    if lat is None and "latitudeI" in position:
        lat = position["latitudeI"] / 1e7
    if lon is None and "longitudeI" in position:
        lon = position["longitudeI"] / 1e7
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None
    return {"latitude": float(lat), "longitude": float(lon), "seen": time.time()}


def on_position(packet, interface):
    if packet.get("fromId") != RESCUE_DEVICE_ID:
        return
    pos = extract_position(packet.get("decoded", {}).get("position", {}))
    if pos:
        latest_positions[RESCUE_DEVICE_ID] = pos
        print("GPS from Rescue Node:", pos["latitude"], pos["longitude"])


def on_message(packet, interface):
    print("\n[INCOMING TEXT PACKET]", flush=True)
    print("Sender:", packet.get("fromId"), flush=True)
    print("Channel:", packet.get("channel"), flush=True)
    print("Message:", packet.get("decoded", {}).get("text"), flush=True)
    if packet.get("fromId") != RESCUE_DEVICE_ID:
        return
    decoded = packet.get("decoded", {})
    message = decoded.get("text", "")
    if not isinstance(message, str) or not message.strip():
        return
    # Meshtastic supplies an ID for normal packets; don't create synthetic IDs
    # on retransmissions, or the same message could create duplicate incidents.
    packet_id = packet.get("id")
    if packet_id is None:
        print("Ignoring radio packet with no packet ID")
        return
    payload = {"packet_id": str(packet_id), "device_id": RESCUE_DEVICE_ID,
               "message": message[:1000], "snr": packet.get("rxSnr")}
    pos = latest_positions.get(RESCUE_DEVICE_ID)
    if pos and time.time() - pos["seen"] <= 900:
        payload.update(latitude=pos["latitude"], longitude=pos["longitude"])
    try:
        response = requests.post(BACKEND_URL + "/gateway/messages", json=payload,
                                 headers={"X-Gateway-Key": GATEWAY_KEY}, timeout=8)
        response.raise_for_status()
        print("Forwarded:", message, "result:", response.json())
    except requests.RequestException as exc:
        print("Failed to forward (not queued):", exc)


def main():
    if len(GATEWAY_KEY) < 32:
        raise SystemExit("Missing/short GATEWAY_KEY in gateway/.env")
    pub.subscribe(on_message, "meshtastic.receive.text")
    pub.subscribe(on_position, "meshtastic.receive.position")
    print("Opening Meshtastic USB gateway:", SERIAL_PORT or "auto-detect")
    radio = meshtastic.serial_interface.SerialInterface(devPath=SERIAL_PORT)
    try:
        for node_id, node in radio.nodes.items():
            if node_id == RESCUE_DEVICE_ID:
                pos = extract_position(node.get("position", {}))
                if pos:
                    latest_positions[node_id] = pos
        print("Ready: waiting for Rescue Node SOS from", RESCUE_DEVICE_ID)
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping gateway")
    finally:
        radio.close()


if __name__ == "__main__":
    main()
