import os
import re
import hmac
from datetime import datetime, timedelta, timezone
from enum import Enum

import jwt
from fastapi import Depends, FastAPI, HTTPException, Header, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pwdlib import PasswordHash
from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./disastermesh-dev.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "development-only-secret-not-for-deployment")
ALGORITHM = "HS256"
password_hash = PasswordHash.recommended()
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)
security = HTTPBearer(auto_error=False)
app = FastAPI(title="DisasterMesh API", version="0.1.0")

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

# Two-node prototype: one fixed sender radio and one USB gateway.
RESCUE_DEVICE_ID = "!0436bda8"
RESCUE_DEVICE_NAME = "Rescue Node"

class RadioMessage(Base):
    __tablename__ = "radio_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    packet_id: Mapped[str] = mapped_column(String(100))
    device_id: Mapped[str] = mapped_column(String(30))
    device_name: Mapped[str] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(Text)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    snr: Mapped[float | None] = mapped_column(Float, nullable=True)
    incident_id: Mapped[int | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("device_id", "packet_id", name="uq_radio_device_packet"),)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(80))
    incident_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

@app.on_event("startup")
def create_tables():
    # MVP only; switch to Alembic migrations before production.
    Base.metadata.create_all(bind=engine)

def get_db():
    with SessionLocal() as db:
        yield db

class GatewayMessageIn(BaseModel):
    packet_id: str = Field(min_length=1, max_length=100)
    device_id: str = Field(min_length=1, max_length=30)
    message: str = Field(min_length=1, max_length=1000)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    snr: float | None = Field(default=None, ge=-100, le=100)

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(min_length=12, max_length=128)

class LoginIn(BaseModel):
    username: str
    password: str

class IncidentIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    message: str = Field(min_length=5, max_length=3000)

class IncidentOut(BaseModel):
    id: int
    owner_id: int
    title: str
    message: str
    category: str
    priority: str
    state: str
    created_at: datetime
    model_config = {"from_attributes": True}

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
    if user is None:
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

def verify_gateway(x_gateway_key: str | None = Header(default=None)):
    expected = os.getenv("GATEWAY_KEY", "")
    if not expected or not x_gateway_key or not hmac.compare_digest(x_gateway_key, expected):
        raise HTTPException(status_code=401, detail="Invalid gateway credentials")

@app.post("/gateway/messages", status_code=201)
def receive_gateway_message(data: GatewayMessageIn, _: None = Depends(verify_gateway), db: Session = Depends(get_db)):
    if data.device_id != RESCUE_DEVICE_ID:
        raise HTTPException(status_code=403, detail="Device is not enrolled")
    old = db.scalar(select(RadioMessage).where(RadioMessage.device_id == data.device_id, RadioMessage.packet_id == data.packet_id))
    if old:
        return {"duplicate": True, "message_id": old.id, "incident_id": old.incident_id}
    # A fixed local responder account owns incident records, preserving the existing schema.
    owner_name = os.getenv("GATEWAY_OWNER_USERNAME", "responder1")
    owner = db.scalar(select(User).where(User.username == owner_name))
    if owner is None or owner.role not in ("responder", "admin"):
        raise HTTPException(status_code=503, detail="Configured responder account is missing or not a responder")
    incident_id = None
    # A simple two-node SOS demo: only SOS messages create incidents.
    if re.search(r"\bSOS\b", data.message, flags=re.IGNORECASE):
        category, priority = triage(data.message)
        incident = Incident(owner_id=owner.id, title="Radio SOS - " + RESCUE_DEVICE_NAME,
                            message=data.message, category=category,
                            priority="high", state="open")
        db.add(incident)
        db.flush()
        incident_id = incident.id
        audit(db, owner.id, "gateway.sos", incident_id)
    row = RadioMessage(packet_id=data.packet_id, device_id=RESCUE_DEVICE_ID,
                       device_name=RESCUE_DEVICE_NAME, message=data.message,
                       latitude=data.latitude, longitude=data.longitude,
                       snr=data.snr, incident_id=incident_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"duplicate": False, "message_id": row.id, "incident_id": incident_id}

@app.get("/gateway/messages")
def list_gateway_messages(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if user.role not in ("responder", "admin"):
        raise HTTPException(status_code=403, detail="Responder or admin required")
    rows = db.scalars(select(RadioMessage).order_by(RadioMessage.id.desc()).limit(50)).all()
    return [{"id": r.id, "device_id": r.device_id, "device_name": r.device_name,
             "message": r.message, "latitude": r.latitude, "longitude": r.longitude,
             "snr": r.snr, "incident_id": r.incident_id, "received_at": r.received_at}
            for r in rows]

@app.get("/health")
def health():
    return {"status": "ok", "ai_mode": os.getenv("AI_MODE", "rules")}

@app.post("/auth/register", status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
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
    if not user or not password_hash.verify(data.password, user.password_digest):
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
    return {"summary": fallback, "source": "rules"}
