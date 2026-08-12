import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import settings

# Determine connection URLs (PostgreSQL by default, SQLite fallback if specified)
db_readonly_url = settings.API_READONLY_DATABASE_URL
db_admin_url = settings.DATABASE_URL
use_sqlite = os.getenv("USE_SQLITE_FALLBACK", "false").lower() == "true"

if use_sqlite:
    sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unihub_fallback.db")
    db_readonly_url = f"sqlite:///{sqlite_path}"
    db_admin_url = f"sqlite:///{sqlite_path}"
    
    engine_readonly = create_engine(db_readonly_url, connect_args={"check_same_thread": False})
    engine_admin = create_engine(db_admin_url, connect_args={"check_same_thread": False})
else:
    engine_readonly = create_engine(
        db_readonly_url,
        pool_pre_ping=True,
        pool_size=settings.DB_READONLY_POOL_SIZE,
        max_overflow=settings.DB_READONLY_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE
    )
    engine_admin = create_engine(
        db_admin_url,
        pool_pre_ping=True,
        pool_size=settings.DB_ADMIN_POOL_SIZE,
        max_overflow=settings.DB_ADMIN_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_readonly)
SessionAdmin = sessionmaker(autocommit=False, autoflush=False, bind=engine_admin)
Base = declarative_base()

def get_db():
    """Dependency for obtaining DB read-only session in FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_admin_db():
    """Dependency for obtaining DB admin (write) session in FastAPI routes."""
    db = SessionAdmin()
    try:
        yield db
    finally:
        db.close()
