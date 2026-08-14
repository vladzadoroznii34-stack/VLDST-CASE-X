import os
import pathlib
import psycopg

u = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")
b = pathlib.Path(__file__).resolve().parents[1]
with psycopg.connect(u) as c:
    c.execute((b / "database/schema.sql").read_text())
    c.execute((b / "database/seed.sql").read_text())
print("Database seeded")
