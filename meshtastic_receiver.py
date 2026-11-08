"""Windows USB gateway using the existing Meshtastic text/position subscriptions.

Importing this module never opens COM9. Radio callbacks persist SOS packets locally;
a separate worker delivers them to FastAPI and retries safely after outages/restarts.
"""
import json
import logging
import math
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx
from gateway_contract import position_status

log = logging.getLogger("disastermesh.gateway")
latest_positions = {}
outbox = None


def allowed_nodes():
    return {x.strip().lower() for x in os.getenv("MESHTASTIC_ALLOWED_NODES", "!0436bda8").split(",") if x.strip()}


def sender_id(packet):
    sender = packet.get("fromId")
    if isinstance(sender, str) and re.fullmatch(r"![0-9a-fA-F]{8}", sender):
        return sender.lower()
    number = packet.get("from")
    if type(number) is int and 0 <= number <= 0xffffffff:
        return f"!{number:08x}"
    return "Unknown"


def save_position(sender, position):
    lat, lon = position.get("latitude"), position.get("longitude")
    try:
        if lat is None and "latitudeI" in position:
            lat = position["latitudeI"] / 1e7
        if lon is None and "longitudeI" in position:
            lon = position["longitudeI"] / 1e7
    except (TypeError, ValueError):
        lat, lon = None, None
    timestamp = None
    try:
        raw_time = position.get("time")
        if type(raw_time) in (int, float) and raw_time > 0:
            timestamp = datetime.fromtimestamp(raw_time, timezone.utc)
    except (ValueError, OverflowError, OSError):
        pass
    # Never replace the original fix timestamp with the time a cached fix was loaded.
    now = datetime.now(timezone.utc)
    max_age = int(os.getenv("GPS_MAX_AGE_SECONDS", "300"))
    candidate_status = position_status(lat, lon, timestamp, now, max_age)
    previous = latest_positions.get(sender)
    if previous and not previous.get("rejected") and position_status(
            previous["latitude"], previous["longitude"], previous["timestamp"], now, max_age) == "valid":
        # An invalid or delayed packet must not erase a newer, still-valid known fix.
        if candidate_status != "valid" or timestamp <= previous["timestamp"]:
            return True
    latest_positions[sender] = {"latitude": lat, "longitude": lon, "timestamp": timestamp,
                                "rejected": "future" if candidate_status == "future" else None}
    return candidate_status == "valid"


def on_position(packet, interface=None):
    sender = sender_id(packet)
    if sender not in allowed_nodes():
        return
    valid = save_position(sender, packet.get("decoded", {}).get("position", {}))
    log.info("GPS update from %s: %s (fix time %s)", sender, "valid" if valid else "unusable", latest_positions[sender]["timestamp"])


def build_event(packet, now=None):
    sender = sender_id(packet)
    if sender not in allowed_nodes():
        return None
    message = packet.get("decoded", {}).get("text", "")
    if not isinstance(message, str) or not re.search(r"\bsos\b", message, re.IGNORECASE):
        return None
    message = message.strip()
    if len(message) > 3000:
        log.warning("Ignoring oversized SOS from %s", sender)
        return None
    packet_id = packet.get("id")
    if type(packet_id) is not int or not 1 <= packet_id <= 0xffffffff:
        log.warning("Ignoring SOS without a valid Meshtastic packet ID from %s", sender)
        return None
    now = now or datetime.now(timezone.utc)
    event = {"node_id": sender, "packet_id": packet_id, "message": message,
             # Local observation time; rxTime is not a verified radio send timestamp.
             "event_timestamp": now.isoformat(), "gps_status": "missing"}
    gps = latest_positions.get(sender)
    if gps:
        gps_status = gps.get("rejected") or position_status(gps["latitude"], gps["longitude"], gps["timestamp"], now,
                                                          int(os.getenv("GPS_MAX_AGE_SECONDS", "300")))
        if gps_status == "valid":
            event["position"] = {"latitude": gps["latitude"], "longitude": gps["longitude"],
                                 "timestamp": gps["timestamp"].isoformat()}
        else:
            event["gps_status"] = gps_status
    snr = packet.get("rxSnr")
    if type(snr) in (int, float) and math.isfinite(snr) and -100 <= snr <= 100:
        event["snr"] = snr
    return event


def on_message(packet, interface=None):
    event = build_event(packet)
    if event is None:
        return
    log.info("SOS from %s, packet %s, GPS %s", event["node_id"], event["packet_id"],
             "valid" if event.get("position") else event["gps_status"])
    if outbox is None:
        log.error("Forwarding is not configured; SOS was not queued")
        return
    try:
        outbox.enqueue(event)
    except sqlite3.Error:
        log.exception("Could not persist SOS packet %s; check outbox storage immediately", event["packet_id"])


class Outbox:
    """On-disk retry queue; never logs keys or message bodies."""
    def __init__(self, path, api_url, api_key):
        parsed = urlparse(api_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("GATEWAY_API_URL must be an HTTP(S) URL without embedded credentials")
        if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Use HTTPS for a gateway API outside this laptop")
        if len(api_key) < 32:
            raise ValueError("Set GATEWAY_API_KEY to at least 32 random characters")
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.url = api_url.rstrip("/") + "/gateway/sos"
        self.key = api_key
        self.stop = threading.Event()
        self.wakeup = threading.Event()
        self.thread = None
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS outbox (
                node_id TEXT NOT NULL, packet_id INTEGER NOT NULL, payload TEXT NOT NULL,
                state TEXT NOT NULL DEFAULT 'pending', error TEXT,
                PRIMARY KEY (node_id, packet_id))""")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def enqueue(self, event):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO outbox(node_id,packet_id,payload) VALUES(?,?,?)",
                       (event["node_id"], event["packet_id"], json.dumps(event, allow_nan=False)))
        self.wakeup.set()

    def drain_once(self, client):
        with self.connect() as db:
            rows = db.execute("SELECT node_id,packet_id,payload FROM outbox WHERE state='pending' ORDER BY rowid LIMIT 100").fetchall()
        delivered = 0
        for node, packet, payload in rows:
            try:
                response = client.post(self.url, json=json.loads(payload), headers={"X-Gateway-Key": self.key})
            except httpx.HTTPError:
                log.warning("API unreachable; queued SOS retained for retry")
                break
            if response.status_code in (200, 201):
                with self.connect() as db:
                    db.execute("DELETE FROM outbox WHERE node_id=? AND packet_id=?", (node, packet))
                delivered += 1
                log.info("API stored SOS %s/%s (HTTP %s)", node, packet, response.status_code)
            elif response.status_code in (400, 403, 404, 405, 413, 422):
                with self.connect() as db:
                    db.execute("UPDATE outbox SET state='rejected',error=? WHERE node_id=? AND packet_id=?",
                               (f"HTTP {response.status_code}", node, packet))
                log.error("API rejected %s/%s (HTTP %s); retained in outbox for inspection", node, packet, response.status_code)
            else:
                log.warning("API HTTP %s; queued SOS retained (check key/service configuration)", response.status_code)
                break
        return delivered

    def run(self):
        with httpx.Client(timeout=5, trust_env=False) as client:
            while not self.stop.is_set():
                self.wakeup.clear()
                try:
                    self.drain_once(client)
                except sqlite3.Error:
                    log.exception("Outbox error; delivery will retry")
                self.wakeup.wait(5)

    def start(self):
        self.thread = threading.Thread(target=self.run, name="gateway-http", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wakeup.set()
        if self.thread:
            self.thread.join(timeout=7)


def load_cached_positions(interface):
    for node_id, node in (interface.nodes or {}).items():
        if node_id in allowed_nodes():
            save_position(node_id, node.get("position", {}))


def on_connected(interface, topic=None):
    load_cached_positions(interface)
    log.info("Gateway ONLINE; waiting for SOS messages and GPS updates")


def on_disconnected(interface=None):
    log.warning("Radio disconnected; check USB cable and MESHTASTIC_PORT")


def main():
    global outbox
    from dotenv import load_dotenv
    load_dotenv()
    import meshtastic.serial_interface
    from pubsub import pub

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    outbox = Outbox(os.getenv("GATEWAY_OUTBOX", "gateway-outbox.db"),
                    os.getenv("GATEWAY_API_URL", "http://localhost:8000"), os.getenv("GATEWAY_API_KEY", ""))
    outbox.start()
    # Preserve the original working event topics and SerialInterface setup.
    pub.subscribe(on_message, "meshtastic.receive.text")
    pub.subscribe(on_position, "meshtastic.receive.position")
    pub.subscribe(on_connected, "meshtastic.connection.established")
    pub.subscribe(on_disconnected, "meshtastic.connection.lost")
    radio = None
    try:
        port = os.getenv("MESHTASTIC_PORT", "COM9")
        log.info("Connecting to DisasterMesh Gateway on %s", port)
        radio = meshtastic.serial_interface.SerialInterface(devPath=port)
        load_cached_positions(radio)
        log.info("Gateway ONLINE; forwarding only SOS from %s", ", ".join(sorted(allowed_nodes())))
        while True:
            threading.Event().wait(1)
    except KeyboardInterrupt:
        log.info("Stopping gateway")
    finally:
        if radio:
            radio.close()
        outbox.close()


if __name__ == "__main__":
    main()
