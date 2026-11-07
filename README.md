# DisasterMesh — local software/cyber MVP

**Prototype only: not for live emergency response.** Uses simulated incident reports. No radio integration, automatic LoRa acknowledgement, offline client synchronization, location/map, full observability, TLS or hardened rate limiting yet.

## Stack
- React (frontend via Nginx)
- Python FastAPI (backend, JWT auth, role-aware incident API)
- PostgreSQL (persistent database)
- Docker Compose (orchestration)
- Deterministic triage rules; optional Ollama summary with automatic rules fallback

## Start (Mac, Docker Desktop)

```bash
cp .env.example .env
python3 -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Edit `.env` and replace **both** secret placeholders with **different** random values. Do not commit `.env`.

```bash
docker compose up --build -d
docker compose ps
```

Open http://localhost:5173 for UI, http://localhost:8000/docs for API documentation, and http://localhost:8000/health for health. Create a citizen through UI.

## Grant a responder role for local testing

Register two user accounts via UI, e.g. `citizen1` and `responder1`. There is intentionally **no public admin registration or public self-promotion**. To bootstrap the *first* admin on your local machine:

```bash
docker compose exec db psql -U disastermesh -d disastermesh -c "UPDATE users SET role='admin' WHERE username='responder1';"
```

This uses `.env.example` default database/user names; adjust the psql arguments if you changed them. Log out and log back in as `responder1` to get a new token; it is now an admin. In the API docs, use `POST /admin/role` with an admin bearer token to grant another registered user the `responder` role. Alternatively, for a simple *local test only*, set `responder1` directly to `responder` in the same SQL command; use a distinct admin account to test audits and role management.

### Expected roles
- Citizen can create/list only own incidents and summarize only own incidents.
- Responder can list all incidents and update statuses.
- Admin has responder privileges and reads the audit log / changes roles.

## Automated API tests (Docker not required)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

## Verify PostgreSQL persistence

```bash
docker compose exec db psql -U disastermesh -d disastermesh -c "SELECT id, title, category, priority, state FROM incidents;"
docker compose exec db psql -U disastermesh -d disastermesh -c "SELECT id, actor_id, action FROM audit_logs ORDER BY id DESC LIMIT 10;"
```

Stop without deleting data: `docker compose down`. Avoid `docker compose down -v` unless you intentionally want to delete your database volume.

## Ollama (optional, later)

Run Ollama on **the host**, pull a *small* model for Jetson, then set `AI_MODE=ollama`, `OLLAMA_MODEL=gemma3:1b`, and `OLLAMA_URL=http://host.docker.internal:11434` in `.env`. `docker compose up -d --force-recreate backend`. On Mac, Ollama's service must explicitly allow container access and must not be exposed on untrusted networks. On Jetson, the address and NVIDIA runtime may differ. Keep rules-only mode for the first complete test.

## Hardware bridge contract (future work)

Implement a separate service that ingests a versioned message envelope (packet ID, sender pseudonymous ID, timestamp, type, payload, optional coordinates, signature/MAC, TTL, hop count). Validate message size, replay protection, permissions, authenticity, and duplicate packets before inserting into database. Radio boards belong to hardware teammates, not the browser/backend direct path.

## Known security gaps before any live deployment

1. Local HTTP only; terminate HTTPS with a reverse proxy for network access.
2. Login rate limiting and account lockout / abuse prevention needed.
3. Backend tokens are kept only in React process memory (lost on refresh), not in localStorage; design secure token refresh later.
4. Replace `Base.metadata.create_all` with Alembic migrations and database least-privilege roles.
5. Review data retention, encryption at rest, backups, recovery, log integrity and privacy.
6. Use locked dependency versions, image scanning, nonroot containers, resource caps and security headers.
7. Radio message transport, acknowledgements and store-and-forward have not been implemented.
8. Rule triage is *not* a substitute for human judgment; LLM summaries must remain advisory.
