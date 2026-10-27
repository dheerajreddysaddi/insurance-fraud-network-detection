"""Configuration. Paths are relative to the repo root; secrets come from environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")  # does not override variables already set in the environment

DATA_DIR = ROOT_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
GROUND_TRUTH_DIR = DATA_DIR / "ground_truth"
CONFIG_DIR = ROOT_DIR / "config"


def get_database_url() -> str:
    """DATABASE_URL unset -> local SQLite file. Set -> that database (e.g. Neon Postgres)."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        DATA_DIR.mkdir(exist_ok=True)
        return "sqlite:///" + (DATA_DIR / "app.db").as_posix()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://"):]
    return url