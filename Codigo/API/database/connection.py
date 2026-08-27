import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

try:
    from API.config import settings
except (ImportError, AttributeError):
    from config import settings

logger = logging.getLogger("unihub_database")

# Determine connection URLs (PostgreSQL by default, SQLite fallback if specified)
db_readonly_url = settings.API_READONLY_DATABASE_URL
db_admin_url = settings.DATABASE_URL
use_sqlite = os.getenv("USE_SQLITE_FALLBACK", "false").lower() == "true"

if use_sqlite:
    sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unihub_fallback.db")
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    db_readonly_url = f"sqlite:///{sqlite_path}"
    db_admin_url = f"sqlite:///{sqlite_path}"
    
    engine_readonly = create_engine(db_readonly_url, connect_args={"check_same_thread": False})
    engine_admin = create_engine(db_admin_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine_readonly, "connect")
    def set_sqlite_pragma_ro(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    @event.listens_for(engine_admin, "connect")
    def set_sqlite_pragma_admin(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    try:
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
    except Exception as e:
        logger.warning(f"No se pudo inicializar el motor PostgreSQL ({e}). Usando motor SQLite fallback.")
        sqlite_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "unihub_fallback.db")
        os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
        db_readonly_url = f"sqlite:///{sqlite_path}"
        db_admin_url = f"sqlite:///{sqlite_path}"
        engine_readonly = create_engine(db_readonly_url, connect_args={"check_same_thread": False})
        engine_admin = create_engine(db_admin_url, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_readonly)
SessionAdmin = sessionmaker(autocommit=False, autoflush=False, bind=engine_admin)
Base = declarative_base()

def get_db():
    """Dependency for obtaining DB read-only session in FastAPI routes with rollback protection."""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Error en sesión de base de datos de solo lectura, rollback aplicado: {e}")
        raise
    finally:
        db.close()

def get_admin_db():
    """Dependency for obtaining DB admin (write) session in FastAPI routes with rollback protection."""
    db = SessionAdmin()
    try:
        yield db
    except Exception as e:
        db.rollback()
        logger.error(f"Error en sesión de base de datos de administración, rollback aplicado: {e}")
        raise
    finally:
        db.close()
