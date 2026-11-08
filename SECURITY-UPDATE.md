# DisasterMesh Docker Scout remediation pass — 2026-11-07

This is a **development prototype**, not a production-ready emergency communication service.

## Changes applied

- `frontend/Dockerfile`: Nginx runtime switched from `nginx:alpine` to `nginx:1.31-alpine-slim`, based on the provided Docker Scout recommendation (which still reports **1 critical and 1 high** in the proposed alternative at scan time). The image must be rebuilt and rescanned on your computer.
- `frontend/Dockerfile`: use `npm ci` with your committed `package-lock.json` instead of `npm install` to reduce version drift.
- `backend/Dockerfile`: explicitly upgrade pip to >=26.2.0,<27 as the supplied scanner reports several fixed pip issues by 26.2.0. If the image build fails because that version is unavailable on your configured Python package index, do not downgrade silently; review your index and rerun the scan.
- Added `.dockerignore` files to prevent development caches and accidental secret files from entering Docker build contexts.
- `compose.yaml`: **unchanged**; PostgreSQL 17 and its existing `pgdata` volume are preserved. The backend remains bound to `127.0.0.1:8000` for development; note that direct access bypasses Nginx rate limiting. Do not expose these services publicly.

## What is NOT fixed or verified

- PostgreSQL image `postgres:17` had 124 scanner findings, including 4 critical; the provided Scout recommendations say **No recommendations**. Those findings require investigation and upstream vendor updates; they are not automatically fixed by these edits. The `golang/stdlib` findings need reachability assessment.
- The Python base image had two reported high-severity Debian zlib findings without a listed fix. Backend runtime image changes alone do not guarantee remediation.
- The recommended Nginx slim image still has a reported critical zlib CVE and high-severity issue. This pass attempts to reduce the attack surface, **not to clear the critical finding**.
- The scanner results are from previously built images; no new images have been built or rescanned here.
- Source-level protections such as rate limiting, credential rotation, authentication revocation, audit completeness, and TLS deployment still need security review. The React site currently is development-only HTTP.

## Safe local rollout (Mac, inside disastermesh-starter)

1. Backup existing data:

   ```bash
   mkdir -p backups
   docker compose exec -T db pg_dump -U disastermesh -d disastermesh -Fc > backups/pre-security-update.dump
   ls -lh backups/pre-security-update.dump
   ```

2. Copy in the revised files, preserving the folder structure. Keep your **own `.env` file** unchanged, private, and outside version control. Do not overwrite your local project until you have a backup.
3. Rebuild only the two application images:

   ```bash
   docker compose build --pull --no-cache backend frontend
   docker compose up -d backend frontend
   docker compose ps
   ```

   If `pip>=26.2.0` cannot be installed, send the full error message and your `docker compose build backend` output; do not delete volumes.

4. Smoke checks:

   ```bash
   curl -f http://localhost:8000/health
   curl -I http://localhost:5173
   docker compose exec frontend nginx -t
   docker compose exec backend id
   docker compose exec db psql -U disastermesh -d disastermesh -c 'SELECT COUNT(*) FROM incidents;'
   ```

5. Run backend tests on your Mac from `backend/` with your existing venv:

   ```bash
   python -m pip install -r requirements.txt
   python -m pytest -q
   ```

6. Rescan the **newly built** images and record counts:

   ```bash
   docker scout cves disastermesh-starter-frontend:latest
   docker scout cves disastermesh-starter-backend:latest
   docker scout cves postgres:17
   ```

7. Inspect fixable severe findings:

   ```bash
   docker scout cves --only-fixed --only-severity critical,high disastermesh-starter-frontend:latest
   docker scout cves --only-fixed --only-severity critical,high disastermesh-starter-backend:latest
   docker scout cves --only-fixed --only-severity critical,high postgres:17
   ```

8. Do NOT run `docker compose down -v`, `docker volume prune`, or change PostgreSQL's major version casually. Your saved records are in a named volume.

## Commit guidance

Only commit sanitized source/configuration, including `.env.example` with placeholders. Never commit `.env`, JWT signing secrets, database dumps, private keys, or real emergency reports. Rotating any secrets previously shared or committed is recommended. Document unresolved CVEs before any real-world deployment.
