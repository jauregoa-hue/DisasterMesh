"""Generate local secrets once; never overwrite an existing .env."""
import argparse
import secrets
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--sqlite-demo", action="store_true")
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    print("Existing .env preserved. Check DATABASE_URL before launching.")
else:
    password = secrets.token_hex(24)
    url = "sqlite:///./disastermesh-dev.db" if args.sqlite_demo else f"postgresql+psycopg://disastermesh:{password}@127.0.0.1:5432/disastermesh"
    target.write_text(
        f"POSTGRES_DB=disastermesh\nPOSTGRES_USER=disastermesh\nPOSTGRES_PASSWORD={password}\n"
        f"DATABASE_URL={url}\nJWT_SECRET={secrets.token_urlsafe(48)}\nGATEWAY_API_KEY={secrets.token_urlsafe(48)}\n"
        "MESHTASTIC_PORT=COM9\nMESHTASTIC_ALLOWED_NODES=!0436bda8\nGATEWAY_API_URL=http://localhost:8000\n"
        "GATEWAY_OUTBOX=./gateway-outbox.db\nGPS_MAX_AGE_SECONDS=300\nAI_MODE=rules\nVITE_MAP_TILE_URL=\n",
        encoding="utf-8")
    print(f"Created .env with random secrets ({'SQLite demo' if args.sqlite_demo else 'PostgreSQL'}).")
