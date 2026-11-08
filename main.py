import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from pwdlib import PasswordHash
from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from gateway_contract import position_status, utc

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./disastermesh-dev.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
security = HTTPBearer(auto_error=False)
@asynccontextmanager
async def lifespan(app):
    if len(JWT_SECRET) < 32:
        raise RuntimeError("Set JWT_SECRET to at least 32 random characters (scripts/setup.ps1).")
    if len(os.getenv("GATEWAY_API_KEY", "")) < 32:
        raise RuntimeError("Set GATEWAY_API_KEY to at least 32 random characters.")
    create_tables()
    yield


app = FastAPI(title="DisasterMesh API", version="0.2.0", lifespan=lifespan)
GATEWAY_USERNAME = "__meshtastic_gateway__"

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_digest: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="citizen")

class Incident(Base):
    __tablename__ = "incidents"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(120))
    message: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30))
    priority: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    gateway: Mapped["GatewayEvent | None"] = relationship(back_populates="incident", uselist=False, lazy="selectin")


class GatewayEvent(Base):
    # Separate additive table: existing incident/user columns and rows are untouched.
    __tablename__ = "gateway_events"
    __table_args__ = (UniqueConstraint("node_id", "packet_id", name="uq_gateway_node_packet"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id"), unique=True)
    node_id: Mapped[str] = mapped_column(String(9))
    packet_id: Mapped[int] = mapped_column(BigInteger)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    position_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    gps_status: Mapped[str] = mapped_column(String(20))
    snr: Mapped[float | None] = mapped_column(Float, nullable=True)
    incident: Mapped[Incident] = relationship(back_populates="gateway")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

def create_tables():
    # MVP only; switch to Alembic migrations before production.
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if not db.scalar(select(User).where(User.username == GATEWAY_USERNAME)):
            db.add(User(username=GATEWAY_USERNAME, password_digest=password_hash.hash(secrets.token_urlsafe(48)), role="gateway"))
            try:
                db.commit()
            except IntegrityError:
                db.rollback()  # Another API worker may have created the service identity.

def get_db():
    with SessionLocal() as db:
        yield db

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=12, max_length=128)

class LoginIn(BaseModel):
    username: str
    password: str

class IncidentIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=5, max_length=3000)


class GatewayOut(BaseModel):
    node_id: str
    packet_id: int
    event_timestamp: datetime
    position_timestamp: datetime | None
    latitude: float | None
    longitude: float | None
    gps_status: str
    snr: float | None
    model_config = {"from_attributes": True}

    @field_validator("event_timestamp", "position_timestamp")
    @classmethod
    def normalize_times(cls, value):
        return utc(value) if value else None


class PositionIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, strict=True)
    longitude: float = Field(ge=-180, le=180, strict=True)
    timestamp: AwareDatetime | None = None


class GatewayIn(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)
    node_id: str = Field(pattern=r"^![0-9a-f]{8}$")
    packet_id: int = Field(ge=1, le=4294967295, strict=True)
    message: str = Field(min_length=1, max_length=3000)
    event_timestamp: AwareDatetime
    position: PositionIn | None = None
    gps_status: Literal["missing", "stale", "future", "unknown_time", "invalid"] = "missing"
    snr: float | None = Field(default=None, ge=-100, le=100, strict=True)

    @model_validator(mode="after")
    def validate_event(self):
        if not re.search(r"\bsos\b", self.message, re.IGNORECASE):
            raise ValueError("Only messages containing the word SOS are ingested")
        if self.event_timestamp > datetime.now(timezone.utc) + timedelta(seconds=30):
            raise ValueError("Event timestamp is in the future; check the laptop clock")
        return self

class IncidentOut(BaseModel):
    id: int
    owner_id: int
    title: str
    message: str
    category: str
    priority: str
    state: str
    created_at: datetime
    gateway: GatewayOut | None = None
    model_config = {"from_attributes": True}

    @field_validator("created_at")
    @classmethod
    def normalize_created(cls, value):
        return utc(value)

class UpdateIn(BaseModel):
    state: str

class PromoteIn(BaseModel):
    username: str
    role: str

def token_for(user: User):
    exp = datetime.now(timezone.utc) + timedelta(hours=2)
    return jwt.encode({"sub": str(user.id), "exp": exp}, JWT_SECRET, algorithm=ALGORITHM)

def current_user(creds: HTTPAuthorizationCredentials | None = Depends(security), db: Session = Depends(get_db)) -> User:
    if creds is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        claims = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[ALGORITHM])
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or user.role == "gateway":
        raise HTTPException(status_code=401, detail="Account not found")
    return user

def triage(message: str):
    text = message.lower()
    patterns = {
        "medical": [r"\binjur", r"\bbleed", r"\bunconscious", r"\bmedical", r"\bheart attack"],
        "fire": [r"\bfire\b", r"\bsmoke\b", r"\bburning\b"],
        "flood": [r"\bflood", r"\bwater rising", r"\btrapped in water"],
        "rescue": [r"\btrapped\b", r"\bmissing\b", r"\bhelp me\b"],
    }
    category = next((key for key, needles in patterns.items() if any(re.search(x, text) for x in needles)), "other")
    critical = [r"\bunconscious\b", r"\bnot breathing\b", r"\btrapped\b", r"\bfire spreading\b"]
    priority = "high" if any(re.search(x, text) for x in critical) else ("medium" if category != "other" else "low")
    return category, priority

def audit(db: Session, actor_id: int, action: str, incident_id: int | None = None):
    db.add(AuditLog(actor_id=actor_id, action=action, incident_id=incident_id))

@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "ai_mode": os.getenv("AI_MODE", "rules"), "database": engine.dialect.name}


def gateway_auth(x_gateway_key: str | None = Header(default=None)):
    expected = os.getenv("GATEWAY_API_KEY", "")
    if len(expected) < 32:
        raise HTTPException(status_code=503, detail="Gateway ingestion is not configured")
    if not x_gateway_key or not secrets.compare_digest(x_gateway_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid gateway credentials")


@app.post("/gateway/sos", response_model=IncidentOut, status_code=201, dependencies=[Depends(gateway_auth)])
def ingest_sos(data: GatewayIn, response: Response, db: Session = Depends(get_db)):
    allowed = {x.strip().lower() for x in os.getenv("MESHTASTIC_ALLOWED_NODES", "!0436bda8").split(",") if x.strip()}
    if data.node_id not in allowed:
        raise HTTPException(status_code=403, detail="Node is not allowlisted")
    query = select(GatewayEvent).where(GatewayEvent.node_id == data.node_id, GatewayEvent.packet_id == data.packet_id)
    existing = db.scalar(query)
    if existing:
        response.status_code = 200
        return existing.incident
    owner = db.scalar(select(User).where(User.username == GATEWAY_USERNAME))
    if owner is None:
        raise HTTPException(status_code=503, detail="Gateway identity has not been initialized")
    gps_status = data.gps_status
    position = data.position
    if position:
        gps_status = position_status(position.latitude, position.longitude, position.timestamp,
                                     data.event_timestamp, int(os.getenv("GPS_MAX_AGE_SECONDS", "300")))
    category, priority = triage(data.message)
    incident = Incident(owner_id=owner.id, title=f"SOS from {data.node_id}", message=data.message,
                        category=category, priority="high" if priority == "low" else priority)
    incident.gateway = GatewayEvent(node_id=data.node_id, packet_id=data.packet_id,
                                   event_timestamp=utc(data.event_timestamp),
                                   position_timestamp=utc(position.timestamp) if position and position.timestamp else None,
                                   latitude=position.latitude if gps_status == "valid" else None,
                                   longitude=position.longitude if gps_status == "valid" else None,
                                   gps_status=gps_status, snr=data.snr)
    db.add(incident)
    try:
        db.flush()
        audit(db, owner.id, "gateway.sos.create", incident.id)
        db.commit()
    except IntegrityError:
        # DB uniqueness is authoritative, including concurrent requests and retries after restart.
        db.rollback()
        existing = db.scalar(query)
        if existing is None:
            raise
        response.status_code = 200
        return existing.incident
    db.refresh(incident)
    return incident

@app.post("/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    if data.username == GATEWAY_USERNAME:
        raise HTTPException(status_code=409, detail="Reserved username")
    if db.scalar(select(User).where(User.username == data.username)):
        raise HTTPException(status_code=409, detail="Username already exists")
    user = User(username=data.username, password_digest=password_hash.hash(data.password), role="citizen")
    db.add(user)
    db.commit()
    db.refresh(user)
    audit(db, user.id, "register")
    db.commit()
    return {"id": user.id, "username": user.username, "role": user.role}

@app.post("/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username))
    if not user or user.role == "gateway" or not password_hash.verify(data.password, user.password_digest):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    audit(db, user.id, "login")
    db.commit()
    return {"access_token": token_for(user), "token_type": "bearer", "role": user.role, "username": user.username}

@app.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}

@app.post("/incidents", response_model=IncidentOut, status_code=201)
def create_incident(data: IncidentIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    category, priority = triage(data.title + " " + data.message)
    incident = Incident(owner_id=user.id, title=data.title, message=data.message, category=category, priority=priority)
    db.add(incident)
    db.flush()
    audit(db, user.id, "incident.create", incident.id)
    db.commit()
    db.refresh(incident)
    return incident

@app.get("/incidents", response_model=list[IncidentOut])
def list_incidents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    stmt = select(Incident).order_by(Incident.id.desc())
    if user.role == "citizen":
        stmt = stmt.where(Incident.owner_id == user.id)
    return db.scalars(stmt.limit(200)).all()

@app.patch("/incidents/{incident_id}", response_model=IncidentOut)
def update_incident(incident_id: int, data: UpdateIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("responder", "admin"):
        raise HTTPException(status_code=403, detail="Responder or admin required")
    if data.state not in ("open", "in_progress", "resolved"):
        raise HTTPException(status_code=422, detail="Invalid status")
    incident = db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    incident.state = data.state
    audit(db, user.id, "incident.update." + data.state, incident_id)
    db.commit()
    db.refresh(incident)
    return incident

@app.get("/audit")
def get_audit(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(100)).all()
    return [{"id": row.id, "actor_id": row.actor_id, "action": row.action, "incident_id": row.incident_id, "at": row.created_at} for row in rows]

@app.post("/admin/role")
def promote_user(data: PromoteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    if data.role not in ("citizen", "responder", "admin"):
        raise HTTPException(status_code=422, detail="Invalid role")
    target = db.scalar(select(User).where(User.username == data.username))
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if target.username == GATEWAY_USERNAME:
        raise HTTPException(status_code=422, detail="Gateway identity cannot be promoted")
    target.role = data.role
    audit(db, user.id, "role.change." + data.role)
    db.commit()
    return {"username": target.username, "role": target.role}

@app.get("/incidents/{incident_id}/summary")
async def summary(incident_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    incident = db.get(Incident, incident_id)
    if not incident or (user.role == "citizen" and incident.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Incident not found")
    fallback = f"[{incident.priority.upper()}] {incident.category}: {incident.title}. {incident.message[:250]}"
    if os.getenv("AI_MODE", "rules") != "ollama":
        return {"summary": fallback, "source": "rules"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(os.getenv("OLLAMA_URL", "http://host.docker.internal:11434") + "/api/generate", json={
                "model": os.getenv("OLLAMA_MODEL", "gemma3:1b"), "stream": False,
                "prompt": "Summarize this disaster report in one neutral sentence. Do not invent facts or instructions. Report: " + incident.message,
                "options": {"num_predict": 100},
            })
            response.raise_for_status()
            return {"summary": response.json()["response"], "source": "ollama"}
    except (httpx.HTTPError, KeyError, ValueError):
        return {"summary": fallback, "source": "rules_fallback"}
