import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-key-do-not-use-for-real-32-characters"

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from main import app, Base, get_db, User, current_user, triage

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(bind=engine)

def db_override():
    with Session() as db:
        yield db

app.dependency_overrides[get_db] = db_override
Base.metadata.create_all(engine)
client = TestClient(app)

def test_triage():
    assert triage("Person trapped in a building") == ("rescue", "high")
    assert triage("Need supplies") == ("other", "low")

def test_auth_incident_permissions_and_audit():
    client.post("/auth/register", json={"username":"alice", "password":"LongTestPassword123!"})
    client.post("/auth/register", json={"username":"bob", "password":"LongTestPassword123!"})
    a = client.post("/auth/login", json={"username":"alice", "password":"LongTestPassword123!"}).json()["access_token"]
    b = client.post("/auth/login", json={"username":"bob", "password":"LongTestPassword123!"}).json()["access_token"]
    ah = {"Authorization":f"Bearer {a}"}
    bh = {"Authorization":f"Bearer {b}"}
    r = client.post("/incidents",headers=ah,json={"title":"Bridge blocked", "message":"Road blocked by debris"})
    assert r.status_code == 201
    incident_id = r.json()["id"]
    assert r.json()["state"] == "open"
    assert client.get("/incidents",headers=bh).json() == []
    assert client.patch(f"/incidents/{incident_id}",headers=ah,json={"state":"resolved"}).status_code == 403
    assert client.get("/audit",headers=ah).status_code == 403
    assert client.get("/incidents").status_code == 401
    assert client.get(f"/incidents/{incident_id}/summary",headers=bh).status_code == 404
    with Session() as db:
        admin = db.query(User).filter(User.username=="alice").one()
        admin.role="admin"
        db.commit()
    assert client.post("/admin/role",headers=ah,json={"username":"bob","role":"responder"}).status_code == 200
    assert client.patch(f"/incidents/{incident_id}",headers=bh,json={"state":"resolved"}).status_code == 200
    assert len(client.get("/audit",headers=ah).json()) >= 3
