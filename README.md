# DisasterMesh - local Meshtastic SOS integration

Prototype for synthetic demonstrations, not a live emergency response service.

Tracker V2 `V2B2` (`!0436bda8`) -> direct LoRa -> Heltec V3 gateway (`!8fc42874`) -> Windows USB `COM9` -> Python receiver -> FastAPI -> PostgreSQL -> React.

The two boards run Meshtastic firmware. No Jetson, custom radio protocol, relay board, or cloud service is required. The phone app sends messages containing the word **SOS**; a physical SOS button and private DisasterMesh channel are still hardware work. Use only synthetic messages on the public Primary channel.

## Windows setup and launch

Run these commands from the repository root. Python 3.13/3.14 and Node.js 22+ are suitable; Chrome is needed only for browser tests. No administrator access or Docker is required for this path.

```powershell
Set-Location C:\Users\brand\MakeUC2026\DisasterMesh
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

`setup.ps1` preserves the existing virtual environment and `.env`. On first setup it generates independent random database, JWT, and gateway credentials. Keep `.env` private and ignored. `start.ps1` downloads a workspace-local PostgreSQL 17 archive on its first run (~382 MB), initializes persistent storage under `.local/postgres/data`, and starts the API and Vite in hidden background processes. PostgreSQL binds to `127.0.0.1:5432`; no Windows service is installed. The helper uses the [binary distribution linked by PostgreSQL](https://www.postgresql.org/download/windows/), downloaded from EDB.

Open:

- Dashboard: http://localhost:5173
- FastAPI docs: http://localhost:8000/docs
- Health: http://localhost:8000/health (`database` should be `postgresql`)

Register your own account in the dashboard, then grant it responder access locally:

```powershell
# Replace your_username with the account you registered.
.\.venv\Scripts\python.exe .\scripts\set_role.py your_username responder
```

Log out and back in. **Responders/admins see hardware SOS incidents.** Citizens see only their own submitted reports. Use `admin` instead of `responder` to bootstrap a local administrator. Public registration always creates citizens; `/admin/role` still requires an administrator token.

Connect the Heltec V3 and run the real gateway in another PowerShell terminal:

```powershell
Set-Location C:\Users\brand\MakeUC2026\DisasterMesh
.\.venv\Scripts\python.exe -m serial.tools.list_ports
.\.venv\Scripts\python.exe .\meshtastic_receiver.py
```

`MESHTASTIC_PORT=COM9` comes from `.env`. Close other Meshtastic/serial-monitor processes that hold COM9. Send `SOS test gps (test)` from V2B2's Meshtastic phone app. New incidents appear within about two seconds after ingestion; select **Acknowledged / in progress**, then **Resolved** using the existing status workflow. The gateway prints metadata and delivery status without printing keys or message bodies. It never sends automatic LoRa replies.

Stop local services without removing data:

```powershell
# Stop the receiver with Ctrl+C in its own terminal first.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop.ps1
```

`stop.ps1 -KeepDatabase` leaves PostgreSQL running. Service logs are `.local/backend.stderr.log`, `.local/backend.stdout.log`, and `.local/frontend.*.log`; PostgreSQL logs are `.local/postgres/server.log`. `start.ps1` refuses to replace processes already using ports 8000/5173. Use `-SkipDatabase` when you manage PostgreSQL separately, with a matching `.env` `DATABASE_URL`.

## Hardware-free demonstration

With the API running and a responder logged in:

```powershell
# Runs the actual receiver callbacks and HTTP outbox, never opens a COM port.
.\.venv\Scripts\python.exe .\scripts\simulate_gateway.py --packet-id 4000000001
# Same node + packet ID: HTTP 200, same incident, no duplicate or status reset.
.\.venv\Scripts\python.exe .\scripts\simulate_gateway.py --packet-id 4000000001
# Still creates an incident, with a clear location-unavailable explanation.
.\.venv\Scripts\python.exe .\scripts\simulate_gateway.py --gps stale
.\.venv\Scripts\python.exe .\scripts\simulate_gateway.py --gps missing
.\.venv\Scripts\python.exe .\scripts\simulate_gateway.py --gps future
```

Synthetic messages are explicitly labeled `[SIMULATED]`. Simulator coordinates are test data, never a fallback for missing hardware GPS. Stop the live receiver before running the simulator because both normally share the outbox.

## Configuration

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL URL; use `127.0.0.1` for native Windows PostgreSQL |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Local helper / Compose database credentials |
| `JWT_SECRET` | Random dashboard signing secret, 32+ characters |
| `GATEWAY_API_KEY` | Independent random gateway key, 32+ characters; never a `VITE_` variable |
| `MESHTASTIC_PORT` | Windows serial port, default `COM9` |
| `MESHTASTIC_ALLOWED_NODES` | Comma-separated node allowlist, default `!0436bda8` |
| `GATEWAY_API_URL` | API base URL, default `http://localhost:8000` |
| `GATEWAY_OUTBOX` | Persistent local receiver retry queue, default `./gateway-outbox.db` |
| `GPS_MAX_AGE_SECONDS` | Maximum fix age **at SOS observation time**, default 300 seconds |
| `VITE_MAP_TILE_URL` | Optional local tile URL template; empty uses online OpenStreetMap tiles |
| `AI_MODE` | Default `rules`; existing optional `ollama` summaries still work |

Environment variables override `.env`. API startup requires configured secrets; there is no built-in development signing key. `uvicorn --env-file .env` loads API settings; receiver and local operator scripts load `.env` themselves. A non-loopback receiver API requires HTTPS. Ordinary local development uses loopback HTTP.

For a SQLite-only software demo on a fresh checkout, run `setup.ps1 -SQLiteDemo`; startup then skips PostgreSQL. Existing `.env` files are deliberately preserved, so edit `DATABASE_URL=sqlite:///./disastermesh-dev.db` yourself if switching an existing setup. SQLite and PostgreSQL are different databases; switching does not migrate incidents.

## Gateway behavior and storage

`POST /gateway/sos` requires `X-Gateway-Key`. Dashboard JWTs cannot ingest radio events, and gateway keys cannot read responder data. Input includes node ID, uint32 Meshtastic packet ID, SOS message, timezone-aware local observation timestamp, optional SNR, and optional GPS fix with its original timestamp. Only allowlisted nodes and messages containing the standalone word `SOS` are accepted.

The existing text and position event topics and `SerialInterface` are retained. Imports never open a serial port, so simulated tests work without hardware. Cached positions load using their original fix time. The receiver saves an SOS in its local SQLite outbox before a separate worker sends HTTP, retrying connection failures, HTTP 401/429, and server failures about every five seconds. Outbox data survives restarts. HTTP 400/403/404/405/413/422 failures are retained as `rejected` rather than retried forever. After correcting configuration, an operator can inspect/requeue rejected rows locally; never delete the queue to fix connectivity.

The backend atomically creates the incident, its gateway metadata, and audit entry. A unique database constraint on `(node_id, packet_id)` handles duplicate/retried/concurrent requests. New packets return HTTP 201; duplicates return HTTP 200 with the original incident, preserving acknowledgements/resolution. Packet IDs include the full unsigned 32-bit range and are stored as PostgreSQL `BIGINT`.

`gateway_events` is an additive table linked to existing `incidents`. Existing user, incident, and audit columns/data remain intact. A reserved, non-login gateway service identity owns hardware incidents and audit events. JWT auth, role management, citizen reports, summaries, and responder updates are preserved. Startup uses `create_all` for this MVP; broader future schema changes need versioned migrations.

## GPS, maps, and offline use

- Missing coordinates, `(0,0)`, invalid/out-of-range/non-finite coordinates, missing fix times, stale fixes, and fixes later than the SOS observation are never mapped as real locations.
- The receiver omits unusable coordinates and sends an explanation. The API independently checks any supplied coordinates and original fix time. Unusable coordinates are stored as null; the incident is still kept.
- Invalid or older position updates cannot erase a newer valid fix; its original expiry still applies. A future-dated fix cannot become trusted simply by waiting for the laptop clock to catch up; a new usable fix is needed.
- Freshness is measured at SOS observation, not at delayed HTTP delivery. Incident location is a snapshot; later GPS updates do not move an existing incident. The timestamp is laptop observation time, not an authenticated radio send time.
- React Leaflet renders local markers and coordinate text. Tiles use the configured server or OpenStreetMap. If internet/tiles are unavailable, the UI explains the blank background; markers, coordinates, reports, and status controls still work. A local basemap is not bundled. Configure `VITE_MAP_TILE_URL` for a local tile service, then restart Vite or rebuild Docker.
- The dashboard polls its authenticated incident API every two seconds, cleans up on logout, and retries after temporary failures. Its current view is limited to the existing latest-200 incident feed.

Local operation needs dependencies installed beforehand. The public Primary channel and node-ID allowlist do **not** authenticate a person or prevent radio spoofing; the gateway API key protects ingestion from unauthorized HTTP callers. This remains a synthetic prototype with local HTTP and advisory rule triage.

## Tests and checks

```powershell
Set-Location C:\Users\brand\MakeUC2026\DisasterMesh
.\.venv\Scripts\python.exe -m pytest -q
npm.cmd run build
npm.cmd run test:e2e
.\.venv\Scripts\python.exe -m pip check
```

Python tests cover existing authentication/RBAC/audits, ingestion credentials, node filtering, simulated text/position packets, GPS edge cases, full-size packet IDs, atomic duplicate handling, concurrent duplicates, outbox restart/lost-response retries, status persistence, and preserving original incident tables/data. Browser tests use a separate SQLite file and ports 8001/5174; they cover polling without refresh, map markers with blocked tiles, duplicate suppression, stale GPS fallback, acknowledgements/resolution, summaries, citizen access, and logout. Chrome must be installed for the configured Playwright `chrome` channel.

To run the gateway suite against an available PostgreSQL database using `.env` credentials:

```powershell
.\.venv\Scripts\python.exe -c "import os,pytest; from dotenv import dotenv_values; os.environ['TEST_DATABASE_URL']=dotenv_values('.env')['DATABASE_URL']; raise SystemExit(pytest.main(['-q']))"
```

PostgreSQL tests create/drop unique `dm_test_*` schemas; the test role needs schema creation rights. The two original baseline API tests retain their in-memory SQLite fixture. Browser tests also accept `BROWSER_DATABASE_URL` for a **disposable** PostgreSQL database; they create synthetic accounts/incidents in that database. Test secrets in test configuration are test-only values, never production defaults.

## Docker alternative

Docker Desktop with Compose must be installed and running. Stop the native stack first to free ports 5432/8000/5173. From the root:

```powershell
docker compose up --build -d
docker compose ps
# Keep the USB receiver on Windows, outside Docker:
.\.venv\Scripts\python.exe .\meshtastic_receiver.py
# Stop containers while preserving PostgreSQL data:
docker compose down
```

Compose uses the root frontend Dockerfile, `Dockerfile.backend`, PostgreSQL 17, database/API health checks, loopback host ports, and a persistent `pgdata` volume. Its API database hostname is `db`; native `.env` `DATABASE_URL` is not passed into the container. The UI uses Nginx `/api/` proxying, while Vite uses the same API prefix in development. Never run `docker compose down -v` unless intentionally deleting the Docker database. Native `.local/postgres/data` and Docker `pgdata` are independent stores.

Docker builds/runtime require Docker; YAML validation alone does not verify image builds. No serial receiver container or USB passthrough is configured.

## Troubleshooting

- **No COM9 / no serial ports:** reconnect/power the Heltec V3 using a data USB cable, check Device Manager, install its USB driver if needed, then update `MESHTASTIC_PORT` to the listed port. The phone's Bluetooth connection to the Tracker is separate from the gateway USB connection.
- **GPS stale/future/unknown:** wait for a timestamped Tracker fix, check clocks, and inspect the position time. Coordinates are intentionally withheld until valid. No gateway/UC default point is substituted.
- **Gateway HTTP 401:** API and Windows receiver must use the same `GATEWAY_API_KEY`; restart both after editing `.env`. Unsent packets stay queued.
- **Gateway HTTP 403:** check `MESHTASTIC_ALLOWED_NODES` on both API and receiver. Radio node IDs can be spoofed on the public channel.
- **Nothing on a citizen dashboard:** grant responder access with `set_role.py`, then log out/back in.
- **API cannot connect to PostgreSQL:** run `local_postgres.py status`, inspect the server log, and match `DATABASE_URL` credentials to the initialized database. Changing `.env` does not rotate an existing database password. Use `127.0.0.1` rather than `localhost` for native PostgreSQL to avoid IPv6 connection delays observed on this machine.
- **Windows blocks a SQLAlchemy native extension:** this environment was verified with SQLAlchemy 2.0 (requirements excludes 2.1). If policy blocks a wheel, build that package locally with `$env:DISABLE_SQLALCHEMY_CEXT='1'` and `python -m pip install --force-reinstall --no-cache-dir --no-binary sqlalchemy 'sqlalchemy>=2.0,<2.1'` inside the virtual environment.
