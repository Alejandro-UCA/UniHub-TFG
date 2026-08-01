import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# Determine connection URL (PostgreSQL by default, SQLite fallback if specified)
db_url = settings.DATABASE_URL
use_sqlite = os.getenv("USE_SQLITE_FALLBACK", "false").lower() == "true"

if use_sqlite:
    sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ruct_fallback.db")
    db_url = f"sqlite:///{sqlite_path}"
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    """Dependency for obtaining DB session in FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
