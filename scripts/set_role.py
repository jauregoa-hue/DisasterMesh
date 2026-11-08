"""Local operator bootstrap; requires filesystem/database access, never a public API."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
load_dotenv()
from sqlalchemy import select
from main import GATEWAY_USERNAME, SessionLocal, User, audit

parser = argparse.ArgumentParser()
parser.add_argument("username")
parser.add_argument("role", choices=["responder", "admin", "citizen"])
args = parser.parse_args()
with SessionLocal() as db:
    user = db.scalar(select(User).where(User.username == args.username))
    if not user or user.username == GATEWAY_USERNAME:
        parser.error("Register a dashboard user first; gateway identity cannot be changed")
    user.role = args.role
    audit(db, user.id, "local.role.change." + args.role)
    db.commit()
print(f"{args.username}: {args.role}. Log out and back in to refresh the dashboard role.")
