from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker,DeclarativeBase
from .config import settings
def normalize_url(u): return (u or "").replace("postgres://","postgresql+psycopg://",1).replace("postgresql://","postgresql+psycopg://",1)
DATABASE_URL=normalize_url(settings.database_url)
engine=create_engine(DATABASE_URL,pool_pre_ping=True) if DATABASE_URL else None
SessionLocal=sessionmaker(bind=engine) if engine else None
class Base(DeclarativeBase): pass
def get_db():
    if not SessionLocal: raise RuntimeError("DATABASE_URL is not configured")
    db=SessionLocal()
    try: yield db
    finally: db.close()
