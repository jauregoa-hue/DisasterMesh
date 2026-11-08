import os
import uuid

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["JWT_SECRET"] = "test-only-jwt-key-at-least-32-characters"
os.environ["GATEWAY_API_KEY"] = "test-only-gateway-key-at-least-32-characters"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import main
import meshtastic_receiver as receiver


@pytest.fixture
def db_factory(tmp_path, monkeypatch):
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        # A unique schema keeps all test data separate from existing application tables.
        schema = "dm_test_" + uuid.uuid4().hex
        bootstrap = create_engine(test_url)
        with bootstrap.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(test_url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False, "timeout": 20})
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", factory)
    monkeypatch.setenv("GATEWAY_API_KEY", "test-only-gateway-key-at-least-32-characters")
    monkeypatch.setenv("MESHTASTIC_ALLOWED_NODES", "!0436bda8")
    monkeypatch.setenv("GPS_MAX_AGE_SECONDS", "300")
    # The original test module has its own dependency override; isolate this suite.
    overrides = main.app.dependency_overrides.copy()
    main.app.dependency_overrides.clear()
    receiver.latest_positions.clear()
    yield factory
    receiver.latest_positions.clear()
    main.app.dependency_overrides.clear()
    main.app.dependency_overrides.update(overrides)
    engine.dispose()
    if test_url:
        with bootstrap.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        bootstrap.dispose()


@pytest.fixture
def client(db_factory):
    with TestClient(main.app) as client:
        yield client


@pytest.fixture
def gateway_headers():
    return {"X-Gateway-Key": os.environ["GATEWAY_API_KEY"]}


@pytest.fixture
def responder(client, db_factory):
    data = {"username": "responder", "password": "LongTestPassword123!"}
    assert client.post("/auth/register", json=data).status_code == 201
    with db_factory() as db:
        user = db.scalar(main.select(main.User).where(main.User.username == data["username"]))
        user.role = "responder"
        db.commit()
    token = client.post("/auth/login", json=data).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
