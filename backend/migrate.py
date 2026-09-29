from pathlib import Path

import psycopg

from forecast.config import required_env


with psycopg.connect(required_env("DATABASE_URL")) as connection:
    connection.execute((Path(__file__).parent / "migrations" / "001_init.sql").read_text())

print("Migration 001_init.sql applied.")
