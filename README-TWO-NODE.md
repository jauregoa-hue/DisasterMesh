# DisasterMesh two-node Mac demo patch

This is a PATCH, not a full replacement project. It modifies only the listed files.

- `backend/app/main.py`: adds `radio_messages` table, authenticated `POST /gateway/messages`, responder `GET /gateway/messages`, and automatic incident creation for SOS messages. `Base.metadata.create_all` creates the new table without dropping old ones.
- `compose.yaml`: passes a secret gateway key and fixed responder username to FastAPI.
- `frontend/src/main.jsx`: displays received radio messages to responders and admins, refreshing every 5 seconds.
- `gateway/receiver.py`: runs on Mac and forwards only Meshtastic packets from `!0436bda8`.
- `gateway/simulate.py`: sends a harmless SOS demo without radios.
- `gateway/requirements.txt`, `gateway/.env.example`: gateway setup.
- `.gitignore`: excludes local secrets and scan artifacts.

## Setup
1. First back up your existing database. Preserve your original project and `.env` file.
2. Copy the files into the **same paths** in your current project. Do not move/delete the existing database volume.
3. Add `GATEWAY_KEY=<long random token>` and `GATEWAY_OWNER_USERNAME=responder1` to the project root `.env` (responder1 must already exist with role responder/admin). Use `python3 -c 'import secrets; print(secrets.token_urlsafe(48))'` to generate a value. Never commit the key.
4. Copy `gateway/.env.example` to `gateway/.env`, then replace the key placeholder with the SAME root `.env` key. Leave `MESHTASTIC_PORT=` blank to attempt auto detection, or set to the Mac `/dev/cu.*` port.
5. `docker compose config --quiet && docker compose up -d --build backend frontend`.
6. Test `curl http://127.0.0.1:8000/health`.
7. `cd gateway && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`.
8. `python simulate.py` to send a safe dummy SOS. Check responder dashboard at `http://localhost:5173` and `GET /gateway/messages` after login.
9. When ready, connect the USB radio and run `python receiver.py` from the gateway directory.

## Security and limitations
- Fixed node IDs are **not cryptographic authentication**. A transmitter can impersonate a node ID. Use Meshtastic channel encryption and physical demonstration constraints.
- Gateway API uses shared `X-Gateway-Key`, bound to Mac loopback. Keep key private and rotate if compromised.
- GPS is used only if received within 15 minutes. No offline queue: failed HTTP forwards are logged and dropped. This is a prototype, not emergency service.
- The backend uses deterministic rules only; the optional Ollama implementation is removed in this patch.
- Not all CVEs are fixed; leave known issues documented. No HTTPS for non-local clients.
