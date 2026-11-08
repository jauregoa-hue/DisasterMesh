"""Exercise the real receiver callbacks and HTTP outbox without opening the radio."""
import argparse
import logging
import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from dotenv import load_dotenv
import meshtastic_receiver as receiver


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--gps", choices=["valid", "missing", "stale", "future", "unknown_time", "invalid"], default="valid")
    parser.add_argument("--packet-id", type=int, default=None)
    args = parser.parse_args()
    node = "!0436bda8"
    if args.gps != "missing":
        timestamp = int(datetime.now(timezone.utc).timestamp())
        if args.gps == "stale": timestamp -= int(os.getenv("GPS_MAX_AGE_SECONDS", "300")) + 60
        if args.gps == "future": timestamp += 3600
        position = {"latitudeI": 391380992, "longitudeI": -844890112, "time": timestamp}
        if args.gps == "unknown_time": position.pop("time")
        if args.gps == "invalid": position["latitudeI"] = 9990000000
        receiver.on_position({"fromId": node, "decoded": {"position": position}})
    receiver.outbox = receiver.Outbox(os.getenv("GATEWAY_OUTBOX", "gateway-outbox.db"),
        os.getenv("GATEWAY_API_URL", "http://localhost:8000"), os.getenv("GATEWAY_API_KEY", ""))
    packet_id = args.packet_id if args.packet_id is not None else secrets.randbelow(0xffffffff) + 1
    receiver.on_message({"fromId": node, "id": packet_id, "rxSnr": 5.25,
                         "decoded": {"text": "[SIMULATED] SOS test: person trapped near bridge"}})
    with httpx.Client(timeout=5, trust_env=False) as client:
        delivered = receiver.outbox.drain_once(client)
    print(f"Synthetic packet {packet_id}: {delivered} queued event(s) delivered. No radio used.")
    return 0 if delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
