import os
from urllib.parse import quote_plus

class Settings:
    # API Configuration
    API_TITLE: str = "API RUCT - Universidades y Titulaciones de España"
    API_VERSION: str = "1.0.0"
    API_DESCRIPTION: str = (
        "API REST oficial para acceder a los datos recolectados sobre universidades públicas y privadas "
        "de España, sus titulaciones oficiales vigentes (Grados y Másteres) y sus planes de estudio extraídos del BOE."
    )
    
    # Configuración de PostgreSQL
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "unihub_db")
    
    # Rol de Solo Lectura para Acceso Restringido de la API REST
    API_DB_USER: str = os.getenv("API_DB_USER", "unihub_api_user")
    API_DB_PASSWORD: str = os.getenv("API_DB_PASSWORD", "unihub_api_password_sec2026")

    # Clave de Administración para Operaciones CRUD y Sincronización ETL
    ADMIN_API_KEY: str = os.getenv("ADMIN_API_KEY", "unihub_super_secret_admin_key_2026")

    # Parámetros del Pool de Conexiones SQLAlchemy
    DB_READONLY_POOL_SIZE: int = int(os.getenv("DB_READONLY_POOL_SIZE", "15"))
    DB_READONLY_MAX_OVERFLOW: int = int(os.getenv("DB_READONLY_MAX_OVERFLOW", "25"))
    DB_ADMIN_POOL_SIZE: int = int(os.getenv("DB_ADMIN_POOL_SIZE", "5"))
    DB_ADMIN_MAX_OVERFLOW: int = int(os.getenv("DB_ADMIN_MAX_OVERFLOW", "10"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    @property
    def DATABASE_URL(self) -> str:
        """Constructs PostgreSQL SQLAlchemy connection string.
        Credentials are URL-encoded to handle special characters (@, /, %, etc.).
        """
        user = quote_plus(self.POSTGRES_USER)
        password = quote_plus(self.POSTGRES_PASSWORD)
        return f"postgresql+psycopg2://{user}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}?client_encoding=utf8"

    @property
    def API_READONLY_DATABASE_URL(self) -> str:
        """Constructs Read-Only PostgreSQL connection string for API Service Role.
        Credentials are URL-encoded to handle special characters (@, /, %, etc.).
        """
        user = quote_plus(self.API_DB_USER)
        password = quote_plus(self.API_DB_PASSWORD)
        return f"postgresql+psycopg2://{user}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}?client_encoding=utf8"

settings = Settings()
