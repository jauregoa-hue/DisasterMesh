import sqlite3
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import meshtastic_receiver as receiver
from gateway_contract import position_status

NODE = "!0436bda8"


def packet(**changes):
    data = {"fromId": NODE, "id": 42, "decoded": {"text": "Sos test gps (test)"}, "rxSnr": 5.25}
    data.update(changes)
    return data


def test_real_callbacks_forward_to_api_without_hardware(client, db_factory, responder, tmp_path, monkeypatch):
    queue = receiver.Outbox(tmp_path / "outbox.db", "http://localhost:8000", "test-only-gateway-key-at-least-32-characters")
    monkeypatch.setattr(receiver, "outbox", queue)
    receiver.on_position({"fromId": NODE, "decoded": {"position": {
        "latitudeI": 391380992, "longitudeI": -844890112, "time": int(datetime.now(timezone.utc).timestamp())}}})
    receiver.on_message(packet())
    assert queue.drain_once(client) == 1
    rows = client.get("/incidents", headers=responder).json()
    assert len(rows) == 1 and rows[0]["gateway"]["latitude"] == pytest.approx(39.1380992)
    assert rows[0]["gateway"]["node_id"] == NODE


def test_lost_http_response_replays_after_outbox_restart(client, tmp_path, db_factory):
    path = tmp_path / "outbox.db"
    queue = receiver.Outbox(path, "http://localhost:8000", "test-only-gateway-key-at-least-32-characters")
    event = receiver.build_event(packet())
    queue.enqueue(event)
    class LostResponse:
        def post(self, *args, **kwargs):
            assert client.post(*args, **kwargs).status_code == 201
            raise httpx.ReadTimeout("response lost after commit")
    assert queue.drain_once(LostResponse()) == 0
    restarted = receiver.Outbox(path, "http://localhost:8000", queue.key)
    assert restarted.drain_once(client) == 1
    with db_factory() as db:
        import main
        assert db.query(main.Incident).count() == 1
    with restarted.connect() as db:
        assert db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 0


@pytest.mark.parametrize("status_code,state", [(401, "pending"), (503, "pending"), (422, "rejected"), (403, "rejected")])
def test_outbox_failure_retention(tmp_path, status_code, state):
    queue = receiver.Outbox(tmp_path / "outbox.db", "http://localhost:8000", "test-only-gateway-key-at-least-32-characters")
    queue.enqueue(receiver.build_event(packet()))
    with httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(status_code))) as client:
        assert queue.drain_once(client) == 0
    with queue.connect() as db:
        assert db.execute("SELECT state FROM outbox").fetchone()[0] == state


@pytest.mark.parametrize("offset,status", [(-10, "valid"), (-301, "stale"), (1, "future"), (None, "unknown_time")])
def test_cached_position_freshness(offset, status):
    receiver.latest_positions.clear()
    now = datetime.now(timezone.utc)
    position = {"latitude": 39.1, "longitude": -84.4}
    if offset is not None: position["time"] = (now + timedelta(seconds=offset)).timestamp()
    receiver.save_position(NODE, position)
    event = receiver.build_event(packet(), now=now)
    assert ("position" in event) == (status == "valid")
    if status != "valid": assert event["gps_status"] == status


@pytest.mark.parametrize("lat,lon,status", [(0, 0, "invalid"), (0, 2, "valid"), (90, 180, "valid"),
    (91, 0, "invalid"), (0, -181, "invalid"), (float("nan"), 2, "invalid"),
    (float("inf"), 2, "invalid"), (True, 2, "invalid"), (None, 2, "missing")])
def test_invalid_coordinates(lat, lon, status):
    now = datetime.now(timezone.utc)
    assert position_status(lat, lon, now, now) == status


def test_filtering_and_missing_packet_identity():
    assert receiver.build_event(packet(fromId="!12345678")) is None
    assert receiver.build_event(packet(decoded={"text": "status hello"})) is None
    assert receiver.build_event(packet(id=None)) is None
    assert receiver.build_event(packet(id=True)) is None
    assert receiver.build_event(packet(decoded={"text": "sososo"})) is None
    assert receiver.sender_id({"from": int("0436bda8", 16)}) == NODE


def test_missing_gps_and_missing_time_are_never_replaced_with_now():
    receiver.latest_positions.clear()
    assert receiver.build_event(packet())["gps_status"] == "missing"
    receiver.save_position(NODE, {"latitude": 39.1, "longitude": -84.4})
    assert receiver.build_event(packet())["gps_status"] == "unknown_time"


def test_key_and_transport_configuration(tmp_path):
    with pytest.raises(ValueError): receiver.Outbox(tmp_path / "a.db", "http://localhost:8000", "")
    with pytest.raises(ValueError): receiver.Outbox(tmp_path / "a.db", "http://192.168.1.5:8000", "x" * 32)


def test_bad_or_out_of_order_updates_preserve_latest_valid_fix():
    receiver.latest_positions.clear()
    now = datetime.now(timezone.utc)
    good = {"latitude": 39.1, "longitude": -84.4, "time": (now - timedelta(seconds=10)).timestamp()}
    receiver.save_position(NODE, good)
    for bad in ({"latitude": 0, "longitude": 0},
                {**good, "latitude": 10, "time": (now - timedelta(seconds=30)).timestamp()},
                {**good, "latitude": 20, "time": (now + timedelta(seconds=10)).timestamp()}):
        receiver.save_position(NODE, bad)
        assert receiver.build_event(packet(), now=now)["position"]["latitude"] == 39.1
    # The preserved fix still expires using its original timestamp.
    assert receiver.build_event(packet(), now=now + timedelta(seconds=400))["gps_status"] == "stale"


def test_future_fix_does_not_become_trusted_by_waiting():
    receiver.latest_positions.clear()
    now = datetime.now(timezone.utc)
    receiver.save_position(NODE, {"latitude": 39.1, "longitude": -84.4, "time": (now + timedelta(seconds=5)).timestamp()})
    event = receiver.build_event(packet(), now=now + timedelta(seconds=20))
    assert event["gps_status"] == "future" and "position" not in event
