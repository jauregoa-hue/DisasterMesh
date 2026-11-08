"""Workspace-local Windows PostgreSQL; no installer, Windows service, or Docker.

Source: https://www.postgresql.org/download/windows/ -> EDB binary archives.
The archive and persistent data live under ignored .local/postgres. Never deletes data.
"""
import argparse
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import psycopg
from dotenv import dotenv_values
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
PGROOT = ROOT / ".local" / "postgres"
BIN = PGROOT / "pgsql" / "bin"
DATA = PGROOT / "data"
ARCHIVE_URL = "https://get.enterprisedb.com/postgresql/postgresql-17.11-5-windows-x64-binaries.zip"


def run(*args, check=True):
    return subprocess.run([str(x) for x in args], check=check,
                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--download", action="store_true", help="Download EDB Windows binaries when absent")
    args = parser.parse_args()
    if os.name != "nt": parser.error("This helper is for Windows; use Docker Compose on other platforms")
    env = {**dotenv_values(ROOT / ".env"), **os.environ}
    if not (BIN / "pg_ctl.exe").exists():
        if args.action != "start" or not args.download:
            parser.error("PostgreSQL binaries missing. Run start --download first.")
        PGROOT.mkdir(parents=True, exist_ok=True)
        archive = PGROOT / "postgresql-binaries.zip"
        if not archive.exists() or not zipfile.is_zipfile(archive):
            print("Downloading EDB PostgreSQL 17 Windows archive (~382 MB)...", flush=True)
            with httpx.stream("GET", ARCHIVE_URL, follow_redirects=True, timeout=60) as response:
                response.raise_for_status()
                with archive.open("wb") as stream:
                    for chunk in response.iter_bytes(1024 * 1024): stream.write(chunk)
        print("Extracting PostgreSQL bin/lib/share files...", flush=True)
        with zipfile.ZipFile(archive) as bundle:
            for name in bundle.namelist():
                if name.startswith(("pgsql/bin/", "pgsql/lib/", "pgsql/share/")):
                    target = (PGROOT / name).resolve()
                    if not target.is_relative_to(PGROOT.resolve()):
                        raise ValueError("Archive path is outside PostgreSQL directory")
                    bundle.extract(name, PGROOT)
    if args.action in ("stop", "status"):
        if not (DATA / "PG_VERSION").exists(): parser.error("No workspace PostgreSQL database initialized")
        extra = ["-m", "fast", "-w"] if args.action == "stop" else []
        return run(BIN / "pg_ctl.exe", "-D", DATA, args.action, *extra, check=False).returncode
    password = env.get("POSTGRES_PASSWORD", "")
    if not password: parser.error("Run scripts/configure_env.py first to create .env credentials")
    database = env.get("POSTGRES_DB", "disastermesh")
    username = env.get("POSTGRES_USER", "disastermesh")
    # Refuse to start alongside an unrelated PostgreSQL installation on the same port.
    if (DATA / "PG_VERSION").exists():
        status = subprocess.run([str(BIN / "pg_ctl.exe"), "-D", str(DATA), "status"], capture_output=True,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if status.returncode == 0:
            print("Workspace PostgreSQL is already running on 127.0.0.1:5432.")
            return 0
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 5432)) == 0:
            parser.error("Port 5432 is already in use. Use the existing database or stop it yourself.")
    admin_file = PGROOT / "admin-password"
    if not (DATA / "PG_VERSION").exists():
        admin_password = secrets.token_urlsafe(48)
        admin_file.write_text(admin_password, encoding="utf-8")
        with tempfile.NamedTemporaryFile(mode="w", dir=PGROOT, delete=False, encoding="utf-8") as stream:
            stream.write(admin_password + "\n")
            password_file = Path(stream.name)
        try:
            run(BIN / "initdb.exe", "-D", DATA, "-U", "local_admin", "--pwfile", password_file,
                "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C")
        finally:
            password_file.unlink(missing_ok=True)
    run(BIN / "pg_ctl.exe", "-D", DATA, "-l", PGROOT / "server.log", "-o", "-h 127.0.0.1 -p 5432", "-w", "start")
    with psycopg.connect(host="127.0.0.1", port=5432, dbname="postgres", user="local_admin",
                         password=admin_file.read_text(encoding="utf-8"), autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (username,)).fetchone():
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(sql.Identifier(username), sql.Literal(password)))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (database,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(database), sql.Identifier(username)))
    print("PostgreSQL ready on 127.0.0.1:5432; database:", database, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
