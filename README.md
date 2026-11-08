# DisasterMesh

**Offline-radio emergency messaging prototype | Meshtastic + FastAPI + PostgreSQL + React**

> **Educational prototype — not a certified emergency or life-safety system.** DisasterMesh is a locally hosted, two-node proof of concept. Do not rely on it for actual rescue, dispatch, or medical emergencies.

## Project overview

During disasters, internet access and cellular infrastructure can become unreliable or unavailable. **DisasterMesh** explores a simple alternative for short-range emergency communication: a person sends a message from a portable Meshtastic LoRa radio, a second radio receives it, and a Mac-hosted application turns the message into a structured incident for a responder to review.

The prototype uses **two physical Meshtastic nodes**. The standalone **rescue sender** transmits messages over **channel index 1**. A separate **gateway receiver** is connected by USB to a Mac. A Python process reads received packets and forwards accepted messages to a locally running FastAPI application. FastAPI validates and authenticates the gateway request, stores the packet in PostgreSQL, and creates an incident for recognized emergency messages. A neon-red React command center lets responders view radio transmissions, see associated incidents, and change incident status.

A Meshtastic mobile app is used to send the three demonstration messages on channel 1. The phone connects to the standalone sender over Bluetooth; **the radio-to-radio hop uses LoRa, not internet**. The backend and browser run on the Mac; no Jetson, Ollama, or cloud service is required. An optional simulator can demonstrate the ingestion pipeline without radios.

### Project goals

- Demonstrate an end-to-end **two-radio LoRa → local software → incident dashboard** workflow.
- Turn three simple emergency message types into trackable incident records.
- Preserve received radio messages, timestamps, optional GPS, signal-to-noise ratio (SNR), incident links, and selected audit events in PostgreSQL.
- Restrict incident management by user role and protect the gateway HTTP endpoint with a dedicated key.
- Support repeatable tests and a live classroom/hackathon demonstration without cloud connectivity.

## Architecture

```text
Phone with Meshtastic app (channel 1)
    │ Bluetooth to standalone rescue sender
    ▼
Standalone Meshtastic rescue sender (!043877c8)
    │ Encrypted channel 1 LoRa transmission (when configured)
    ▼
Meshtastic gateway receiver (USB-connected to Mac)
    │ USB serial
    ▼
Mac: gateway/receiver.py
    │ HTTP POST /gateway/messages + X-Gateway-Key
    ▼
Docker: FastAPI backend ────────── PostgreSQL 17
    │                                  ├─ users
    │                                  ├─ radio_messages
    │                                  ├─ incidents
    │                                  └─ audit_logs
    ▼
Docker: Nginx + React command center at http://localhost:5173
```

The gateway Python script runs **directly on macOS** to access the USB device. FastAPI, PostgreSQL, and Nginx/React run inside Docker Compose. The PostgreSQL service has no published host database port; HTTP services bind to `127.0.0.1` for local use.

## Tech stack

| Component | Technology | Responsibility |
| --- | --- | --- |
| Radio network | Two Meshtastic LoRa-capable nodes | Transmit and receive short messages on shared channel 1 |
| Sender interface | Meshtastic mobile app | Sends SOS / Rescue, Medical Emergency, Supply Request |
| Gateway | Python, Meshtastic Python API, PyPubSub, Requests | Receive radio text/GPS and send valid packets to API |
| Backend | Python 3.12, FastAPI, SQLAlchemy | Gateway ingestion, rules-based classification, JWT authentication, RBAC |
| Database | PostgreSQL 17 | Store users, packets, incidents and audit records |
| Frontend | React 19, Vite, Nginx | Neon-red incident and radio-monitoring dashboard |
| Local deployment | Docker Compose + Docker Desktop on Mac | Start the backend, frontend and database together |
| Tests | Pytest, FastAPI TestClient | Check permissions, gateway ingestion, classification and deduplication |

## Supported emergency messages

| Message text | Incident category | Priority | Behavior |
| --- | --- | --- | --- |
| `SOS / Rescue` | `rescue` | `high` | Saves the radio packet and creates an incident |
| `Medical Emergency` | `medical` | `high` | Saves the radio packet and creates an incident |
| `Supply Request` | `supply` | `medium` | Saves the radio packet and creates an incident |
| Other radio text | — | — | Saves radio packet without automatically creating an incident |

Classification is **deterministic and keyword-based**; it is not an AI model and does not evaluate clinical or operational urgency. Newly received messages are classified when ingested. Older radio records with null `incident_id` are not automatically backfilled.

## Repository layout

```text
DisasterMesh/
├── backend/
│   ├── app/main.py              # FastAPI, models, endpoints and incident logic
│   ├── tests/test_api.py        # Authentication and incident API tests
│   ├── tests/test_gateway.py    # Gateway and emergency-classification tests
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/main.jsx             # React command center
│   ├── src/style.css            # Neon-red cyberpunk styling
│   ├── nginx.conf               # Frontend serving, API proxy and security headers
│   ├── package.json
│   └── Dockerfile
├── gateway/
│   ├── receiver.py              # USB Meshtastic → HTTP gateway
│   ├── simulate.py              # No-radio test message
│   ├── requirements.txt
│   └── .env.example
├── compose.yaml
├── .env.example
├── .gitignore
├── SECURITY-FINDINGS.md
└── README.md
```

## Prerequisites

- macOS laptop with Docker Desktop and Docker Compose.
- Python 3.12 or a compatible Python 3 version for the standalone gateway.
- Two compatible Meshtastic nodes, with the same region, modem preset, and a correctly configured shared **channel index 1** (including the same private channel key).
- USB **data** cable for the receiver and a Bluetooth-capable phone connected to the standalone sender.
- The USB receiver's macOS serial port, typically `/dev/cu.usbmodem...` or `/dev/cu.usbserial...`.

### 1. Clone and configure the stack

```bash
git clone https://github.com/jauregoa-hue/DisasterMesh.git
cd DisasterMesh
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Edit the **root `.env`** with a strong PostgreSQL password, one random `JWT_SECRET`, and a *different* random `GATEWAY_KEY` (generate another token for the gateway). Use `GATEWAY_OWNER_USERNAME=responder1` for the configured responder account. Keep `AI_MODE=rules`. If you already have a running PostgreSQL Docker volume, **keep your existing `.env` database password** rather than changing it casually; a mismatch will prevent login to the existing DB.

**Never commit `.env` or send actual keys or database dumps in public ZIPs.** `.env.example` contains placeholders only.

### 2. Start the application

```bash
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/health
```

Open:

- **Dashboard:** http://localhost:5173
- **FastAPI docs:** http://localhost:8000/docs
- **Health:** http://localhost:8000/health (expected JSON includes `"status":"ok"` and `"ai_mode":"rules"`)

Docker runs three services: `db`, `backend`, and `frontend`. Data is stored in the `pgdata` Docker volume. **Do not run `docker compose down -v`** unless you intentionally want to erase the database volume.

### 3. Create local demo accounts

Registration creates a **citizen** account. For a fresh local database, register `responder1` and a second citizen through the UI. The prototype intentionally does not allow anonymous users to self-assign responder/admin roles.

For local bootstrap, use the database console to promote a trusted test account (this is a **local administrator setup step**, not a production role-provisioning design):

```bash
docker compose exec db psql -U disastermesh -d disastermesh \
  -c "UPDATE users SET role='responder' WHERE username='responder1';"
```

Log out and sign back in to refresh the token. The account named by `GATEWAY_OWNER_USERNAME` must exist and have the `responder` or `admin` role, otherwise gateway ingestion returns HTTP `503`.

For an initial admin, use a **separate trusted account** with `role='admin'` via local database bootstrap. Afterward, admins can use `POST /admin/role` to manage user roles. Never provide demo passwords in the repository.

### 4. Set up the USB Meshtastic gateway

```bash
cd gateway
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m serial.tools.list_ports -v
cp .env.example .env
```

Edit `gateway/.env`:

```dotenv
GATEWAY_KEY=USE_THE_SAME_PRIVATE_GATEWAY_KEY_AS_ROOT_ENV
BACKEND_URL=http://127.0.0.1:8000
MESHTASTIC_PORT=/dev/cu.YOUR_REAL_USB_PORT
```

The same `GATEWAY_KEY` must be in the root `.env` and `gateway/.env`. The gateway receiver must be plugged into the Mac by USB; the rescue sender remains independently powered. Confirm the phone is paired **over Bluetooth to the standalone sender**, not the USB receiver. Select **channel 1** in the app.

Launch from the gateway directory:

```bash
python receiver.py
```

Keep this terminal open. The configured accepted rescue sender is `!043877c8`. If you swap the physical sender later, update the allowlist consistently in `gateway/receiver.py`, `backend/app/main.py`, and the frontend's displayed node ID. If the serial port is locked, close any other Meshtastic CLI/serial monitor before retrying.

### 5. Test the complete pipeline

From the phone paired with the rescue sender, select **channel 1** and transmit these three messages **one at a time**:

1. `SOS / Rescue`
2. `Medical Emergency`
3. `Supply Request`

For each one: inspect the gateway terminal for a received/forwarded packet, then check PostgreSQL from another terminal in the repository root:

```bash
docker compose exec db psql -U disastermesh -d disastermesh \
  -c "SELECT r.id, r.device_id, r.message, r.incident_id, i.category, i.priority, i.state FROM radio_messages r LEFT JOIN incidents i ON i.id=r.incident_id ORDER BY r.id DESC LIMIT 10;"
```

For **new** messages, expect `rescue / high`, `medical / high`, and `supply / medium`, each with a non-null incident ID. All three should show in the responder's **Radio Transmissions** and **Incidents** views. Change an incident status from `open` to `in_progress` or `resolved` to demonstrate responder workflow.

GPS is **optional** and is attached only if the gateway has recently received a valid position from the rescue sender (within 15 minutes); blank coordinates are expected when no fresh GPS was received. The application is not a live GPS tracker.

### 6. Test without a radio

With Docker running and the gateway key configured, from `gateway/` with its virtual environment activated:

```bash
python simulate.py
```

The script sends a test SOS directly to the backend with example coordinates, bypassing radio transmission. **Clearly label simulator output as simulated** during a demonstration. A successful request returns HTTP `201` and stores a message and incident.

## API and security overview

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /health` | Public (localhost) | Health and triage mode |
| `POST /auth/register` / `POST /auth/login` | Public (localhost) | Register citizen / get JWT |
| `GET /me` | JWT user | Current user details |
| `POST /incidents` / `GET /incidents` | JWT user | Report incidents / list permitted incidents |
| `PATCH /incidents/{id}` | Responder or admin | Change incident state |
| `GET /gateway/messages` | Responder or admin | See recent radio transmissions |
| `POST /gateway/messages` | `X-Gateway-Key` | Accept allowed rescue sender's packets |
| `GET /audit` / `POST /admin/role` | Admin | Audit and role-management endpoints |

Implemented controls include: JWT sign-in, Argon2-based password hashing, role checks, a separate gateway secret, fixed sender-ID allowlist, packet-ID deduplication (per sender), input-length/range checks, limited audit logging, loopback-only HTTP ports, a non-root backend container and Nginx security headers/rate limiting.

**Security limitations:** Node IDs can be spoofed and do not authenticate LoRa transmitters; gateway authentication applies only to the Mac-to-FastAPI request. GPS and SNR should be treated as untrusted/possibly stale. The HTTP gateway has **no durable retry queue**: if FastAPI is unavailable, forwarding may fail and the packet is not stored for later replay. Local HTTP isn't suitable for exposure to external networks; there is no TLS termination, complete abuse protection, data retention policy, or hardened production deployment. See `SECURITY-FINDINGS.md` and `SECURITY-UPDATE.md`; historical container scan findings are not proof that every issue was remediated.

## Automated tests

From project root on your Mac:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest tests -v
```

The tests cover existing account/incident permissions and gateway classification/authentication/deduplication; they use test SQLite databases rather than your running PostgreSQL volume. Test execution is still required on the user's machine; a README does not certify the build or physical devices.

Quick unauthenticated gateway check (run from any terminal while backend is up):

```bash
curl -s -o /dev/null -w 'HTTP %{http_code}\n' \
  -X POST http://127.0.0.1:8000/gateway/messages \
  -H 'Content-Type: application/json' \
  -d '{"packet_id":"unauthorized-test","device_id":"!043877c8","message":"SOS / Rescue"}'
```

Expected: `HTTP 401`.

Check frontend Nginx syntax:

```bash
docker compose exec frontend nginx -t
```

## Suggested live demonstration

1. Start Docker Compose; show containers and health endpoint.
2. Open the neon-red dashboard; sign in as a responder.
3. Show the separately powered rescue radio and USB-connected gateway; start `gateway/receiver.py`.
4. Select channel 1 in the Meshtastic phone app connected to the **rescue sender**.
5. Send **SOS / Rescue**; point out the received packet, new high-priority incident, and radio record.
6. Repeat with **Medical Emergency** (high) and **Supply Request** (medium).
7. Update one incident to `in_progress`, then `resolved`.
8. Display the PostgreSQL join query above to show packet → incident links and discuss optional GPS.
9. Show the automated tests and rejected unauthorized API request.
10. Walk through this GitHub repository and explain the two-node architecture and limitations.

## Future improvements

- Offline gateway retry queue, acknowledgements, and delivery monitoring.
- Better node enrollment/authenticity and radio-channel operations.
- Explicit GPS recency/location UI, mapping, and privacy controls.
- Database migrations with Alembic, retention policy, backup recovery testing, and production-grade secrets/TLS.
- Expanded automated integration tests against real radios and failure cases.

---

**Status:** Functional two-node architecture with validated local radio reception reported during development. Final three-category incident behavior, current automated test results, and GitHub synchronization must be confirmed by the demo/test commands above; no unsupported deployment guarantees are implied.
