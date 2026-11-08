from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
import main


def event(**changes):
    now = datetime.now(timezone.utc)
    data = {"node_id": "!0436bda8", "packet_id": 4294967295, "message": "SOS person trapped near bridge",
            "event_timestamp": now.isoformat(), "position": {
                "latitude": 39.1380992, "longitude": -84.4890112, "timestamp": (now - timedelta(seconds=10)).isoformat()}}
    data.update(changes)
    return data


def test_ingestion_auth_and_allowlist(client, gateway_headers, responder):
    assert client.post("/gateway/sos", json=event()).status_code == 401
    assert client.post("/gateway/sos", json=event(), headers=responder).status_code == 401
    assert client.post("/gateway/sos", json=event(), headers={"X-Gateway-Key": "wrong"}).status_code == 401
    assert client.post("/gateway/sos", json=event(node_id="!12345678"), headers=gateway_headers).status_code == 403
    assert client.get("/incidents", headers=gateway_headers).status_code == 401
    assert client.post("/auth/register", json={"username": main.GATEWAY_USERNAME, "password": "LongTestPassword123!"}).status_code == 409


def test_sos_persistence_duplicate_and_responder_workflow(client, db_factory, gateway_headers, responder):
    payload = event()
    first = client.post("/gateway/sos", json=payload, headers=gateway_headers)
    assert first.status_code == 201
    incident = first.json()
    assert incident["gateway"]["packet_id"] == 4294967295
    assert incident["gateway"]["gps_status"] == "valid"
    assert incident["gateway"]["latitude"] == 39.1380992
    assert incident["created_at"].endswith("Z") or incident["created_at"].endswith("+00:00")
    again = client.post("/gateway/sos", json=payload, headers=gateway_headers)
    assert again.status_code == 200 and again.json()["id"] == incident["id"]
    for state in ("in_progress", "resolved"):
        updated = client.patch(f'/incidents/{incident["id"]}', json={"state": state}, headers=responder)
        assert updated.status_code == 200 and updated.json()["state"] == state
    # A duplicate must not reopen a resolved incident or overwrite original message/GPS.
    duplicate = client.post("/gateway/sos", json=event(message="SOS different retry"), headers=gateway_headers).json()
    assert duplicate["state"] == "resolved" and duplicate["message"] == payload["message"]
    assert len(client.get("/incidents", headers=responder).json()) == 1
    assert client.get(f'/incidents/{incident["id"]}/summary', headers=responder).json()["source"] == "rules"
    citizen = {"username": "citizen", "password": "LongTestPassword123!"}
    client.post("/auth/register", json=citizen)
    headers = {"Authorization": "Bearer " + client.post("/auth/login", json=citizen).json()["access_token"]}
    assert client.get("/incidents", headers=headers).json() == []
    assert client.patch(f'/incidents/{incident["id"]}', json={"state": "resolved"}, headers=headers).status_code == 403
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(main.GatewayEvent)) == 1
        assert db.scalar(select(func.count()).select_from(main.AuditLog).where(main.AuditLog.action == "gateway.sos.create")) == 1


@pytest.mark.parametrize("offset,status", [(-10, "valid"), (-301, "stale"), (1, "future"), (None, "unknown_time")])
def test_backend_rechecks_gps(client, gateway_headers, offset, status):
    data = event()
    now = datetime.fromisoformat(data["event_timestamp"])
    data["position"]["timestamp"] = (now + timedelta(seconds=offset)).isoformat() if offset is not None else None
    response = client.post("/gateway/sos", json=data, headers=gateway_headers)
    assert response.status_code == 201
    gps = response.json()["gateway"]
    assert gps["gps_status"] == status
    assert (gps["latitude"] is not None) == (status == "valid")
    assert (gps["longitude"] is not None) == (status == "valid")


@pytest.mark.parametrize("status", ["missing", "stale", "future", "unknown_time", "invalid"])
def test_sos_without_usable_location_is_kept(client, gateway_headers, status):
    response = client.post("/gateway/sos", headers=gateway_headers, json=event(position=None, gps_status=status))
    assert response.status_code == 201
    gps = response.json()["gateway"]
    assert gps["latitude"] is None and gps["longitude"] is None and gps["gps_status"] == status


@pytest.mark.parametrize("changes", [{"packet_id": 0}, {"packet_id": -1}, {"packet_id": True}, {"packet_id": "42"},
    {"packet_id": 4294967296}, {"message": "status hello"}, {"message": "SOS" * 1100}, {"message": "   "},
    {"node_id": "invalid"}, {"event_timestamp": "2026-01-01T00:00:00"},
    {"event_timestamp": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, {"unexpected": "value"},
    {"position": {"latitude": 91, "longitude": 10}}, {"position": {"latitude": True, "longitude": 10}},
    {"gps_status": "valid"}])
def test_malformed_events_rejected(client, gateway_headers, changes):
    assert client.post("/gateway/sos", headers=gateway_headers, json=event(**changes)).status_code == 422


def test_zero_zero_is_not_mapped(client, gateway_headers):
    data = event()
    data["position"].update(latitude=0, longitude=0)
    gps = client.post("/gateway/sos", headers=gateway_headers, json=data).json()["gateway"]
    assert gps["gps_status"] == "invalid" and gps["latitude"] is None


def test_concurrent_duplicates_create_one_incident(client, gateway_headers, db_factory):
    payload = event()
    def post(_):
        return client.post("/gateway/sos", headers=gateway_headers, json=payload)
    with ThreadPoolExecutor(max_workers=6) as workers:
        responses = list(workers.map(post, range(6)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    with db_factory() as db:
        assert db.scalar(select(func.count()).select_from(main.Incident)) == 1


def test_restart_preserves_deduplication(client, gateway_headers):
    data = event()
    first = client.post("/gateway/sos", headers=gateway_headers, json=data)
    main.create_tables()  # Same startup operation against an already populated database.
    second = client.post("/gateway/sos", headers=gateway_headers, json=data)
    assert second.status_code == 200 and first.json()["id"] == second.json()["id"]


def test_upgrade_preserves_original_incident_schema_and_data(db_factory):
    # Reproduce the original three tables, then apply the additive gateway startup.
    main.Base.metadata.create_all(main.engine, tables=[main.User.__table__, main.Incident.__table__, main.AuditLog.__table__])
    with db_factory() as db:
        user = main.User(username="existing", password_digest=main.password_hash.hash("LongTestPassword123!"), role="citizen")
        db.add(user)
        db.flush()
        incident = main.Incident(owner_id=user.id, title="Existing report", message="Keep this report", category="other", priority="low", state="resolved")
        db.add(incident)
        db.flush()
        incident_id = incident.id
        db.commit()
    main.create_tables()
    with db_factory() as db:
        preserved = db.get(main.Incident, incident_id)
        assert preserved.title == "Existing report" and preserved.state == "resolved" and preserved.gateway is None
